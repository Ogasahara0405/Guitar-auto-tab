/**
 * Python採譜ワーカー（../worker）のクライアント
 *
 * `python -m worker <cmd> ...` を subprocess で起動し、stdout の JSON を
 * zod（shared/schema.ts）で検証して返す。runner はテストで差し替え可能。
 */
import { spawn } from "node:child_process";
import {
  AcquireResult,
  FramesResult,
  MuteCheckItem,
  MuteCheckResult,
  PerceptionResult,
  type Mode,
} from "../../shared/schema";

export interface WorkerCtx {
  /** リポジトリルート（output/ と .venv の基準） */
  root: string;
  /** worker 起動用の python 実行ファイル */
  python: string;
  /** テスト用の差し替え */
  runner?: WorkerRunner;
}

export type WorkerRunner = (
  args: string[],
  opts: { root: string; python: string; stdin?: string },
) => Promise<unknown>;

/** worker の結果JSON行マーカー（worker/__main__.py の JSON_MARKER と一致させる） */
const JSON_MARKER = "__GAT_JSON__";

/**
 * worker の stdout から結果 JSON を取り出す（worker/__main__.py の _dump と対）。
 * - 行頭アンカー（"\n" + マーカー）で最後の出現を探す: JSON ペイロード内に
 *   同じ文字列（例: 動画タイトル）が含まれても誤検出しない（json.dumps は
 *   改行を出さないため本物のマーカー行は必ずアンカーに一致する）
 * - マーカーが無ければ従来どおり最後の行を JSON として試す
 * - マーカー直後の1行のみを渡し、後続ノイズに耐える
 */
export function parseWorkerOutput(out: string): unknown {
  const anchor = "\n" + JSON_MARKER;
  const idx = out.lastIndexOf(anchor);
  let payload: string;
  if (idx >= 0) {
    payload = out.slice(idx + anchor.length);
  } else if (out.startsWith(JSON_MARKER)) {
    payload = out.slice(JSON_MARKER.length);
  } else {
    payload = out.trim().split("\n").pop() ?? "";
  }
  return JSON.parse(payload.split("\n", 1)[0].trim());
}

/**
 * 既定の runner: python -m worker を起動し、stdout のマーカー行以降を JSON として読む。
 * yt-dlp の進捗など改行なしのノイズが混ざっても壊れない。
 * （UTF-8のマルチバイト境界でチャンク分割されても化けないよう、
 *   Buffer を蓄積してから一括デコードする）
 */
export const defaultRunner: WorkerRunner = (args, opts) =>
  new Promise((resolvePromise, reject) => {
    const proc = spawn(opts.python, ["-m", "worker", ...args], {
      cwd: opts.root,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];
    proc.stdout.on("data", (d: Buffer) => outChunks.push(d));
    proc.stderr.on("data", (d: Buffer) => errChunks.push(d));
    proc.on("error", (e) =>
      reject(new Error(`worker を起動できません（${opts.python}）: ${e.message}`)),
    );
    proc.on("close", (code) => {
      const out = Buffer.concat(outChunks).toString("utf-8");
      const err = Buffer.concat(errChunks).toString("utf-8");
      if (code !== 0) {
        reject(
          new Error(
            `worker ${args[0]} が失敗しました（code=${code}）: ${err.slice(-800) || out.slice(-400)}`,
          ),
        );
        return;
      }
      try {
        resolvePromise(parseWorkerOutput(out));
      } catch {
        reject(new Error(`worker ${args[0]} のJSON出力を解釈できません: ${out.slice(-400)}`));
      }
    });
    if (opts.stdin !== undefined) {
      proc.stdin?.write(opts.stdin);
    }
    proc.stdin?.end();
  });

async function run<T>(
  ctx: WorkerCtx,
  schema: { parse: (v: unknown) => T },
  args: string[],
  stdin?: string,
): Promise<T> {
  const runner = ctx.runner ?? defaultRunner;
  const raw = await runner(args, { root: ctx.root, python: ctx.python, stdin });
  try {
    return schema.parse(raw);
  } catch (e) {
    throw new Error(`worker ${args[0]} の出力が契約と一致しません: ${String(e).slice(0, 500)}`);
  }
}

/** メディアの取得（YouTube URL / ローカルファイル） */
export function acquire(
  ctx: WorkerCtx,
  params: { out: string; url?: string; file?: string },
) {
  const args = ["acquire", "--out", params.out];
  if (params.url) args.push("--url", params.url);
  else if (params.file) args.push("--file", params.file);
  else throw new Error("acquire には url か file が必要です");
  return run(ctx, AcquireResult, args);
}

/** 音声・映像の知覚（採譜・コード抽出・動作解析・拍検出） */
export function perceive(
  ctx: WorkerCtx,
  params: { src: string; out: string; mode: Mode; separate?: boolean },
) {
  const args = ["perceive", "--src", params.src, "--out", params.out, "--mode", params.mode];
  if (params.separate === false) args.push("--no-separate");
  return run(ctx, PerceptionResult, args);
}

/** 指定時刻の映像フレーム抽出（frames/ に保存される） */
export function extractFrames(
  ctx: WorkerCtx,
  params: { src: string; out: string; times: number[] },
) {
  return run(ctx, FramesResult, [
    "frames",
    "--src",
    params.src,
    "--out",
    params.out,
    "--times",
    "-",
  ], JSON.stringify(params.times));
}

/** 押さえ方のミュート弦の音声確認 */
export function verifyMutes(
  ctx: WorkerCtx,
  params: { audio: string; request: MuteCheckItem[] },
) {
  return run(ctx, MuteCheckResult, [
    "verify-mutes",
    "--audio",
    params.audio,
    "--request",
    "-",
  ], JSON.stringify(params.request));
}
