"""ノート列 → 弦/フレット割当（手ポジション移動最小化の動的計画法）

複数本指で同時に鳴っているノート（開始時刻がほぼ同じグループ）は、
重複しない弦の組み合わせとしてまとめて割り当てる。
同時に鳴らせるのは1手で押さえられる範囲のみ＝開放弦を除くフレット開きは
MAX_FRET_SPAN 以内（例: 8Fを押さえるなら5〜11Fの間で、最大値−最小値が3まで）。
この条件を満たす押さえ方しか候補に残さず、物理的に押さえられない同時発音
（誤検出の疑い）は根拠の弱い声から除く。
ブリッジ側映像のピッキング位置（弦レーン）や、指板の黒丸マーカー
から推定したフレット位置の手がかりがあれば、映像に忠実な割当を
優先する（音声から自然に決まる割当と大きく矛盾する場合のみ音声側を採る）。
"""
import itertools

import numpy as np

# 6弦(低音E)→1弦(高音E) の開放弦MIDI。index 0 = 6弦
TUNING_MIDI = [40, 45, 50, 55, 59, 64]
MAX_FRET = 22

# 同時発音とみなす開始時刻の誤差（秒）
GROUP_TOL = 0.05

# 同時にならせる弦のフレット開きの上限（開放弦は指を使わないので数えない）
# 1手のポジション（指1〜4本）で押さえられる幅。例: 8Fを押さえるとき
# 同時に鳴らせるのは5〜11Fの間で、最大値−最小値が3になる場合まで
MAX_FRET_SPAN = 3

# 映像の弦位置に沿う割当を許すコスト差（手がかり1つあたり）
LANE_SLACK = 1.5
# レーン間隔と弦間節のずれの重み（映像仮説の選択用）
LANE_SPACING_W = 0.4
# 映像のフレット位置推定（指板の黒丸マーカー）を許容する誤差（フレット数）
FRET_TOL = 2
# フレット位置に沿う割当を許すコスト差（手がかり1つあたり）
# マーカー検出は物理配置で検証済みのため、大きなポジション移動が
# 音声側のDPコストに跳ねても映像のフレット位置を優先できる余裕を取る
FRET_SLACK = 3.5


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


def _fretted_span(combo) -> float:
    """押さえるフレット（開放弦を除く）の開き。開放弦だけ/単音なら0"""
    fretted = [f for _, f in combo if f > 0]
    return (max(fretted) - min(fretted)) if len(fretted) >= 2 else 0.0


def _playable_together(midis) -> bool:
    """この音の組を1手で同時に押さえられるか（弦の重複なし＋開き3以内）"""
    cands_list = [candidates(int(m)) for m in midis]
    if any(not c for c in cands_list):
        return False
    for combo in itertools.product(*cands_list):
        strings = [c[0] for c in combo]
        if len(set(strings)) != len(strings):
            continue
        if _fretted_span(combo) <= MAX_FRET_SPAN:
            return True
    return False


def _trim_to_playable(group):
    """1手で押さえられない同時発音は、根拠の弱い声から除く

    開放弦以外のフレット開きが MAX_FRET_SPAN を超える同時発音は
    物理的に同時に鳴らせない（=誤検出の疑い）ため、弱い声から除いて
    押さえられる組み合わせに収める。除く順は (evidence 昇順, 高い音優先)。
    """
    g = list(group)
    while len(g) > 1 and not _playable_together([n["midi"] for n in g]):
        weakest = min(
            range(len(g)),
            key=lambda i: (g[i].get("evidence", 1.0), -g[i]["midi"]),
        )
        g.pop(weakest)
    return g


def _event_placements(group, restrict=None, fret_pref=None):
    """同時発音グループの割当候補: [(コスト, ((弦index, フレット), ...)), ...]

    restrict: 各ノートの弦index固定（None=自由）。映像の弦位置に沿わせるため。
    fret_pref: 各ノートのフレット推定（None=自由）。指板の黒丸マーカー由来。
    """
    cands_list = []
    for i, n in enumerate(group):
        c = candidates(n["midi"])
        if restrict is not None and restrict[i] is not None:
            c = [x for x in c if x[0] == restrict[i]]
        if fret_pref is not None and fret_pref[i] is not None:
            c = [x for x in c if abs(x[1] - fret_pref[i]) <= FRET_TOL]
        cands_list.append(c)
    if any(not c for c in cands_list):
        return []
    out, over = [], []
    for combo in itertools.product(*cands_list):
        strings = [c[0] for c in combo]
        if len(set(strings)) != len(strings):
            continue  # 同じ弦は同時に弾けない
        cost = sum(_note_cost(*c) for c in combo)
        # 押さえ方の広がり（弦の間隔とフレットの開きが大きいと不利）
        span_s = max(strings) - min(strings)
        span_f = _fretted_span(combo)  # 開放弦は指を使わないので開きに数えない
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
        row = (cost, combo)
        if span_f <= MAX_FRET_SPAN:
            out.append(row)   # 1手のポジションで押さえられる
        else:
            over.append(row)  # 開きすぎ（押さえ方が無い場合の保険）
    if not out:
        out = over  # 3フレット以内の押さえ方が無い同時発音（安全側）
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


def _solve(events, restrict=None, fret_pref=None):
    """DPで割当を解く。戻り値 (総コスト, 割当済みノート)。割当不能なら None"""
    placements = []
    for i, g in enumerate(events):
        r = restrict[i] if restrict is not None else None
        f = fret_pref[i] if fret_pref is not None else None
        p = _event_placements(g, r, f)
        if not p:
            return None
        placements.append(p)

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
        return None

    total = float(min(dp[-1].values()))
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
            # 仮説の比較中に元ノートを汚さないよう複製に割り当てる
            assigned = dict(note)
            assigned["string"] = 6 - s  # 表記は 6弦=6 / 1弦=1
            assigned["fret"] = int(f)
            out.append(assigned)
    return total, sorted(out, key=lambda x: (x["start"], x["midi"]))


def _lane_restrictions(events, lane_hints):
    """映像の弦レーンから「どの弦を弾いたか」の仮説を作る（上から順の並びは保つ）

    レーンの並びと弦の並びは同じ向きに並ぶはずだが、どちらが1弦側かは
    映像だけでは決められないため、両向きの仮説を間隔の自然さ順に返す。
    """
    hinted = []
    for i, g in enumerate(events):
        if len(g) != 1:
            continue  # 同時発音は複数弦にまたがるためレーンの解釈が曖昧
        h = lane_hints.get(round(float(g[0]["start"]), 3))
        if h:
            r, k = int(h[0]), int(h[1])
            if 0 <= r < k and k >= 2:
                hinted.append((i, r, k))
    ranks = sorted({r for _, r, _ in hinted})
    if len(ranks) < 2:
        return []
    k_max = max(k for _, _, k in hinted)

    out = []
    for flip in (False, True):
        for combo in itertools.combinations(range(6), len(ranks)):
            strings = list(reversed(combo)) if flip else list(combo)
            # レーン間隔と弦間隔が揃う仮説を優先（映像の並びを忠実に再現）
            mismatch = 0.0
            for a in range(len(ranks) - 1):
                dr = (ranks[a + 1] - ranks[a]) / max(k_max - 1, 1) * 5.0
                ds = strings[a + 1] - strings[a]
                mismatch += abs(ds - dr)
            restrict = [[None] * len(g) for g in events]
            for i, r, _k in hinted:
                restrict[i][0] = strings[ranks.index(r)]
            out.append((LANE_SPACING_W * mismatch, restrict))
    out.sort(key=lambda x: x[0])
    return [r for _m, r in out]


def _fret_preferences(events, fret_hints):
    """fret_hints（{開始時刻: フレット推定}）をイベント内のノート順のリストに変換"""
    if not fret_hints:
        return None
    out = []
    any_hint = False
    for g in events:
        row = []
        for n in g:
            h = fret_hints.get(round(float(n["start"]), 3))
            fe = float(h) if h is not None else None
            row.append(fe)
            if fe is not None:
                any_hint = True
        out.append(row)
    return out if any_hint else None


def assign_frets(notes, lane_hints=None, fret_hints=None):
    """
    notes: [{"start","end","midi"}] に "string"(6..1, 6=低音E) と "fret" を付与して返す。
    開始時刻がほぼ同じノートは同時発音として、重複しない弦にまとめて割り当てる。
    同時発音は開放弦以外のフレット開きが MAX_FRET_SPAN 以内（1手で押さえられる
    範囲）の割当に限定し、それを満たさない同時発音は根拠の弱い声から除く。
    ギター音域外のノートは除去する。

    lane_hints: {開始時刻(秒): (映像の弦レーン 0..K-1, レーン数K)} を渡すと、
    ブリッジ側映像のピッキング位置に沿う弦割当を優先する（映像に忠実なタブ）。
    fret_hints: {開始時刻(秒): フレット番号} を渡すと、指板の黒丸マーカーから
    推定したフレット位置（±FRET_TOL）に沿う割当を優先する。
    音声から自然に決まる割当と大きく矛盾する場合は音声側を採る（安全側）。
    """
    events = _group_events([n for n in notes if candidates(n["midi"])])
    if not events:
        return []
    # 1手で押さえられない同時発音（誤検出の疑い）は弱い声から除く
    events = [_trim_to_playable(g) for g in events]

    best = _solve(events, None)
    if best is None:
        return [n for g in events for n in g]

    fret_pref = _fret_preferences(events, fret_hints)

    def try_hyps(hyps, pref):
        """映像の仮説を受け入れる（音声の自然な割当 + 許容コスト以内のみ）"""
        nonlocal best
        for restrict in hyps:
            cand = _solve(events, restrict, pref)
            if cand is None:
                continue
            n_lane = (
                sum(1 for ev in restrict for x in ev if x is not None) if restrict else 0
            )
            n_fret = (
                sum(1 for ev in pref for x in ev if x is not None) if pref else 0
            )
            slack = LANE_SLACK * n_lane + FRET_SLACK * n_fret
            if cand[0] <= best[0] + slack:
                best = cand  # 最も整合的な映像の仮説を採用
                return True
        return False

    if lane_hints:
        hyps = _lane_restrictions(events, lane_hints)
        # まず映像の弦位置＋フレット位置の両方で試し、合わなければ弦位置のみ
        for pref in ((fret_pref, None) if fret_pref else (None,)):
            if try_hyps(hyps, pref):
                break
            if pref is not fret_pref:
                break
    elif fret_pref:
        try_hyps([None], fret_pref)

    return best[1]
