"""映像フレーム抽出: ノート位置の映像フレームを切り出し、タブ譜とリンクする

どの弦を弾いているかは映像のブリッジ側から確認できるため、
採譜した各ノートの開始時刻に合わせてフレーム画像を保存する。
analysis.json の各ノート/コードに "frame"（ファイル名）を付与することで、
- プレイヤーで再生時にその瞬間の映像を並べて確認できる
- Claude Code の採譜磨き上げフローでフレーム画像を確認できる
（ミュートの有無は音声側の根拠と併せて確認する: ノートは鳴っている音のみ採譜される）
"""
import os
import re
import subprocess

from . import audio

FRAME_RE = re.compile(r"^frame_[0-9]+\.[0-9]+\.jpg$")

# 同一視するフレーム間隔（この範囲のイベントは同じフレームを参照）
FRAME_DUP_SEC = 0.25
MAX_FRAMES = 400


def has_video(path: str) -> bool:
    """ファイルに映像ストリームが含まれるか（ffprobe不要・ffmpegの出力から判定）"""
    if not path or not os.path.exists(path):
        return False
    try:
        ff = audio.get_ffmpeg_exe()
        res = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True)
        return bool(re.search(r"^\s*Stream #.*Video:", res.stderr, re.MULTILINE))
    except Exception:
        return False


def extract_frames(src: str, times, outdir: str, max_frames: int = MAX_FRAMES) -> dict:
    """指定時刻（秒）のフレームをJPEGで切り出す。

    戻り値: {時刻(秒, 小数2桁): ファイル名}。映像が無い/失敗時は {}。
    フレーム数が max_frames を超える場合は等間隔に間引く。
    """
    if not has_video(src):
        return {}
    os.makedirs(outdir, exist_ok=True)
    ff = audio.get_ffmpeg_exe()

    uniq = sorted({round(float(t), 2) for t in times if t is not None and float(t) >= 0})
    if not uniq:
        return {}
    # 近接する時刻は同じフレームにまとめる
    picked = []
    for t in uniq:
        if not picked or t - picked[-1] >= FRAME_DUP_SEC:
            picked.append(t)
    uniq = picked
    if len(uniq) > max_frames:
        step = len(uniq) / max_frames
        uniq = sorted({uniq[int(i * step)] for i in range(max_frames)})

    out = {}
    for t in uniq:
        name = f"frame_{t:07.2f}.jpg"
        dst = os.path.join(outdir, name)
        if not os.path.exists(dst):
            cmd = [
                ff, "-y", "-ss", f"{t:.3f}", "-i", src,
                "-frames:v", "1", "-q:v", "4", "-vf", "scale='min(1280,iw)':-2",
                dst,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not os.path.exists(dst):
                continue
        out[round(t, 2)] = name
    return out


def frame_for(frames: dict, t: float, tol: float = 0.35) -> str | None:
    """時刻 t に対応するフレーム名を返す（無ければ None）"""
    if not frames:
        return None
    key = round(float(t), 2)
    if key in frames:
        return frames[key]
    best, best_d = None, None
    for k, name in frames.items():
        d = abs(k - t)
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = name, d
    return best
