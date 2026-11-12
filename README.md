# Guitar Auto Tab 🎸

YouTube・音声/動画ファイルから**ギタータブ譜を自動生成**するローカルWebアプリ。
個人利用・完全無料（有料API・課金トークン一切なし）。採譜エンジンは無料OSS（librosa等）で動作します。

## 機能

- **メロディモード（単音弾き・リードパート）**: 単音フレーズを採譜し、6弦×フレットのタブ譜へ自動変換（手ポジション移動を最小化する動的計画法）
- **コードモード（バッキングパート）**: コード進行を検出し、**コード / パワーコード**の出力形式を選択可能
- **動画と同期して確認**: YouTube動画や動画ファイルを再生しながら、タブ譜に現在位置カーソルが追従
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

## 動作テスト

```powershell
.\.venv\Scripts\python.exe tests\test_pipeline.py
```

既知のメロディ/コードを合成して、採譜→タブ変換→PDF出力→JSON連携までを検証します。

## 構成

```
app/
  main.py            # FastAPI（Web API + フロントエンド配信）
  core/              # 採譜エンジン（Python・DSP系）
    audio.py         # ffmpeg変換 / yt-dlp によるYouTube音声取得
    melody.py        # 単音採譜（pyin + セグメント整形）
    chords.py        # コード認識（CQTクロマ + テンプレート照合 + 平滑化）
    tabassign.py     # ノート→弦/フレット割当（DP・ポジション最適化）
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
    components/      # プレイヤー / タブ譜SVG / フォーム類
output/<id>/         # 解析結果（analysis.json / tab.txt / tab.pdf）
```

技術の使い分け: **採譜エンジン（数値計算・DSP）は Python**（librosa 等の生態系）、**UI（動画同期プレイヤー・タブ譜描画）は React + TypeScript**。

## 制限・既知の課題

- チューニングは**標準（EADGBE）**固定（キャポ・変則対応は今後）
- 歪んだギター・分厚いミックスは精度が下がる（音源分離（Demucs）の追加を予定）
- YouTubeの音声取得は個人利用を前提とした機能です（公開サービス化する場合は規約・権利の確認が必要）
- 拍子は4/4前提で小節線を描画（テンポ検出に依存）
