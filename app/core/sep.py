"""音源分離（Demucs）: ミックスからギター成分を取り出す

Demucs(htdemucs_6s・無料OSS)で6成分（drums/bass/vocals/guitar/piano/other）に
分離し、guitarステムを採譜に使う。バックの原曲（ボーカル・ベース等）による
誤検出を防ぐ。torch/demucs未導入・分離失敗時はNoneを返し、
呼び出し側は元音声で処理を続行する（完全無料・外部API不使用）。
"""
import os

from . import audio

SAMPLERATE = 44100


def demucs_available() -> bool:
    try:
        import demucs.api  # noqa: F401
        import torch  # noqa: F401

        return True
    except Exception:
        return False


def separate_guitar(src: str, outdir: str) -> str | None:
    """src（音声/動画ファイル）からギター成分を分離し、wavパスを返す。失敗時None"""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        import soundfile as sf
        import torch
        from demucs.api import Separator
    except Exception:
        return None

    os.makedirs(outdir, exist_ok=True)
    try:
        # Demucsは44.1kHzステレオを想定（同梱ffmpegでデコード）
        src44 = os.path.join(outdir, "sep_input.wav")
        audio.ensure_wav(src, src44, sr=SAMPLERATE, channels=2)
        data, _ = sf.read(src44, dtype="float32")
        wav = torch.from_numpy(data.T.copy())  # [channels, samples]
        sep = Separator(model="htdemucs_6s", device="cpu", progress=False)
        _, stems = sep.separate_tensor(wav)
        out = os.path.join(outdir, "guitar_stem.wav")
        sf.write(out, stems["guitar"].numpy().T, int(sep.samplerate))
    except Exception:
        return None
    return out if os.path.exists(out) else None
