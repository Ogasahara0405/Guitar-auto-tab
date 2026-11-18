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

/** 既定の runner: python -m worker を起動し、最後の stdout 行を JSON として読む */
export const defaultRunner: WorkerRunner = (args, opts) =>
  new Promise((resolvePromise, reject) => {
    const proc = spawn(opts.python, ["-m", "worker", ...args], {
      cwd: opts.root,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let out = "";
    let err = "";
    proc.stdout.on("data", (d: Buffer) => (out += d.toString()));
    proc.stderr.on("data", (d: Buffer) => (err += d.toString()));
    proc.on("error", (e) =>
      reject(new Error(`worker を起動できません（${opts.python}）: ${e.message}`)),
    );
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `worker ${args[0]} が失敗しました（code=${code}）: ${err.slice(-800) || out.slice(-400)}`,
          ),
        );
        return;
      }
      const line = out.trim().split("\n").pop() ?? "";
      try {
        resolvePromise(JSON.parse(line));
      } catch {
        reject(new Error(`worker ${args[0]} のJSON出力を解釈できません: ${line.slice(0, 400)}`));
      }
    });
    if (opts.stdin !== undefined) {
      proc.stdin.write(opts.stdin);
    }
    proc.stdin.end();
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
