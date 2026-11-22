"""音声の読み込み・変換・YouTubeダウンロード"""
import os
import shutil
import subprocess
import time

SR = 22050


def get_ffmpeg_exe() -> str:
    """システムのffmpeg、なければimageio-ffmpeg同梱バイナリを使う"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def ensure_wav(src: str, dst: str, sr: int = SR, channels: int = 1) -> str:
    """任意の音声/動画ファイルを wav に変換してパスを返す（デフォルト: mono 22050Hz）"""
    ff = get_ffmpeg_exe()
    cmd = [ff, "-y", "-i", src, "-vn", "-ac", str(channels), "-ar", str(sr), dst]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"ffmpeg変換に失敗しました: {res.stderr[-500:]}")
    return dst


def download_youtube(url: str, outdir: str):
    """yt-dlpでYouTubeの音声/映像を取得し、(wavパス, タイトル, 取得元ファイル)を返す

    映像+音声は同梱ffmpeg（imageio-ffmpeg）でマージして取得する。
    現代のYouTubeには480p以下の「映像+音声の単一ファイル」が無く、
    単一ファイル指定だと音声のみに落ちて映像機能（フレームリンク・
    映像ゲート）が動かなくなるため、まず分離ストリームのマージを試す。
    映像付きで取得できる場合は動画も保持し、ブリッジ側の弦の確認用に
    ノート位置のフレームを切り出せるようにする（取得できない場合は音声のみ）。
    YouTube側の一時的な403（レート制限・PO Token等）に備え、
    再試行ごとに再生クライアントを切り替える。
    """
    import yt_dlp

    os.makedirs(outdir, exist_ok=True)
    # 403回避のフォールバック順: 既定 → android_vr → tv → mweb
    client_cycle = [None, "android_vr", "tv", "mweb"]
    info = None
    dl_path = ""
    last_err = ""
    for i, client in enumerate(client_cycle):
        if i:
            time.sleep(3.0)
        opts = {
            # 映像(≤480p)+音声のマージ → 単一ファイル(≤480p) → 映像(任意)+音声のマージ → 音声のみ
            # （480p以下の映像が無い動画でも、映像は無くさない）
            "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/bestaudio/best",
            "outtmpl": os.path.join(outdir, "source_dl.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            # 進捗表示（[download] X%）は stdout に改行なしで出力され、
            # CLI契約のJSONと同一行に混ざるため必ず抑止する
            "noprogress": True,
            "noplaylist": True,
            # マージ（+video+audio）に使うffmpeg（同梱バイナリ。システムffmpeg不要）
            "ffmpeg_location": get_ffmpeg_exe(),
        }
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                dl_path = ydl.prepare_filename(info)
            break
        except Exception as e:
            last_err = str(e)
    if info is None:
        raise RuntimeError(
            "YouTube音声の取得に失敗しました（"
            + last_err
            + "）。アクセスが一時的に制限されている可能性があるため、"
            "少し待って再試行するか、音声/動画ファイルを直接アップロードしてください。"
        )
    title = info.get("title") or "youtube_audio"
    if not os.path.exists(dl_path):
        raise RuntimeError("YouTube音声の取得結果が見つかりません")
    wav = os.path.join(outdir, "source_dl.wav")
    if os.path.abspath(dl_path) != os.path.abspath(wav):
        ensure_wav(dl_path, wav)
    return wav, title, dl_path


def load_audio(path: str, sr: int = SR):
    """wavを読み込み (波形, sr) を返す"""
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True)
    return y, sr
