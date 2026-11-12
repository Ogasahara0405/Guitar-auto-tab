"""ノート列 → 弦/フレット割当（手ポジション移動最小化の動的計画法）"""
import numpy as np

# 6弦(低音E)→1弦(高音E) の開放弦MIDI。index 0 = 6弦
TUNING_MIDI = [40, 45, 50, 55, 59, 64]
MAX_FRET = 22


def candidates(midi: int, max_fret: int = MAX_FRET):
    """その音高を弾ける (弦index 0..5, フレット) の候補一覧"""
    cands = []
    for s, open_m in enumerate(TUNING_MIDI):
        f = midi - open_m
        if 0 <= f <= max_fret:
            cands.append((s, f))
    return cands


def _note_cost(s: int, f: int) -> float:
    c = 0.0
    if f == 0:
        c -= 0.4  # 開放弦は押さえなくてよい
    if f > 15:
        c += 0.25 * (f - 15)  # ハイポジションはやや不利
    return c


def _trans_cost(a: tuple, b: tuple) -> float:
    s1, f1 = a
    s2, f2 = b
    d = abs(f2 - f1)
    pos = (0.15 if (f1 == 0 or f2 == 0) else 0.35) * d
    if d > 7:
        pos += 0.3 * (d - 7)  # 大きなポジションジャンプにペナルティ
    string = 0.0 if s1 == s2 else 0.3
    return pos + string


def assign_frets(notes):
    """
    notes: [{"start","end","midi"}] に "string"(6..1, 6=低音E) と "fret" を付与して返す。
    ギター音域外のノートは除去する。
    """
    notes = [n for n in notes if candidates(n["midi"])]
    if not notes:
        return []

    cands_list = [candidates(n["midi"]) for n in notes]
    n = len(notes)
    inf = float("inf")

    dp: list = [dict() for _ in range(n)]
    prev: list = [dict() for _ in range(n)]
    for c in cands_list[0]:
        dp[0][c] = _note_cost(*c)

    for i in range(1, n):
        for c in cands_list[i]:
            best, arg = inf, None
            for pc, cost in dp[i - 1].items():
                t = cost + _trans_cost(pc, c)
                if t < best:
                    best, arg = t, pc
            if arg is not None:
                dp[i][c] = best + _note_cost(*c)
                prev[i][c] = arg

    if not dp[-1]:
        return notes

    c = min(dp[-1], key=dp[-1].get)
    seq = [c]
    for i in range(n - 1, 0, -1):
        c = prev[i][c]
        seq.append(c)
    seq.reverse()

    for note, (s, f) in zip(notes, seq):
        note["string"] = 6 - s  # 表記は 6弦=6 / 1弦=1
        note["fret"] = int(f)
    return notes
