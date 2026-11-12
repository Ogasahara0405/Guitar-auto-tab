"""Guitar Auto Tab - ローカルWebアプリ (FastAPI)"""
import asyncio
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core import pipeline


def _open_browser_when_ready() -> None:
    """サーバーの応答を確認してからブラウザを開く（起動直後の接続拒否を防ぐ）"""
    url = f"http://127.0.0.1:{os.environ.get('GAT_PORT', '8000')}"
    for _ in range(120):
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=0.5) as res:
                if res.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    webbrowser.open(url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("GAT_OPEN_BROWSER") == "1":
        threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    yield


app = FastAPI(title="Guitar Auto Tab", lifespan=lifespan)

# フロントエンド（React + TypeScript）のビルド成果物を配信する
STATIC_DIR = Path(__file__).resolve().parent / "static" / "dist"
if not STATIC_DIR.is_dir():
    raise RuntimeError(
        f"フロントエンドがビルドされていません（{STATIC_DIR} がありません）。"
        "frontend/ ディレクトリで `npm install` と `npm run build` を実行してください。"
    )
JOB_ID_RE = re.compile(r"^[0-9a-f]{8}$")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def api_analyze(
    mode: str = Form("melody"),
    chord_style: str = Form("chord"),
    url: str = Form(""),
    file: UploadFile | None = File(None),
):
    url = (url or "").strip()
    if not url and file is None:
        raise HTTPException(400, "YouTube URL またはファイルを指定してください")
    try:
        if file is not None:
            suffix = Path(file.filename or "audio").suffix or ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_path = tmp.name
            result = await asyncio.to_thread(
                pipeline.analyze,
                tmp_path,
                mode=mode,
                chord_style=chord_style,
                is_url=False,
                title=Path(file.filename or "audio").stem,
                keep_original=tmp_path,
            )
        else:
            result = await asyncio.to_thread(
                pipeline.analyze, url, mode=mode, chord_style=chord_style, is_url=True
            )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(500, f"解析に失敗しました: {e}")


@app.post("/api/import")
async def api_import(file: UploadFile = File(...)):
    """Claude Codeで磨いた analysis.json の取り込み"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        result = await asyncio.to_thread(pipeline.import_analysis, tmp_path)
    except Exception as e:
        raise HTTPException(400, f"JSONの取り込みに失敗しました: {e}")
    return JSONResponse(result)


def _job_dir(jid: str) -> Path:
    if not JOB_ID_RE.match(jid):
        raise HTTPException(404, "ジョブが見つかりません")
    d = pipeline.OUTPUT_DIR / jid
    if not d.is_dir():
        raise HTTPException(404, "ジョブが見つかりません")
    return d


@app.get("/api/jobs/{jid}/tab.pdf")
def job_pdf(jid: str):
    p = _job_dir(jid) / "tab.pdf"
    if not p.exists():
        raise HTTPException(404, "PDFがありません")
    return FileResponse(p, media_type="application/pdf", filename="guitar_tab.pdf")


@app.get("/api/jobs/{jid}/tab.txt")
def job_txt(jid: str):
    p = _job_dir(jid) / "tab.txt"
    if not p.exists():
        raise HTTPException(404, "TXTがありません")
    return FileResponse(p, media_type="text/plain; charset=utf-8", filename="guitar_tab.txt")


@app.get("/api/jobs/{jid}/analysis.json")
def job_json(jid: str):
    p = _job_dir(jid) / "analysis.json"
    if not p.exists():
        raise HTTPException(404, "JSONがありません")
    return FileResponse(
        p, media_type="application/json; charset=utf-8", filename="analysis.json"
    )


@app.get("/api/jobs/{jid}/frames/{name}")
def job_frame(jid: str, name: str):
    """映像フレーム（ブリッジ側の弦の確認用）"""
    from app.core.video import FRAME_RE

    if not FRAME_RE.match(name):
        raise HTTPException(404, "フレームがありません")
    p = _job_dir(jid) / "frames" / name
    if not p.exists():
        raise HTTPException(404, "フレームがありません")
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/jobs/{jid}/media")
def job_media(jid: str):
    d = _job_dir(jid)
    meta_file = None
    import json

    data = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    meta_file = data.get("meta", {}).get("media_file")
    if not meta_file:
        raise HTTPException(404, "メディアがありません")
    p = d / meta_file
    if not p.exists():
        raise HTTPException(404, "メディアがありません")
    return FileResponse(p)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
