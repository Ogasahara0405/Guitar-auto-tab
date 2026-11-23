/**
 * 解析パイプライン統括: 入力 → ワーカー知覚 → 選別・割当 → 成果物保存
 *
 * 旧: app/core/pipeline.py のオーケストレーションを移植。
 * DSP（音源分離・採譜・映像解析）は Python ワーカーが担い、
 * tone の閾値による除去・映像ゲート・弦/フレット割当・ボイシング・
 * 譜面描画・保存をここで行う。
 */
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { cp, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import {
  AnalysisResult,
  type ChordEvent,
  type ChordStyle,
  type Mode,
  type NoteEvent,
} from "../../shared/schema";
import { acquire, extractFrames, perceive, verifyMutes, type WorkerCtx } from "../worker/client";
import { cleanMelodyNotes } from "./clean";
import { gateChords, gateNotes } from "./gate";
import { assignFrets, type RawNote } from "./tabassign";
import { shapeFor } from "./voicing";
import { renderPdf } from "./pdf";
import { scoreToAscii } from "./render";

/** ギターとみなす音色一致度の下限（旧 tone.py の TONE_MIN） */
const TONE_MIN = 0.5;

/** 旧 uuid4().hex[:8] と同じ 8桁のジョブID */
function newJobId(): string {
  return randomBytes(4).toString("hex");
}

export function jobDir(root: string, id: string): string {
  return join(root, "output", id);
}

/** 時刻 t に対応するフレーム名を返す（無ければ null）。旧 video.frame_for */
export function frameFor(frames: Record<string, string>, t: number, tol = 0.35): string | null {
  const entries = Object.entries(frames ?? {});
  if (!entries.length) return null;
  let best: string | null = null;
  let bestD = Infinity;
  for (const [k, name] of entries) {
    const d = Math.abs(Number(k) - t);
    if (d <= tol && d < bestD) {
      best = name;
      bestD = d;
    }
  }
  return best;
}

export interface AnalyzeParams {
  mode: Mode;
  chordStyle: ChordStyle;
  source: { kind: "url"; url: string } | { kind: "file"; path: string; filename: string };
  separate?: boolean;
}

/**
 * 解析の本体。
 * mode: "melody"(単音/リード) | "chords"(コード/バッキング)
 * chordStyle: "chord"(フルコード) | "power"(パワーコード) ※chordsモード時のみ
 * separate: Demucsによるギター音源分離を使う（未導入・失敗時は自動で元音声で解析）
 * 戻り値: 解析結果（AnalysisResult）。artifacts は output/<id>/ に保存。
 */
export async function analyze(ctx: WorkerCtx, params: AnalyzeParams): Promise<AnalysisResult> {
  const id = newJobId();
  const workdir = jobDir(ctx.root, id);
  await mkdir(workdir, { recursive: true });

  // --- メディア取得（YouTube / ローカルファイル） ---
  const acq =
    params.source.kind === "url"
      ? await acquire(ctx, { out: workdir, url: params.source.url })
      : await acquire(ctx, { out: workdir, file: params.source.path });
  // ファイル入力時はアップロード元のファイル名をタイトルにする（一時ファイル名で上書き）
  const title =
    params.source.kind === "file"
      ? params.source.filename.replace(/\.[^.]+$/, "")
      : acq.title;

  // --- 知覚（Demucs分離・採譜・コード抽出・映像動作解析・拍検出） ---
  const perc = await perceive(ctx, {
    src: join(workdir, acq.media),
    out: workdir,
    mode: params.mode,
    separate: params.separate,
  });

  let notes: NoteEvent[] = [];
  let chords: ChordEvent[] = [];
  let toneDropped: number | null = null;
  let cleanDropped: number | null = null;

  if (params.mode === "melody") {
    // ギター音色モデルで無関係な音を除去（スコア未満を落とす）
    const keptByTone = perc.notes.filter((n) => n.tone >= TONE_MIN);
    toneDropped = perc.notes.length - keptByTone.length;
    // 不要音クリーニング（断片・弱い短音・根拠の弱い副次声を落とす）
    const [cleaned, d] = cleanMelodyNotes(keptByTone);
    cleanDropped = d;
    // 映像（演奏動作）に忠実に選別し、弦/フレットを割り当てる
    const gated = gateNotes(cleaned, perc.play);
    const assigned = assignFrets(gated.notes as RawNote[], gated.laneHints, gated.fretHints);
    notes = assigned.map((n) => ({
      start: n.start,
      end: n.end,
      midi: Math.round(n.midi),
      string: n.string ?? null,
      fret: n.fret ?? null,
      evidence: (n.evidence as number | null | undefined) ?? null,
      tone: (n.tone as number | null | undefined) ?? null,
      frame: null,
    }));
  } else {
    // 映像に忠実にコードを選別 → 押さえ方を決め、ミュート弦を音声で確認
    const gated = gateChords(perc.chords, perc.play);
    let lastPos = 0.0;
    const shaped: { start: number; end: number; label: string; shape: { string: number; fret: number }[] }[] = [];
    for (const c of gated.chords) {
      if (c.label === "N.C.") continue;
      const v = shapeFor(c.label, params.chordStyle, lastPos);
      if (v === null) continue;
      lastPos = v.pos;
      shaped.push({ start: c.start, end: c.end, label: c.label, shape: v.shape });
    }
    let mutedPer: number[][] = shaped.map(() => []);
    if (shaped.length) {
      const resp = await verifyMutes(ctx, {
        audio: join(workdir, perc.audio_file),
        request: shaped.map((s) => ({ start: s.start, end: s.end, shape: s.shape })),
      });
      mutedPer = resp.muted;
    }
    chords = shaped.map((s, i) => {
      const muted = mutedPer[i] ?? [];
      return {
        start: s.start,
        end: s.end,
        label: s.label,
        shape: s.shape.filter((st) => !muted.includes(st.string)),
        muted: muted.length ? muted : null,
        frame: null,
      };
    });
  }

  // 映像がある場合、各ノート/コード位置のフレームを切り出してリンクする
  const events = [...notes, ...chords];
  let frames: Record<string, string> = {};
  if (events.length) {
    const resp = await extractFrames(ctx, {
      src: join(workdir, acq.media),
      out: workdir,
      times: events.map((e) => e.start),
    });
    frames = resp.frames;
  }
  let linked = 0;
  for (const e of events) {
    const name = frameFor(frames, e.start);
    if (name) {
      e.frame = name;
      linked += 1;
    }
  }

  const body = {
    meta: {
      title,
      duration: perc.duration,
      tempo: params.mode === "chords" ? (perc.chords_tempo ?? perc.tempo) : perc.tempo,
      mode: params.mode,
      tuning: "EADGBE",
      separated: perc.separated,
      video_frames: linked ? Object.keys(frames).length : null,
      tone_dropped: toneDropped,
      clean_dropped: cleanDropped,
      source_job: null,
      generated: new Date().toISOString().slice(0, 19),
      media_file: params.source.kind === "file" ? acq.media : null,
    },
    notes,
    chords,
    beats: perc.beats,
    barlines: perc.barlines,
  };
  const result = AnalysisResult.parse({ ...body, id });

  await saveArtifacts(result, workdir);
  return result;
}

/**
 * Claude Codeで磨いた analysis.json を取り込み、ジョブとして登録する
 * （表示・PDF/TXT出力を同じ流れで行えるようにする）
 */
export async function importAnalysis(ctx: WorkerCtx, jsonText: string): Promise<AnalysisResult> {
  const data = JSON.parse(jsonText);
  if (!data || typeof data !== "object" || !("meta" in data)) {
    throw new Error("meta を含む解析結果JSONを指定してください");
  }
  const id = newJobId();
  const workdir = jobDir(ctx.root, id);
  await mkdir(workdir, { recursive: true });
  // 磨き上げ元ジョブの映像フレームを引き継ぐ（リンク切れを防ぐ）
  const srcJob = data.meta?.source_job;
  if (typeof srcJob === "string" && /^[0-9a-f]{8}$/.test(srcJob)) {
    const srcFrames = join(ctx.root, "output", srcJob, "frames");
    if (existsSync(srcFrames)) {
      await cp(srcFrames, join(workdir, "frames"), { recursive: true });
    }
  }
  const result = AnalysisResult.parse({ ...data, id });
  await saveArtifacts(result, workdir);
  return result;
}

/** 成果物（analysis.json / tab.txt / tab.pdf）を output/<id>/ に保存 */
export async function saveArtifacts(result: AnalysisResult, workdir: string): Promise<void> {
  await writeFile(join(workdir, "analysis.json"), JSON.stringify(result, null, 2), "utf-8");
  await writeFile(join(workdir, "tab.txt"), scoreToAscii(result), "utf-8");
  await renderPdf(result, join(workdir, "tab.pdf"));
}
