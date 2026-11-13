/** analysis.json（バックエンドの解析結果）の型定義
 *
 * 型の実体はバックエンドの app/schemas.py（Pydantic）— Python/TypeScript で
 * 手書きの二重管理をしないため、OpenAPI 経由で機械的に同期する:
 *   app/schemas.py → app/export_openapi.py → openapi.json → npm run gen:api → api-types.ts
 * ここはその受け口（再エクスポート）。APIの形式を変えたら上の手順で再生成すること。
 */
export type {
  ShapeNote,
  NoteEvent,
  ChordEvent,
  AnalysisMeta,
  AnalysisResult,
} from "./api-types";

/** タブ譜表示用のイベント（ノートまたはコード）— UI内部の型（API契約外） */
export interface TabEvent {
  start: number;
  end: number;
  cells: { row: number; text: string }[];
  label: string | null;
}
