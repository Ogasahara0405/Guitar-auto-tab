/**
 * GET /api/jobs/:id/:name — 成果物の配信（旧 job_pdf / job_txt / job_json / job_media）
 * name: tab.pdf | tab.txt | analysis.json | media
 */
import { createReadStream, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { basename, extname, join } from "node:path";
import { createError, getRouterParam, sendStream, setHeader } from "h3";
import { jobDir } from "../../../core/pipeline";
import { workerCtx } from "../../../utils/gat";

const JOB_ID_RE = /^[0-9a-f]{8}$/;

const MIME: Record<string, string> = {
  ".pdf": "application/pdf",
  ".txt": "text/plain; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".mov": "video/quicktime",
  ".m4v": "video/mp4",
  ".m4a": "audio/mp4",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
};

function sendFile(event: Parameters<typeof sendStream>[0], path: string) {
  setHeader(event, "Content-Type", MIME[extname(path).toLowerCase()] || "application/octet-stream");
  return sendStream(event, createReadStream(path));
}

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, "id") ?? "";
  const name = getRouterParam(event, "name") ?? "";
  if (!JOB_ID_RE.test(id)) {
    throw createError({ statusCode: 404, message: "ジョブが見つかりません" });
  }
  const { root } = workerCtx(event);
  const dir = jobDir(root, id);

  if (name === "media") {
    const metaPath = join(dir, "analysis.json");
    if (!existsSync(metaPath)) {
      throw createError({ statusCode: 404, message: "ジョブが見つかりません" });
    }
    const data = JSON.parse(await readFile(metaPath, "utf-8"));
    const mf = data?.meta?.media_file;
    if (typeof mf !== "string" || !mf) {
      throw createError({ statusCode: 404, message: "メディアがありません" });
    }
    const p = join(dir, basename(mf));
    if (!existsSync(p)) {
      throw createError({ statusCode: 404, message: "メディアがありません" });
    }
    return sendFile(event, p);
  }

  if (!["tab.pdf", "tab.txt", "analysis.json"].includes(name)) {
    throw createError({ statusCode: 404, message: "成果物が見つかりません" });
  }
  const p = join(dir, name);
  if (!existsSync(p)) {
    throw createError({ statusCode: 404, message: "成果物が見つかりません" });
  }
  return sendFile(event, p);
});
