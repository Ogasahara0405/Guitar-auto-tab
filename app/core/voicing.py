"""コードラベル → ギターの押さえ方(ボイシング)。表記は6弦→1弦の順。None=ミュート

押さえ方は1手で押さえられる範囲（開放弦を除くフレット開きが
tabassign.MAX_FRET_SPAN 以内）のものだけを候補とする。
"""

from .tabassign import MAX_FRET_SPAN

# 開放コードの定型フォーム { (ルート音名, クオリティ): [6弦..1弦] }
_OPEN_SHAPES = {
    ("E", "maj"): [0, 2, 2, 1, 0, 0],
    ("E", "min"): [0, 2, 2, 0, 0, 0],
    ("E", "7"): [0, 2, 0, 1, 0, 0],
    ("A", "maj"): [None, 0, 2, 2, 2, 0],
    ("A", "min"): [None, 0, 2, 2, 1, 0],
    ("A", "7"): [None, 0, 2, 0, 2, 0],
    ("A", "m7"): [None, 0, 2, 0, 1, 0],
    ("D", "maj"): [None, None, 0, 2, 3, 2],
    ("D", "min"): [None, None, 0, 2, 3, 1],
    ("D", "7"): [None, None, 0, 2, 1, 2],
    ("C", "maj"): [None, 3, 2, 0, 1, 0],
    ("C", "7"): [None, 3, 2, 3, 1, 0],
    ("G", "maj"): [3, 2, 0, 0, 0, 3],
    ("G", "7"): [3, 2, 0, 0, 0, 1],
    ("G", "min"): [3, 5, 5, 3, 3, 3],
}

_PITCH_TO_PC = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}
_QUALITY_PARSE = [("", "maj"), ("m7", "m7"), ("7", "7"), ("m", "min")]

# 開放弦MIDI（6弦→1弦）
_OPEN_MIDI = [40, 45, 50, 55, 59, 64]


def parse_label(label: str):
    """"Am" / "C#7" → (root音名, クオリティキー)。失敗時は (None, None)"""
    if not label or label == "N.C.":
        return None, None
    root = label[:2] if len(label) >= 2 and label[1] == "#" else label[:1]
    if root not in _PITCH_TO_PC:
        return None, None
    suffix = label[len(root):]
    for suf, qual in _QUALITY_PARSE:
        if suffix == suf:
            return root, qual
    return root, "maj"


def _shape_pos(shape):
    frets = [f for f in shape if f is not None and f > 0]
    return float(np_mean(frets)) if frets else 0.0


def np_mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _hand_ok(shape) -> bool:
    """開放弦を除くフレット開きが MAX_FRET_SPAN 以内（1手で押さえられる）か"""
    fretted = [f for f in shape if f is not None and f > 0]
    return not fretted or max(fretted) - min(fretted) <= MAX_FRET_SPAN


def _power_candidates(root: str):
    """パワーコード候補: [(ポジション, shape)]"""
    pc = _PITCH_TO_PC[root]
    out = []
    f6 = (pc - 40) % 12  # 6弦ルート
    f5 = (pc - 45) % 12  # 5弦ルート
    for base, fret in ((0, f6), (0, f6 + 12), (1, f5), (1, f5 + 12)):
        if fret > 15:
            continue
        shape = [None] * 6
        if base == 0:
            shape[0], shape[1], shape[2] = fret, fret + 2, fret + 2
        else:
            shape[1], shape[2], shape[3] = fret, fret + 2, fret + 2
        out.append((fret, shape))
    return out


def _full_candidates(root: str, qual: str):
    """そのコードの押さえ方候補: [(ポジション, shape)]"""
    out = []
    key = (root, qual)
    if key in _OPEN_SHAPES:
        out.append((0.0, list(_OPEN_SHAPES[key])))

    pc = _PITCH_TO_PC[root]
    f6 = (pc - 40) % 12
    f5 = (pc - 45) % 12

    # Eフォーム・バレエコード（6弦ルート）
    if 1 <= f6 <= 12:
        f = f6
        if qual == "maj":
            s = [f, f + 2, f + 2, f + 1, f, f]
        elif qual == "min":
            s = [f, f + 2, f + 2, f, f, f]
        elif qual == "7":
            s = [f, f + 2, f, f + 1, f, f]
        else:  # m7 はマイナーシェイプで代用（MVP）
            s = [f, f + 2, f + 2, f, f, f]
        out.append((float(f), s))

    # Aフォーム・バレエコード（5弦ルート）
    if 1 <= f5 <= 12:
        f = f5
        if qual == "maj":
            s = [None, f, f + 2, f + 2, f + 2, f]
        elif qual == "min":
            s = [None, f, f + 2, f + 2, f + 1, f]
        elif qual == "7":
            s = [None, f, f + 2, f, f + 2, f]
        else:
            s = [None, f, f + 2, f + 2, f + 1, f]
        out.append((float(f), s))
    return out


def shape_for(label: str, chord_style: str, last_pos: float):
    """
    コードラベルから押さえ方を決める。
    chord_style: "chord"(フルコード) / "power"(パワーコード)
    戻り値: [{"string": 6..1, "fret": int}, ...]（ミュート弦は含めない）/ None
    """
    root, qual = parse_label(label)
    if root is None:
        return None
    if chord_style == "power":
        cands = _power_candidates(root)
    else:
        cands = _full_candidates(root, qual) or _power_candidates(root)
    # 1手で押さえられない押さえ方は候補から外す（無い場合は安全側で残す）
    ok = [c for c in cands if _hand_ok(c[1])]
    if ok:
        cands = ok
    if not cands:
        return None

    pos, shape = min(cands, key=lambda c: abs(c[0] - last_pos))
    out = [
        {"string": 6 - i, "fret": int(f)}
        for i, f in enumerate(shape)
        if f is not None
    ]
    return {"shape": out, "pos": float(pos)}
