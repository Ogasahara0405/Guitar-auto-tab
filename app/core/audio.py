"""音声の読み込み・変換・YouTubeダウンロード"""
import os
import shutil
import subprocess

SR = 22050


def get_ffmpeg_exe() -> str:
    """システムのffmpeg、なければimageio-ffmpeg同梱バイナリを使う"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def ensure_wav(src: str, dst: str, sr: int = SR) -> str:
    """任意の音声/動画ファイルを mono wav に変換してパスを返す"""
    ff = get_ffmpeg_exe()
    cmd = [ff, "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(sr), dst]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"ffmpeg変換に失敗しました: {res.stderr[-500:]}")
    return dst


def download_youtube(url: str, outdir: str):
    """yt-dlpでYouTubeの音声を取得し、(wavパス, タイトル)を返す"""
    import yt_dlp

    os.makedirs(outdir, exist_ok=True)
    ff = get_ffmpeg_exe()
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(outdir, "source_dl.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": os.path.dirname(ff),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav"}
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    title = info.get("title") or "youtube_audio"
    wav = os.path.join(outdir, "source_dl.wav")
    if not os.path.exists(wav):
        raise RuntimeError("YouTube音声の取得結果(wav)が見つかりません")
    return wav, title


def load_audio(path: str, sr: int = SR):
    """wavを読み込み (波形, sr) を返す"""
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True)
    return y, sr
