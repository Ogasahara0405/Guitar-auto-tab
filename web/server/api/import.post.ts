/**
 * POST /api/import — Claude Codeで磨いた analysis.json の取り込み（旧 api_import）
 */
import { createError, readMultipartFormData } from "h3";
import { importAnalysis } from "../core/pipeline";
import { workerCtx } from "../utils/gat";

export default defineEventHandler(async (event) => {
  const form = (await readMultipartFormData(event)) ?? [];
  const part = form.find((p) => p.filename && p.data.length);
  if (!part) {
    throw createError({ statusCode: 400, message: "JSONファイルを指定してください" });
  }
  try {
    return await importAnalysis(workerCtx(event), part.data.toString("utf-8"));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw createError({ statusCode: 400, message: `JSONの取り込みに失敗しました: ${msg}` });
  }
});
