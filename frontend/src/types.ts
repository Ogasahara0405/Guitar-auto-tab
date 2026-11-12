/** analysis.json（バックエンドの解析結果）の型定義 */

export interface NoteEvent {
  start: number;
  end: number;
  midi: number;
  /** 6=低音E弦 … 1=高音e弦（未割当の場合は null） */
  string: number | null;
  /** フレット番号（未割当の場合は null） */
  fret: number | null;
  /** 採譜の音声根拠（0..1。大きいほど確実に鳴っている） */
  evidence?: number;
  /** ブリッジ側の弦の確認用フレーム画像（frames/ 内のファイル名） */
  frame?: string;
}

export interface ShapeNote {
  /** 6=低音E弦 … 1=高音e弦 */
  string: number;
  fret: number;
}

export interface ChordEvent {
  start: number;
  end: number;
  label: string;
  shape: ShapeNote[];
  /** 音声確認で鳴っていない（ミュート）と判定して除いた弦番号 */
  muted?: number[];
  /** ブリッジ側の弦の確認用フレーム画像（frames/ 内のファイル名） */
  frame?: string;
}

export interface AnalysisMeta {
  title: string;
  duration: number;
  tempo: number;
  mode: "melody" | "chords";
  tuning?: string;
  /** Demucsによるギター音源分離を使った場合 true */
  separated?: boolean;
  /** 切り出した映像フレームの枚数（0/未定義なら映像なし） */
  video_frames?: number;
  /** 磨き上げ元ジョブID（フレーム引き継ぎ用） */
  source_job?: string;
  generated?: string;
  /** ブラウザ再生用に保存された元メディア（ファイル入力時のみ） */
  media_file?: string;
}

export interface AnalysisResult {
  id: string;
  meta: AnalysisMeta;
  notes: NoteEvent[];
  chords: ChordEvent[];
  beats: number[];
  barlines: number[];
}

/** タブ譜表示用のイベント（ノートまたはコード） */
export interface TabEvent {
  start: number;
  end: number;
  cells: { row: number; text: string }[];
  label: string | null;
}
