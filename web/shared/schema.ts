/**
 * 解析結果（analysis.json）とワーカー応答のスキーマ — 単一情報源（zod）
 *
 * 旧構成（app/schemas.py の Pydantic → OpenAPI → api-types.ts 生成）に代わり、
 * この1ファイルを Python/TS 間の契約の単一情報源とする。
 * TypeScript 型は z.infer で導出し、API 境界（server/api/）と
 * ワーカー出力の検証（server/worker/client.ts）の両方で使う。
 *
 * 磨き上げフロー（Claude Code で analysis.json を修正して取り込む）で
 * 未知のキーが付いても落とさないよう、オブジェクトは passthrough で扱う。
 */
import { z } from "zod";

/** メロディ/コードのモード */
export const Mode = z.enum(["melody", "chords"]);
/** コードの出力形式（chords モード時） */
export const ChordStyle = z.enum(["chord", "power"]);

export type Mode = z.infer<typeof Mode>;
export type ChordStyle = z.infer<typeof ChordStyle>;

/** 未知キーを許容する契約オブジェクト（Pydantic の extra="allow" 相当） */
const contract = <T extends z.ZodRawShape>(shape: T) => z.object(shape).passthrough();

export const ShapeNote = contract({
  string: z.number().int().describe("6=低音E弦 … 1=高音e弦"),
  fret: z.number().int().describe("フレット番号"),
});

export const NoteEvent = contract({
  start: z.number(),
  end: z.number(),
  midi: z.number().int(),
  string: z.number().int().nullable().default(null).describe("6=低音E弦 … 1=高音e弦"),
  fret: z.number().int().nullable().default(null).describe("フレット番号"),
  evidence: z.number().nullable().default(null).describe("採譜の音声根拠（0..1）"),
  tone: z.number().nullable().default(null).describe("ギター音色モデルとの一致度（0..1）"),
  frame: z.string().nullable().default(null).describe("ブリッジ側の確認用フレーム画像名"),
});

export const ChordEvent = contract({
  start: z.number(),
  end: z.number(),
  label: z.string(),
  shape: z.array(ShapeNote),
  muted: z.array(z.number().int()).nullable().default(null).describe("ミュートと判定して除いた弦番号"),
  frame: z.string().nullable().default(null),
});

export const AnalysisMeta = contract({
  title: z.string(),
  duration: z.number(),
  tempo: z.number(),
  mode: Mode,
  tuning: z.string().nullable().default(null),
  separated: z.boolean().nullable().default(null).describe("Demucsによる音源分離を使った場合 true"),
  video_frames: z.number().int().nullable().default(null),
  tone_dropped: z.number().int().nullable().default(null),
  source_job: z.string().nullable().default(null).describe("磨き上げ元ジョブID（フレーム引き継ぎ用）"),
  generated: z.string().nullable().default(null),
  media_file: z.string().nullable().default(null).describe("ブラウザ再生用の元メディア（ファイル入力時のみ）"),
});

/** 解析結果の本体（id なし。保存ファイル・取り込み用） */
export const AnalysisBody = contract({
  meta: AnalysisMeta,
  notes: z.array(NoteEvent),
  chords: z.array(ChordEvent),
  beats: z.array(z.number()),
  barlines: z.array(z.number()),
});

/** API が返す解析結果（analysis.json と同じ構造 + id） */
export const AnalysisResult = AnalysisBody.extend({
  id: z.string(),
});

export type ShapeNote = z.infer<typeof ShapeNote>;
export type NoteEvent = z.infer<typeof NoteEvent>;
export type ChordEvent = z.infer<typeof ChordEvent>;
export type AnalysisMeta = z.infer<typeof AnalysisMeta>;
export type AnalysisBody = z.infer<typeof AnalysisBody>;
export type AnalysisResult = z.infer<typeof AnalysisResult>;

/* ==== ワーカー（worker/）出力の契約 ==== */

/** 映像の演奏動作データ（gate.ts がノート/コードの選別に使う） */
export const PlayEvent = z.object({
  t: z.number(),
  strength: z.number(),
  y: z.number().nullable().describe("動きの縦位置（動きが無いフレームは null）"),
  width: z.number(),
  units: z.number().describe("縦の広がり（弦1本分の倍数）"),
});

export const FretMap = z.object({
  a: z.number().describe("ナット位置（ピクセル）"),
  b: z.number().describe("スケール長（ピクセル）"),
  w: z.number().int().describe("基準フレーム幅"),
  inliers: z.number().int(),
  residual: z.number(),
});

export const PlayData = z.object({
  times: z.array(z.number()),
  energy: z.array(z.number()),
  events: z.array(PlayEvent),
  band: z.tuple([z.number(), z.number()]).nullable(),
  p90: z.number(),
  neck_xs: z.array(z.number().nullable()),
  fret_map: FretMap.nullable(),
});

export const PerceptionNote = z.object({
  start: z.number(),
  end: z.number(),
  midi: z.number().int(),
  evidence: z.number().default(1),
  tone: z.number().default(1).describe("ギター音色モデルとの一致度（スコアのみ・除去はweb側）"),
});

export const PerceptionChord = z.object({
  start: z.number(),
  end: z.number(),
  label: z.string(),
});

/** `python -m worker perceive` の出力 */
export const PerceptionResult = z.object({
  duration: z.number(),
  tempo: z.number(),
  chords_tempo: z.number().nullable().describe("コード抽出側のテンポ（chords モードで使用）"),
  separated: z.boolean(),
  mode: Mode,
  audio_file: z.string().describe("ミュート確認に使うwav（jobディレクトリ基準のファイル名）"),
  notes: z.array(PerceptionNote),
  chords: z.array(PerceptionChord),
  play: PlayData.nullable(),
  beats: z.array(z.number()),
  barlines: z.array(z.number()),
});

/** `python -m worker acquire` の出力 */
export const AcquireResult = z.object({
  wav: z.string(),
  title: z.string(),
  media: z.string().describe("映像/音声の取得元ファイル（フレーム抽出・動作解析に使用）"),
});

/** `python -m worker frames` の出力 */
export const FramesResult = z.object({
  frames: z.record(z.string()).describe("時刻(秒, 文字列キー) → フレーム画像ファイル名"),
});

/** `python -m worker verify-mutes` の入力1要素 */
export const MuteCheckItem = z.object({
  start: z.number(),
  end: z.number(),
  shape: z.array(z.object({ string: z.number().int(), fret: z.number().int() })),
});

/** `python -m worker verify-mutes` の出力 */
export const MuteCheckResult = z.object({
  muted: z.array(z.array(z.number().int())).describe("入力順に対応するミュート弦番号"),
});

export type PlayEvent = z.infer<typeof PlayEvent>;
export type FretMap = z.infer<typeof FretMap>;
export type PlayData = z.infer<typeof PlayData>;
export type PerceptionNote = z.infer<typeof PerceptionNote>;
export type PerceptionChord = z.infer<typeof PerceptionChord>;
export type PerceptionResult = z.infer<typeof PerceptionResult>;
export type AcquireResult = z.infer<typeof AcquireResult>;
export type FramesResult = z.infer<typeof FramesResult>;
export type MuteCheckItem = z.infer<typeof MuteCheckItem>;
export type MuteCheckResult = z.infer<typeof MuteCheckResult>;
