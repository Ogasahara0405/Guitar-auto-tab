/**
 * ノート列 → 弦/フレット割当（手ポジション移動最小化の動的計画法）
 *
 * 旧: app/core/tabassign.py を移植。
 * 複数本指で同時に鳴っているノート（開始時刻がほぼ同じグループ）は、
 * 重複しない弦の組み合わせとしてまとめて割り当てる。
 * 同時に鳴らせるのは1手で押さえられる範囲のみ＝開放弦を除くフレット開きは
 * MAX_FRET_SPAN 以内。この条件を満たす押さえ方しか候補に残さず、
 * 物理的に押さえられない同時発音（誤検出の疑い）は根拠の弱い声から除く。
 * 映像の弦レーン・フレット位置の手がかりがあれば、映像に忠実な割当を優先。
 */
import { groupByStart, round3 } from "../../shared/events";

// 6弦(低音E)→1弦(高音E) の開放弦MIDI。index 0 = 6弦
export const TUNING_MIDI = [40, 45, 50, 55, 59, 64];
export const MAX_FRET = 22;

// 同時にならせる弦のフレット開きの上限（開放弦は指を使わないので数えない）
export const MAX_FRET_SPAN = 3;

// 映像の弦位置に沿う割当を許すコスト差（手がかり1つあたり）
const LANE_SLACK = 1.5;
// レーン間隔と弦間節のずれの重み（映像仮説の選択用）
const LANE_SPACING_W = 0.4;
// 映像のフレット位置推定を許容する誤差（フレット数）
const FRET_TOL = 2;
// フレット位置に沿う割当を許すコスト差（手がかり1つあたり）
const FRET_SLACK = 3.5;

export interface RawNote {
  start: number;
  end: number;
  midi: number;
  evidence?: number | null;
  [k: string]: unknown;
}

/** 割当済みノート（string: 6=低音E … 1=高音e） */
export interface TabNote extends RawNote {
  string?: number;
  fret?: number;
}

/** (弦index 0..5, フレット)。index 0 = 6弦 */
export type Placement = readonly [number, number];

/** 映像の弦レーン手がかり: 開始時刻キー → (レーン 0..K-1, レーン数K) */
export type LaneHints = Map<number, readonly [number, number]>;
/** 指板マーカーのフレット手がかり: 開始時刻キー → フレット番号 */
export type FretHints = Map<number, number>;

/** その音高を弾ける (弦index, フレット) の候補一覧 */
export function candidates(midi: number, maxFret = MAX_FRET): Placement[] {
  const cands: Placement[] = [];
  for (let s = 0; s < TUNING_MIDI.length; s++) {
    const f = midi - TUNING_MIDI[s];
    if (0 <= f && f <= maxFret) cands.push([s, f] as const);
  }
  return cands;
}

function noteCost(s: number, f: number): number {
  let c = 0.0;
  if (f === 0) c -= 0.4; // 開放弦は押さえなくてよい
  if (f > 15) c += 0.25 * (f - 15); // ハイポジションはやや不利
  return c;
}

/** 押さえるフレット（開放弦を除く）の開き。開放弦だけ/単音なら0 */
function frettedSpan(combo: Placement[]): number {
  const fretted = combo.map(([, f]) => f).filter((f) => f > 0);
  return fretted.length >= 2 ? Math.max(...fretted) - Math.min(...fretted) : 0.0;
}

/** この音の組を1手で同時に押さえられるか（弦の重複なし＋開き3以内） */
function playableTogether(midis: number[]): boolean {
  const candsList = midis.map((m) => candidates(Math.round(m)));
  if (candsList.some((c) => c.length === 0)) return false;
  for (const combo of product(candsList)) {
    const strings = combo.map(([s]) => s);
    if (new Set(strings).size !== strings.length) continue;
    if (frettedSpan(combo) <= MAX_FRET_SPAN) return true;
  }
  return false;
}

/** 1手で押さえられない同時発音は、根拠の弱い声から除く */
function trimToPlayable<T extends RawNote>(group: T[]): T[] {
  const g = [...group];
  while (g.length > 1 && !playableTogether(g.map((n) => n.midi))) {
    let weakest = 0;
    for (let i = 1; i < g.length; i++) {
      const a = g[i].evidence ?? 1.0;
      const b = g[weakest].evidence ?? 1.0;
      if (a < b || (a === b && g[i].midi > g[weakest].midi)) weakest = i;
    }
    g.splice(weakest, 1);
  }
  return g;
}

/** 直積（itertools.product） */
function product<T>(lists: T[][]): T[][] {
  let out: T[][] = [[]];
  for (const list of lists) {
    const next: T[][] = [];
    for (const prefix of out) for (const item of list) next.push([...prefix, item]);
    out = next;
  }
  return out;
}

/** n個からk個の組み合わせ（itertools.combinations） */
function combinations(n: number, k: number): number[][] {
  const out: number[][] = [];
  const cur: number[] = [];
  const rec = (start: number) => {
    if (cur.length === k) {
      out.push([...cur]);
      return;
    }
    for (let i = start; i < n; i++) {
      cur.push(i);
      rec(i + 1);
      cur.pop();
    }
  };
  rec(0);
  return out;
}

type CostCombo = readonly [number, Placement[]];

/**
 * 同時発音グループの割当候補: [(コスト, combo)] をコスト昇順に最大48件。
 * restrict: 各ノートの弦index固定（null=自由）。fret_pref: 各ノートのフレット推定。
 */
function eventPlacements(
  group: RawNote[],
  restrict?: (number | null)[] | null,
  fretPref?: (number | null)[] | null,
): CostCombo[] {
  const candsList: Placement[][] = [];
  for (let i = 0; i < group.length; i++) {
    let c = candidates(group[i].midi);
    const r = restrict ? restrict[i] : null;
    if (r != null) c = c.filter(([s]) => s === r);
    const f = fretPref ? fretPref[i] : null;
    if (f != null) c = c.filter(([, fret]) => Math.abs(fret - f) <= FRET_TOL);
    candsList.push(c);
  }
  if (candsList.some((c) => c.length === 0)) return [];

  const out: CostCombo[] = [];
  const over: CostCombo[] = [];
  for (const combo of product(candsList)) {
    const strings = combo.map(([s]) => s);
    if (new Set(strings).size !== strings.length) continue; // 同じ弦は同時に弾けない
    let cost = combo.reduce((acc, [s, f]) => acc + noteCost(s, f), 0);
    // 押さえ方の広がり（弦の間隔とフレットの開きが大きいと不利）
    const spanS = Math.max(...strings) - Math.min(...strings);
    const spanF = frettedSpan(combo);
    if (spanS >= 4 && spanF >= 5) cost += 0.4;
    else if (spanS >= 3 && spanF >= 7) cost += 0.3;
    // 低音側の音が高音弦にならない（自然な運指）
    const order = combo
      .map((_, i) => i)
      .sort((a, b) => group[a].midi - group[b].midi || strings[b] - strings[a]);
    for (let k = 0; k + 1 < order.length; k++) {
      if (strings[order[k]] > strings[order[k + 1]]) {
        cost += 0.3;
        break;
      }
    }
    const row: CostCombo = [cost, combo];
    if (spanF <= MAX_FRET_SPAN) out.push(row);
    else over.push(row); // 開きすぎ（押さえ方が無い場合の保険）
  }
  if (!out.length) {
    // 映像の弦/フレット仮説が「人間の手では押さえられない割当」を強制する場合は
    // その仮説を棄却する（不可能な割当で代用しない → 自由な割当にフォールバック）
    return restrict || fretPref ? [] : over;
  }
  const rows = out;
  rows.sort((a, b) => a[0] - b[0]);
  return rows.slice(0, 48);
}

/** 2つの割当（同時発音グループ）間の移動コスト */
function placeTrans(p1: Placement[], p2: Placement[]): number {
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0.0);
  const f1 = mean(p1.map(([, f]) => f));
  const f2 = mean(p2.map(([, f]) => f));
  const s1 = mean(p1.map(([s]) => s));
  const s2 = mean(p2.map(([s]) => s));
  const d = Math.abs(f2 - f1);
  let cost = (f1 === 0 || f2 === 0 ? 0.15 : 0.35) * d;
  if (d > 7) cost += 0.3 * (d - 7);
  if (Math.abs(s2 - s1) > 0.5) cost += 0.3;
  return cost;
}

/** 近接した音どうし（ストラムのずれ等）は、合わせて人間の手の範囲に収まる必要がある */
const NEAR_SIMULTANEOUS = 0.12;

/** ほぼ同時に鳴る2つの割当が、合わせて手の範囲（開き3以内）に収まるか */
function reachPenalty(p1: Placement[], p2: Placement[]): number {
  const combined = [...p1, ...p2];
  const strings = combined.map(([s]) => s);
  if (new Set(strings).size !== strings.length) return 40.0; // 同じ弦の同時押さえは不可能
  const excess = frettedSpan(combined) - MAX_FRET_SPAN;
  return excess > 0 ? 40.0 * excess : 0.0;
}

/** DPで割当を解く。戻り値 (総コスト, 割当済みノート)。割当不能なら null */
function solve(
  events: RawNote[][],
  restrict?: ((number | null)[] | null)[] | null,
  fretPref?: ((number | null)[] | null)[] | null,
): [number, TabNote[]] | null {
  const placements: CostCombo[][] = [];
  for (let i = 0; i < events.length; i++) {
    const r = restrict ? restrict[i] : null;
    const f = fretPref ? fretPref[i] : null;
    const p = eventPlacements(events[i], r, f);
    if (!p.length) return null;
    placements.push(p);
  }

  const n = events.length;
  const inf = Number.POSITIVE_INFINITY;
  const dp: Map<number, number>[] = [];
  const prev: Map<number, number>[] = [];
  for (let i = 0; i < n; i++) {
    dp.push(new Map());
    prev.push(new Map());
  }
  for (let j = 0; j < placements[0].length; j++) dp[0].set(j, placements[0][j][0]);

  for (let i = 1; i < n; i++) {
    // ストラムのずれ等でほぼ同時に鳴る音どうしは、合わせて手の範囲に収める
    const nearSim =
      Math.abs(events[i][0].start - events[i - 1][0].start) <= NEAR_SIMULTANEOUS;
    for (let j = 0; j < placements[i].length; j++) {
      const [cost, combo] = placements[i][j];
      let best = inf;
      let arg: number | null = null;
      for (const [pj, pcost] of dp[i - 1]) {
        const prevCombo = placements[i - 1][pj][1];
        const reach = nearSim ? reachPenalty(prevCombo, combo as Placement[]) : 0.0;
        const t = pcost + placeTrans(prevCombo, combo as Placement[]) + reach;
        if (t < best) {
          best = t;
          arg = pj;
        }
      }
      if (arg !== null) {
        dp[i].set(j, best + cost);
        prev[i].set(j, arg);
      }
    }
  }

  const lastDp = dp[n - 1];
  if (!lastDp.size) return null;
  let j = 0;
  let total = inf;
  for (const [k, v] of lastDp) {
    if (v < total) {
      total = v;
      j = k;
    }
  }
  const seq = [j];
  for (let i = n - 1; i > 0; i--) {
    j = prev[i].get(j)!;
    seq.push(j);
  }
  seq.reverse();

  const out: TabNote[] = [];
  for (let i = 0; i < n; i++) {
    const combo = placements[i][seq[i]][1];
    for (let k = 0; k < events[i].length; k++) {
      const [s, f] = combo[k];
      out.push({ ...events[i][k], string: 6 - s, fret: Math.round(f) });
    }
  }
  out.sort((a, b) => a.start - b.start || a.midi - b.midi);
  return [total, out];
}

/**
 * 映像の弦レーンから「どの弦を弾いたか」の仮説を作る（上から順の並びは保つ）
 * レーンの並びと弦の並びは同じ向きに並ぶはずだが、どちらが1弦側かは
 * 映像だけでは決められないため、両向きの仮説を間隔の自然さ順に返す。
 */
function laneRestrictions(
  events: RawNote[][],
  laneHints: LaneHints,
): ((number | null)[][] | null)[] {
  const hinted: [number, number, number][] = [];
  for (let i = 0; i < events.length; i++) {
    const g = events[i];
    if (g.length !== 1) continue; // 同時発音は複数弦にまたがるためレーンの解釈が曖昧
    const h = laneHints.get(round3(g[0].start));
    if (h) {
      const [r, k] = [Math.round(h[0]), Math.round(h[1])];
      if (0 <= r && r < k && k >= 2) hinted.push([i, r, k]);
    }
  }
  const ranks = [...new Set(hinted.map(([, r]) => r))].sort((a, b) => a - b);
  if (ranks.length < 2) return [];
  const kMax = Math.max(...hinted.map(([, , k]) => k));

  const out: [number, (number | null)[][]][] = [];
  for (const flip of [false, true]) {
    for (const combo of combinations(6, ranks.length)) {
      const strings = flip ? [...combo].reverse() : [...combo];
      // レーン間隔と弦間隔が揃う仮説を優先（映像の並びを忠実に再現）
      let mismatch = 0.0;
      for (let a = 0; a + 1 < ranks.length; a++) {
        const dr = ((ranks[a + 1] - ranks[a]) / Math.max(kMax - 1, 1)) * 5.0;
        const ds = strings[a + 1] - strings[a];
        mismatch += Math.abs(ds - dr);
      }
      const restrict: (number | null)[][] = events.map((g) => g.map(() => null));
      for (const [i, r] of hinted) {
        restrict[i][0] = strings[ranks.indexOf(r)];
      }
      out.push([LANE_SPACING_W * mismatch, restrict]);
    }
  }
  out.sort((a, b) => a[0] - b[0]);
  return out.map(([, r]) => r);
}

/** fret_hints をイベント内のノート順のリストに変換 */
function fretPreferences(
  events: RawNote[][],
  fretHints: FretHints,
): (number | null)[][] | null {
  if (!fretHints.size) return null;
  const out: (number | null)[][] = [];
  let anyHint = false;
  for (const g of events) {
    const row: (number | null)[] = [];
    for (const n of g) {
      const h = fretHints.get(round3(n.start));
      const fe = h == null ? null : Number(h);
      row.push(fe);
      if (fe != null) anyHint = true;
    }
    out.push(row);
  }
  return anyHint ? out : null;
}

/**
 * notes に "string"(6..1, 6=低音E) と "fret" を付与して返す。
 * 開始時刻がほぼ同じノートは同時発音として、重複しない弦にまとめて割り当てる。
 * 同時発音は開放弦以外のフレット開きが MAX_FRET_SPAN 以内の割当に限定し、
 * それを満たさない同時発音は根拠の弱い声から除く。ギター音域外のノートは除去する。
 *
 * laneHints: ブリッジ側映像のピッキング位置（弦レーン）に沿う弦割当を優先。
 * fretHints: 指板の黒丸マーカーから推定したフレット位置（±FRET_TOL）を優先。
 * 音声から自然に決まる割当と大きく矛盾する場合は音声側を採る（安全側）。
 */
export function assignFrets(
  notes: RawNote[],
  laneHints?: LaneHints | null,
  fretHints?: FretHints | null,
): TabNote[] {
  const playable = notes
    .filter((n) => candidates(n.midi).length > 0)
    .sort((a, b) => a.start - b.start || a.midi - b.midi);
  if (!playable.length) return [];
  const events = groupByStart(playable).map((g) => trimToPlayable(g));

  let best = solve(events, null, null);
  if (best === null) return events.flat();

  const fretPref = fretHints ? fretPreferences(events, fretHints) : null;

  /** 映像の仮説を受け入れる（音声の自然な割当 + 許容コスト以内のみ） */
  const tryHyps = (
    hyps: ((number | null)[][] | null)[],
    pref: (number | null)[][] | null,
  ): boolean => {
    for (const restrict of hyps) {
      const cand = solve(events, restrict, pref);
      if (cand === null) continue;
      const nLane = restrict ? restrict.reduce((a, row) => a + row.filter((x) => x != null).length, 0) : 0;
      const nFret = pref ? pref.reduce((a, row) => a + row.filter((x) => x != null).length, 0) : 0;
      const slack = LANE_SLACK * nLane + FRET_SLACK * nFret;
      if (cand[0] <= best![0] + slack) {
        best = cand; // 最も整合的な映像の仮説を採用
        return true;
      }
    }
    return false;
  };

  if (laneHints && laneHints.size) {
    const hyps = laneRestrictions(events, laneHints);
    // まず映像の弦位置＋フレット位置の両方で試し、合わなければ弦位置のみ
    const tries: ((number | null)[][] | null)[] = fretPref ? [fretPref, null] : [null];
    for (const pref of tries) {
      if (tryHyps(hyps, pref)) break;
      if (pref !== fretPref) break;
    }
  } else if (fretPref) {
    tryHyps([null], fretPref);
  }

  return best![1];
}
