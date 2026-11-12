"""コード(バッキング)の採譜: 音声 → コードタイムライン

ミュート確認（音での確認）: 全弦を弾いているように見える押さえ方でも、
軽く触れて鳴らしていない弦（ミュート）がある場合は音声側に根拠が立たない。
filter_muted が各弦の実際の鳴りを倍音の過剰（他弦の倍音予測に対する残差）で
判定し、鳴っていない弦をタブ譜から除く。
"""
import numpy as np
import librosa

from .tabassign import TUNING_MIDI

PITCH = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_QUALITY_SUFFIX = {"maj": "", "min": "m", "7": "7", "m7": "m7"}
_QUALITY_INTERVALS = {
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "7": [0, 4, 7, 10],
    "m7": [0, 3, 7, 10],
}


def _templates():
    """(ラベル一覧, テンプレート行列(K,12)) を返す"""
    labels, vecs = [], []
    for q, ivs in _QUALITY_INTERVALS.items():
        for root in range(12):
            v = np.zeros(12)
            for iv in ivs:
                v[(root + iv) % 12] = 1.0
            v /= np.linalg.norm(v)
            labels.append(PITCH[root] + _QUALITY_SUFFIX[q])
            vecs.append(v)
    return labels, np.stack(vecs)


def extract_chords(y: np.ndarray, sr: int, hop_length: int = 512):
    """
    戻り値: {"tempo": BPM, "chords": [{"start","end","label"}, ...]}
    label は "Am" / "E7" など、判定不能区間は "N.C."
    """
    if y.size == 0:
        return {"tempo": 120.0, "chords": []}

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    times = librosa.times_like(chroma, sr=sr, hop_length=hop_length)
    duration = float(len(y) / sr)

    tempo_arr, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    tempo = float(np.atleast_1d(tempo_arr)[0]) or 120.0
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop_length)

    # ビート位置で区切る（少なすぎる場合は固定幅フォールバック）
    if len(beat_times) >= 4:
        edges = list(beat_times)
    else:
        edges = list(np.arange(0.0, duration, 0.5))
    edges = [e for e in edges if e < duration]
    if not edges or edges[0] > 0.25:
        edges = [0.0] + edges
    edges.append(duration)

    # 小さな区間は前の区間へ併合
    merged = [edges[0]]
    for e in edges[1:]:
        if e - merged[-1] < 0.22:
            continue
        merged.append(e)
    if merged[-1] < duration:
        merged.append(duration)
    edges = merged

    labels, T = _templates()
    seg_labels = []
    for a, b in zip(edges[:-1], edges[1:]):
        mask = (times >= a) & (times < b)
        if not mask.any():
            seg_labels.append("N.C.")
            continue
        c = chroma[:, mask].mean(axis=1)
        nrm = np.linalg.norm(c)
        if nrm < 1e-6:
            seg_labels.append("N.C.")
            continue
        c = c / nrm
        sims = T @ c
        k = int(np.argmax(sims))
        seg_labels.append(labels[k] if sims[k] >= 0.55 else "N.C.")

    # 孤立した1区間のラベルを両隣の共通ラベルで埋める（平滑化）
    smoothed = list(seg_labels)
    for i in range(1, len(seg_labels) - 1):
        if (
            seg_labels[i] != seg_labels[i - 1]
            and seg_labels[i - 1] == seg_labels[i + 1]
            and seg_labels[i - 1] != "N.C."
        ):
            smoothed[i] = seg_labels[i - 1]

    # 連続する同ラベルをまとめてタイムライン化
    chords = []
    for i, lab in enumerate(smoothed):
        a, b = float(edges[i]), float(edges[i + 1])
        if chords and chords[-1]["label"] == lab:
            chords[-1]["end"] = round(b, 3)
        else:
            chords.append({"start": round(a, 3), "end": round(b, 3), "label": lab})
    return {"tempo": tempo, "chords": chords}


# ---- ミュート確認（音での確認） ----

_N_FFT_MUTE = 4096


def _spec_peak(S: np.ndarray, f: float, sr: int, n_fft: int) -> float:
    b = int(round(f * n_fft / sr))
    lo, hi = max(1, b - 2), min(len(S) - 1, b + 2)
    return float(S[lo: hi + 1].max()) if hi >= lo else 0.0


def _string_freq(string_no: int, fret: int) -> float:
    """弦番号(6..1)とフレットから実音の周波数"""
    midi = TUNING_MIDI[6 - string_no] + int(fret)
    return 440.0 * 2.0 ** ((midi - 69) / 12)


def _harmonic_model(amps, f_target: float, f0: float) -> float:
    """他弦の倍音系列モデルによる f_target への混入予測

    amps: その弦の1..4倍音の実測強度。減衰比は幾何平均で推定し、
    実測値そのもの（＝他の弦の基本音と衝突している可能性がある）は使わない。
    """
    if amps[0] <= 1e-9:
        return 0.0
    ratio = (amps[2] / amps[0]) ** 0.5 if amps[2] > 1e-9 else 0.45
    # 実測値は他の弦の基本音と衝突して膨らむことがあるため、ギターらしい減衰比に留める
    ratio = min(max(ratio, 0.2), 0.55)
    k = f_target / f0
    ki = round(k)
    if ki < 1 or ki > 6 or abs(k - ki) > 0.04 * ki:
        return 0.0
    return float(amps[0] * ratio ** (ki - 1))


def filter_muted(y: np.ndarray, sr: int, t0: float, t1: float, shape: list):
    """押さえ方の各弦が「実際に鳴っているか」を音声で確認し、
    ミュート（鳴っていない）弦を除いたshapeと、除いた弦番号を返す。

    判定は各弦の基本音・2倍音の「他弦の倍音系列モデルに対する残差」で行う
    （オクターブ上の弦が他弦の倍音と衝突するケースでも誤判定しにくい）。
    音声の根拠が弱すぎる場合は変更せずそのまま返す。
    """
    if not shape or y.size == 0:
        return list(shape), []
    i0, i1 = int(t0 * sr), int(t1 * sr)
    seg = y[i0: i1] if i1 > i0 else np.zeros(1, dtype=y.dtype)
    if seg.size < int(0.05 * sr):
        return list(shape), []

    S = np.abs(librosa.stft(seg, n_fft=_N_FFT_MUTE, hop_length=256))
    S_seg = np.median(S, axis=1)

    freqs = [_string_freq(st["string"], st["fret"]) for st in shape]
    amps = [[_spec_peak(S_seg, f * k, sr, _N_FFT_MUTE) for k in range(1, 5)] for f in freqs]

    strengths = []
    for i, f in enumerate(freqs):
        excess1 = amps[i][0]
        excess2 = amps[i][1]
        for j, fj in enumerate(freqs):
            if i == j:
                continue
            excess1 -= _harmonic_model(amps[j], f, fj)
            excess2 -= _harmonic_model(amps[j], 2 * f, fj)
        strengths.append(max(excess1, 0.5 * excess2, 0.0))

    mx = max(strengths) if strengths else 0.0
    if mx <= 1e-9:
        return list(shape), []

    sounding = [st for st, s in zip(shape, strengths) if s >= 0.12 * mx]
    muted = [st["string"] for st, s in zip(shape, strengths) if s < 0.12 * mx]
    if len(sounding) < 2:
        # 音声側の根拠が弱い（短すぎる・減衰しすぎ等）場合は元の押さえ方を維持
        return list(shape), []
    return sounding, muted
