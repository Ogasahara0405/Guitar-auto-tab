/**
 * GET /api/jobs/:id/frames/:frame — 映像フレーム画像の配信（旧 job_frame）
 */
import { createReadStream, existsSync } from "node:fs";
import { basename, join } from "node:path";
import { createError, getRouterParam, sendStream, setHeader } from "h3";
import { jobDir } from "../../../../core/pipeline";
import { workerCtx } from "../../../../utils/gat";

const JOB_ID_RE = /^[0-9a-f]{8}$/;

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, "id") ?? "";
  const frame = basename(getRouterParam(event, "frame") ?? "");
  if (!JOB_ID_RE.test(id) || !/^frame_[0-9]+\.[0-9]+\.jpg$/.test(frame)) {
    throw createError({ statusCode: 404, message: "フレームが見つかりません" });
  }
  const { root } = workerCtx(event);
  const p = join(jobDir(root, id), "frames", frame);
  if (!existsSync(p)) {
    throw createError({ statusCode: 404, message: "フレームが見つかりません" });
  }
  setHeader(event, "Content-Type", "image/jpeg");
  return sendStream(event, createReadStream(p));
});
