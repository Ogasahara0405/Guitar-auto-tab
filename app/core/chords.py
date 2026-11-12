"""コード(バッキング)の採譜: 音声 → コードタイムライン"""
import numpy as np
import librosa

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
