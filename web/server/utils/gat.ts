/**
 * ワーカーコンテキストの構築（リポジトリルートと python 実行ファイルの解決）
 */
import { join } from "node:path";
import type { H3Event } from "h3";
import { useRuntimeConfig } from "#imports";
import type { WorkerCtx } from "../worker/client";

export function workerCtx(event: H3Event): WorkerCtx {
  const config = useRuntimeConfig(event);
  // NUXT_GAT_ROOT / NUXT_GAT_PYTHON で runtimeConfig が上書きされる。
  // run.bat 等が渡す素の GAT_ROOT / GAT_PYTHON も受け付ける。
  const root = config.gatRoot || process.env.GAT_ROOT || process.cwd();
  const python =
    config.gatPython ||
    process.env.GAT_PYTHON ||
    (process.platform === "win32"
      ? join(root, ".venv", "Scripts", "python.exe")
      : join(root, ".venv", "bin", "python"));
  return { root, python };
}
