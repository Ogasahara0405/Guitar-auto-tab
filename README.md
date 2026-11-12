# Guitar Auto Tab 🎸

YouTube・音声/動画ファイルから**ギタータブ譜を自動生成**するローカルWebアプリ。
個人利用・完全無料（有料API・課金トークン一切なし）。採譜エンジンは無料OSS（librosa等）で動作します。

## 機能

- **メロディモード（単音弾き・リードパート）**: 単音フレーズを採譜し、6弦×フレットのタブ譜へ自動変換（手ポジション移動を最小化する動的計画法）
- **複数本指・同時発音に対応**: ダブルストップ・オクターブ・小コードなど複数弦を同時に弾く部分を最大3声まで検出。開始時刻が揃ったノートは**弦が重ならない組み合わせ**としてタブにまとめて配置されます
- **コードモード（バッキングパート）**: コード進行を検出し、**コード / パワーコード**の出力形式を選択可能
- **ミュートの音声確認**: 全弦を押さえているように見えても実際に鳴っていない弦（ミュート）は、倍音の残差判定で**タブ譜から自動的に除きます**（映像だけでなく音声側の根拠を必ず確認）
- **映像フレームリンク（ブリッジ側の確認用）**: ノート位置の映像フレームを自動抽出し、再生中に表示。どの弦を弾いているかをブリッジ側の映像で照合できます
- **音源分離（Demucs・無料OSS）**: ミックスからギター成分だけを自動抽出して採譜。バックの原曲（ボーカル・ベース・ドラム）による誤検出を大幅に抑制（使用時はタイトルに「音源分離: ON」と表示）
- **動画と同期して確認**: YouTube動画や動画ファイルを再生しながら、タブ譜に現在位置カーソルが追従（現在の弦行もハイライト）
- **保存**: タブ譜を **PDF / TXT（ASCIIタブ）/ analysis.json** として保存
- **Claude Code連携（採譜の磨き上げ）**: analysis.json を書き出し → Claude Code に渡して採譜を修正 → 取り込みで反映

## 必要なもの

- Windows（macOS/Linuxも可、要調整）
- Python 3.12（`winget install Python.Python.3.12` で導入可）
- ffmpeg は不要（pip の `imageio-ffmpeg` 同梱バイナリを使用）
- Node.js LTS — **フロントエンドのビルド/改造時のみ**（ビルド済みUIが `app/static/dist/` にあれば不要）

## セットアップ

```powershell
cd Guitar-auto-tab
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

フロントエンド（React + TypeScript）を改造する場合、または `app/static/dist/` が無い場合:

```powershell
cd frontend
npm install
npm run build   # 成果物を app/static/dist/ に出力
```

### （推奨）音源分離 Demucs の導入 — 採譜精度が大きく向上します

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install demucs
```

初回の解析時に学習済みモデル（約330MB）が自動ダウンロードされます（すべて無料・外部API不使用）。
未導入でも動作します（その場合は元音声のまま解析し、精度は下がります）。

## 起動

```powershell
run.bat
```

または:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

**サーバーの起動完了を確認してから**ブラウザが自動で開きます（`run.bat` 経由の場合）。手動起動時は <http://127.0.0.1:8000> を開いてください。

フロントエンド開発時はビルド不要の開発サーバーも使えます（APIは8000へプロキシ）:

```powershell
cd frontend
npm run dev     # http://127.0.0.1:5173
```

## 使い方

1. **出力したいパート**を選択（メロディ / コード）。コードのときは**コード / パワーコード**も選択
2. **YouTube URL** を貼るか、**音声/動画ファイル**を選択
3. **解析開始**（30秒〜数分。曲の長さ次第）
4. 再生しながらタブ譜を確認（カーソルが追従）
5. **PDF保存 / TXT保存** で書き出し

### Claude Code で採譜を磨く（個人利用フロー）

完全自動の結果に誤りがある場合の手順:

1. **analysis.json書き出し** でデータを保存
2. Claude Code にファイルを渡して修正を依頼（例: 「`output/xxxx/analysis.json` の採譜を確認して、不自然なノート分割とポジション選択を直して」）
3. 修正後のJSONを **磨き上げJSONを取り込み** で読み込み → 表示・PDF/TXT保存に反映

元の解析で映像フレームが抽出されている場合（`output/xxxx/frames/`）、取り込み後も各ノートの `"frame"` から同じフレーム画像を参照できます。どの弦を弾いているかの確認にはこのフレーム（ブリッジ側の見え方）を、ミュートの有無は音声の根拠を併せて確認してください。

## 動作テスト

```powershell
.\.venv\Scripts\python.exe tests\test_pipeline.py
```

既知のメロディ/コード/同時発音（ダブルストップ・オクターブ）/ミュート付きコードを合成して、採譜→タブ変換→フレーム抽出→PDF出力→JSON連携までを検証します。

## 構成

```
app/
  main.py            # FastAPI（Web API + フロントエンド配信）
  core/              # 採譜エンジン（Python・DSP系）
    audio.py         # ffmpeg変換 / yt-dlp によるYouTube音声取得
    video.py         # 映像フレーム抽出（ノート位置 ↔ ブリッジ側映像のリンク）
    sep.py           # 音源分離（Demucs: ミックスからギター成分を抽出）
    melody.py        # メロディ採譜（pyin + 多声音検出: ダブルストップ等・音での確認付き）
    chords.py        # コード認識（CQTクロマ + テンプレート照合）+ ミュート弦の音声確認
    tabassign.py     # ノート→弦/フレット割当（DP・同時発音は弦の重複なしで割当）
    voicing.py       # コード→押さえ方（開放/バレエ/パワーコード）
    grid.py          # タブ譜のグリッド配置計算
    render.py        # ASCIIタブ出力
    pdf.py           # PDF出力（reportlab・日本語対応）
    pipeline.py      # 解析パイプライン統括
  static/dist/       # フロントエンドのビルド成果物
frontend/            # フロントエンド（React + TypeScript / Vite）
  src/
    App.tsx          # 状態管理・画面構成
    api.ts           # 型付きAPIクライアント
    types.ts         # analysis.json の型定義
    components/      # プレイヤー / タブ譜SVG / フレームリンク / フォーム類
output/<id>/         # 解析結果（analysis.json / tab.txt / tab.pdf / frames/）
```

技術の使い分け: **採譜エンジン（数値計算・DSP）は Python**（librosa 等の生態系）、**UI（動画同期プレイヤー・タブ譜描画）は React + TypeScript**。

## 制限・既知の課題

- チューニングは**標準（EADGBE）**固定（キャポ・変則対応は今後）
- フルミックスの曲でも音源分離（Demucs）でギター成分を抽出してから採譜するため誤検出は大幅に減っていますが、バックの原曲に同じフレーズのギターが大きく入っている場合は影響を受けることがあります。分離のため解析に数十秒（曲長・CPUに依存）が加算されます
- YouTubeの音声取得は個人利用を前提とした機能です（公開サービス化する場合は規約・権利の確認が必要）
- 拍子は4/4前提で小節線を描画（テンポ検出に依存）
