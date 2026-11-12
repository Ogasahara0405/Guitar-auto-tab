"""単音メロディの採譜: 音声 → ノートイベント抽出"""
import numpy as np
import librosa


def _nan_median_filter(x: np.ndarray, size: int = 5) -> np.ndarray:
    """NaNを無視する移動中央値フィルタ（ビブラート・ジッタ平滑化用）"""
    n = len(x)
    half = size // 2
    out = np.full(n, np.nan)
    for i in range(n):
        w = x[max(0, i - half): min(n, i + half + 1)]
        w = w[~np.isnan(w)]
        if len(w):
            out[i] = float(np.median(w))
    return out


def extract_notes(y: np.ndarray, sr: int, hop_length: int = 256):
    """
    音声からノートイベント列を抽出する。
    戻り値: [{"start": 秒, "end": 秒, "midi": MIDIノート番号}, ...]

    処理の流れ:
      1. pyin でF0追跡 → 中央値平滑化 → 半音量子化
      2. ピッチ連続性と無音ギャップでセグメント化
         （セグメントの切れ目理由 "pitch"/"gap" を記録）
      3. 極小セグメント除去 → 同一音高の隣接セグメントを
         継続ノートとして結合（アタック時の一時的なピッチ誤差対策）
      4. 強いオンセットでのみ同音の再ピッキングを分割
    """
    if y.size == 0:
        return []

    f0, voiced, _ = librosa.pyin(
        y, fmin=70.0, fmax=1100.0, sr=sr, hop_length=hop_length
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)
    frame_dur = hop_length / sr

    with np.errstate(divide="ignore", invalid="ignore"):
        midi = 69.0 + 12.0 * np.log2(f0 / 440.0)
    midi = np.where(np.isnan(midi), np.nan, midi)
    midi_q = np.round(_nan_median_filter(midi, size=5))

    # --- Stage 1: セグメント化 ---
    gap_frames = max(1, int(round(0.06 / frame_dur)))
    raw = []
    cur = None
    gap = 0

    def close(end_t: float, reason: str):
        nonlocal cur
        if cur is not None:
            cur["end"] = float(end_t)
            cur["closed_by"] = reason
            raw.append(cur)
            cur = None

    for i, t in enumerate(times):
        m = midi_q[i]
        if np.isnan(m):
            gap += 1
            if cur is not None and gap >= gap_frames:
                close(cur["last"] + frame_dur / 2, "gap")
            continue
        gap = 0
        if cur is None:
            cur = {
                "start": max(0.0, t - frame_dur / 2),
                "midi": int(m),
                "last": t,
            }
        elif int(m) == cur["midi"]:
            cur["last"] = t
        else:
            boundary = (cur["last"] + t) / 2
            close(boundary, "pitch")
            cur = {"start": boundary, "midi": int(m), "last": t}
    if cur is not None:
        close(cur["last"] + frame_dur / 2, "end")

    # --- Stage 2: 極小セグメント（アタック瞬間の誤検出）を除去 ---
    kept = [s for s in raw if s["end"] - s["start"] >= 0.04]

    # --- Stage 3: 同一音高の隣接セグメント結合 ---
    # ピッチ誤差で分断された継続ノートのみ結合し、
    # 無音ギャップで切れた同音の連打はノートを分離したまま維持する
    merged = []
    for seg in kept:
        if merged and seg["midi"] == merged[-1]["midi"] and merged[-1]["closed_by"] != "gap":
            merged[-1]["end"] = seg["end"]
            merged[-1]["closed_by"] = seg["closed_by"]
        else:
            merged.append(dict(seg))

    # --- Stage 4: 再ピッキング分割（同音の連打） ---
    # オンセット位置に加えて「エネルギーの深い落ち込み（ディップ）」が
    # ある場合のみ分割する。アタック時の誤検出や減衰中の分裂を防ぐ。
    onsets = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=hop_length, units="time",
        backtrack=True, delta=0.2, wait=int(0.1 / frame_dur),
    )
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=hop_length)

    def rms_max(t0: float, t1: float) -> float:
        m = (rms_times >= t0) & (rms_times < t1)
        return float(rms[m].max()) if m.any() else 0.0

    out = []
    for seg in merged:
        dur = seg["end"] - seg["start"]
        splits = []
        if dur >= 0.3:
            for o in onsets:
                if not (seg["start"] + 0.1 < o < seg["end"] - 0.1):
                    continue
                # 分割点はその付近のRMS最小点
                w0, w1 = max(seg["start"], o - 0.05), min(seg["end"], o + 0.08)
                m = (rms_times >= w0) & (rms_times < w1)
                if not m.any():
                    continue
                idx = int(np.argmin(rms[m]))
                dip_t = float(rms_times[m][idx])
                r_dip = float(rms[m][idx])
                r_prev = rms_max(dip_t - 0.25, dip_t - 0.05)
                r_next = rms_max(dip_t + 0.02, dip_t + 0.15)
                if (
                    r_dip < 0.5 * r_prev
                    and r_dip < 0.5 * r_next
                    and dip_t - seg["start"] >= 0.08
                    and seg["end"] - dip_t >= 0.08
                ):
                    splits.append(dip_t)
        if splits:
            pts = [seg["start"]] + sorted(splits) + [seg["end"]]
            for a, b in zip(pts[:-1], pts[1:]):
                if b - a >= 0.06:
                    out.append({"start": round(float(a), 3), "end": round(float(b), 3), "midi": seg["midi"]})
        else:
            out.append(
                {"start": round(seg["start"], 3), "end": round(seg["end"], 3), "midi": seg["midi"]}
            )
    return out
