"""ノート列 → 弦/フレット割当（手ポジション移動最小化の動的計画法）

複数本指で同時に鳴っているノート（開始時刻がほぼ同じグループ）は、
重複しない弦の組み合わせとしてまとめて割り当てる。
"""
import itertools

import numpy as np

# 6弦(低音E)→1弦(高音E) の開放弦MIDI。index 0 = 6弦
TUNING_MIDI = [40, 45, 50, 55, 59, 64]
MAX_FRET = 22

# 同時発音とみなす開始時刻の誤差（秒）
GROUP_TOL = 0.05


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


def _group_events(notes):
    """開始時刻がほぼ同じノートを1イベント（同時発音）にまとめる"""
    notes = sorted(notes, key=lambda n: (n["start"], n["midi"]))
    events = []
    for n in notes:
        if events and n["start"] - events[-1][0]["start"] <= GROUP_TOL:
            events[-1].append(n)
        else:
            events.append([n])
    return events


def _event_placements(group):
    """同時発音グループの割当候補: [(コスト, ((弦index, フレット), ...)), ...]"""
    cands_list = [candidates(n["midi"]) for n in group]
    if any(not c for c in cands_list):
        return []
    out = []
    for combo in itertools.product(*cands_list):
        strings = [c[0] for c in combo]
        if len(set(strings)) != len(strings):
            continue  # 同じ弦は同時に弾けない
        cost = sum(_note_cost(*c) for c in combo)
        # 押さえ方の広がり（弦の間隔とフレットの開きが大きいと不利）
        span_s = max(strings) - min(strings)
        frets = [c[1] for c in combo]
        span_f = max(frets) - min(frets)
        if span_s >= 4 and span_f >= 5:
            cost += 0.4
        elif span_s >= 3 and span_f >= 7:
            cost += 0.3
        # 低音側の音が高音弦にならない（自然な運指）
        order = sorted(range(len(combo)), key=lambda i: (group[i]["midi"], -strings[i]))
        for a, b in zip(order[:-1], order[1:]):
            if strings[a] > strings[b]:
                cost += 0.3
                break
        out.append((cost, combo))
    out.sort(key=lambda x: x[0])
    # 状態数の爆発を防ぐ（良い候補上位に絞る）
    return out[:48]


def _place_trans(p1, p2) -> float:
    """2つの割当（同時発音グループ）間の移動コスト"""
    f1 = float(np.mean([f for _, f in p1])) if p1 else 0.0
    f2 = float(np.mean([f for _, f in p2])) if p2 else 0.0
    s1 = float(np.mean([s for s, _ in p1])) if p1 else 0.0
    s2 = float(np.mean([s for s, _ in p2])) if p2 else 0.0
    d = abs(f2 - f1)
    cost = (0.15 if (f1 == 0 or f2 == 0) else 0.35) * d
    if d > 7:
        cost += 0.3 * (d - 7)
    if abs(s2 - s1) > 0.5:
        cost += 0.3
    return cost


def assign_frets(notes):
    """
    notes: [{"start","end","midi"}] に "string"(6..1, 6=低音E) と "fret" を付与して返す。
    開始時刻がほぼ同じノートは同時発音として、重複しない弦にまとめて割り当てる。
    ギター音域外のノートは除去する。
    """
    events = _group_events([n for n in notes if candidates(n["midi"])])
    if not events:
        return []

    placements = [_event_placements(g) for g in events]
    events = [g for g, p in zip(events, placements) if p]
    placements = [p for p in placements if p]
    if not events:
        return []

    n = len(events)
    inf = float("inf")
    dp: list = [dict() for _ in range(n)]
    prev: list = [dict() for _ in range(n)]
    for j, (cost, combo) in enumerate(placements[0]):
        dp[0][j] = cost

    for i in range(1, n):
        for j, (cost, combo) in enumerate(placements[i]):
            best, arg = inf, None
            for pj, pcost in dp[i - 1].items():
                t = pcost + _place_trans(placements[i - 1][pj][1], combo)
                if t < best:
                    best, arg = t, pj
            if arg is not None:
                dp[i][j] = best + cost
                prev[i][j] = arg

    if not dp[-1]:
        return [n for g in events for n in g]

    j = min(dp[-1], key=dp[-1].get)
    seq = [j]
    for i in range(n - 1, 0, -1):
        j = prev[i][j]
        seq.append(j)
    seq.reverse()

    out = []
    for i, group in enumerate(events):
        _cost, combo = placements[i][seq[i]]
        for note, (s, f) in zip(group, combo):
            note["string"] = 6 - s  # 表記は 6弦=6 / 1弦=1
            note["fret"] = int(f)
            out.append(note)
    return sorted(out, key=lambda x: (x["start"], x["midi"]))
