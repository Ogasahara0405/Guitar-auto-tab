"""解析結果（analysis.json）のAPIスキーマ — 言語をまたぐ契約の単一情報源

Python(Pydantic) と TypeScript の間で型定義を手書き二重管理しないため、
このファイルを元に機械的に同期する:

    app/schemas.py（ここ）
      → OpenAPI:  .venv\\Scripts\\python.exe app\\export_openapi.py
      → frontend/openapi.json
      → frontend/src/api-types.ts（生成物: npm run gen:api）

フロントの frontend/src/types.ts は api-types.ts の再エクスポート。
API の形式を変えたら export_openapi.py を実行して frontend/openapi.json を
更新すること（tests/test_pipeline.py の test_api_contract がずれを検出する）。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# リクエスト側の列挙（フォームパラメータの検証にも使う）
Mode = Literal["melody", "chords"]
ChordStyle = Literal["chord", "power"]


class _ContractBase(BaseModel):
    # 磨き上げフローで未知のキーが付いても落とさない（契約の既知フィールドは型検証する）
    model_config = ConfigDict(extra="allow")


class ShapeNote(_ContractBase):
    """コード押さえ方の1弦分"""

    string: int = Field(description="6=低音E弦 … 1=高音e弦")
    fret: int = Field(description="フレット番号")


class NoteEvent(_ContractBase):
    """1つのノート（同時発音は start が一致した複数ノートとして表現）"""

    start: float
    end: float
    midi: int
    string: int | None = Field(description="6=低音E弦 … 1=高音e弦（未割当の場合は null）")
    fret: int | None = Field(description="フレット番号（未割当の場合は null）")
    evidence: float | None = Field(
        default=None, description="採譜の音声根拠（0..1。大きいほど確実に鳴っている）"
    )
    tone: float | None = Field(
        default=None,
        description="ギター音色モデルとの一致度（0..1。小さいほど無関係な音の可能性）",
    )
    frame: str | None = Field(
        default=None,
        description="ブリッジ側の弦の確認用フレーム画像（frames/ 内のファイル名）",
    )


class ChordEvent(_ContractBase):
    """1つのコード（バッキング）"""

    start: float
    end: float
    label: str
    shape: list[ShapeNote]
    muted: list[int] | None = Field(
        default=None,
        description="音声確認で鳴っていない（ミュート）と判定して除いた弦番号",
    )
    frame: str | None = Field(
        default=None,
        description="ブリッジ側の弦の確認用フレーム画像（frames/ 内のファイル名）",
    )


class AnalysisMeta(_ContractBase):
    title: str
    duration: float
    tempo: float
    mode: Mode
    tuning: str | None = None
    separated: bool | None = Field(
        default=None, description="Demucsによるギター音源分離を使った場合 true"
    )
    video_frames: int | None = Field(
        default=None, description="切り出した映像フレームの枚数（0/未定義なら映像なし）"
    )
    tone_dropped: int | None = Field(
        default=None,
        description="ギター音色モデル（6弦1F〜1弦22Fの学習）で無関係な音と判定して除いたノート数",
    )
    source_job: str | None = Field(
        default=None, description="磨き上げ元ジョブID（フレーム引き継ぎ用）"
    )
    generated: str | None = None
    media_file: str | None = Field(
        default=None,
        description="ブラウザ再生用に保存された元メディア（ファイル入力時のみ）",
    )


class AnalysisResult(_ContractBase):
    """API が返す解析結果（analysis.json と同じ構造 + id）"""

    id: str
    meta: AnalysisMeta
    notes: list[NoteEvent]
    chords: list[ChordEvent]
    beats: list[float]
    barlines: list[float]
