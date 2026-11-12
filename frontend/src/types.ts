/** analysis.json（バックエンドの解析結果）の型定義 */

export interface NoteEvent {
  start: number;
  end: number;
  midi: number;
  /** 6=低音E弦 … 1=高音e弦（未割当の場合は null） */
  string: number | null;
  /** フレット番号（未割当の場合は null） */
  fret: number | null;
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
}

export interface AnalysisMeta {
  title: string;
  duration: number;
  tempo: number;
  mode: "melody" | "chords";
  tuning?: string;
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
