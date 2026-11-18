/**
 * POST /api/analyze — 解析の実行（旧 FastAPI api_analyze と同一のAPI契約）
 * FormData: mode / chord_style / url / file
 */
import { randomBytes } from "node:crypto";
import { writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { createError, readMultipartFormData } from "h3";
import { ChordStyle, Mode } from "../../shared/schema";
import { analyze } from "../core/pipeline";
import { workerCtx } from "../utils/gat";

export default defineEventHandler(async (event) => {
  const form = (await readMultipartFormData(event)) ?? [];
  const fields = new Map<string, string>();
  let filePath: string | null = null;
  let filename = "audio";
  for (const part of form) {
    if (part.filename && part.data.length) {
      const ext = extname(part.filename) || ".bin";
      const tmp = join(tmpdir(), `gat-upload-${randomBytes(8).toString("hex")}${ext}`);
      await writeFile(tmp, part.data);
      filePath = tmp;
      filename = part.filename;
    } else if (part.name) {
      fields.set(part.name, part.data.toString("utf-8"));
    }
  }

  const url = (fields.get("url") || "").trim();
  if (!url && filePath === null) {
    throw createError({ statusCode: 400, message: "YouTube URL またはファイルを指定してください" });
  }

  const mode = Mode.safeParse(fields.get("mode") || "melody");
  const chordStyle = ChordStyle.safeParse(fields.get("chord_style") || "chord");
  if (!mode.success || !chordStyle.success) {
    throw createError({ statusCode: 400, message: "mode / chord_style の値が不正です" });
  }

  try {
    return await analyze(workerCtx(event), {
      mode: mode.data,
      chordStyle: chordStyle.data,
      source: filePath
        ? { kind: "file", path: filePath, filename }
        : { kind: "url", url },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw createError({ statusCode: 500, message: `解析に失敗しました: ${msg}` });
  }
});
