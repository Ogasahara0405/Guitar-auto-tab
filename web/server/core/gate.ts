/**
 * 映像（演奏動作データ）に忠実なノート/コードの選別
 *
 * 旧: app/core/video.py の gate_notes / gate_chords / _lane_ranks / fret_at を移植。
 * ワーカーが計算した play データ（動きの包絡線・動作イベント・ネック横位置・
 * フレット座標）を使い、以下を決める:
 * - 映像で演奏動作が確認できない位置のノートは除去する（関係ない音を出さない）
 * - 単弦ピッキングの映像に3声以上が乗った場合は弱い声を2声までに絞る
 * - 単弦ピッキングの弦位置（レーン）をタブ割当の手がかりとして返す
 * - 指板の黒丸マーカーから「何フレットを弾いているか」の手がかりも返す
 */
import { round3 } from "../../shared/events";
import type { PlayData, PlayEvent, PerceptionChord, PerceptionNote, FretMap } from "../../shared/schema";
import type { FretHints, LaneHints } from "./tabassign";

const SUPPORT_WIN = 0.2; // ノート位置の映像を確認する窓（±秒）
const SUPPORT_RATIO = 0.12; // 「演奏動作あり」とみなす動きの強度（映像内のp90比）
const EVENT_MIN_DIST = 0.15; // 動作イベント間の最小間隔（秒）
const NARROW_UNITS = 1.2; // 縦の広がりが弦1本分のこの倍未満なら「単弦ピッキング」
// 動作解析フレームの幅（worker/video.py の MOTION_W と一致させる）
const MOTION_W = 320;

/** 指板座標（fmap.w 基準の x ピクセル）をフレット番号に変換する */
export function fretAt(x: number, fmap: FretMap): number | null {
  const { a, b } = fmap;
  if (b === 0) return null;
  const r = (x - a) / b;
  if (!(0.0 < r && r < 0.75)) return null;
  const n = -12.0 * Math.log2(1.0 - r);
  if (!(0.0 <= n && n <= 22.0)) return null;
  return Math.round(n);
}

/** 単弦ピッキングイベントの縦位置を弦レーン（0..K-1、画面上で上から順）に束ねる */
function laneRanks(events: PlayEvent[]): Map<number, readonly [number, number]> {
  const narrow = events.filter((ev) => (ev.units ?? 99.0) < NARROW_UNITS * 2 && Number.isFinite(ev.y));
  if (narrow.length < 2) return new Map();
  const ys = narrow.map((ev) => ev.y as number).sort((a, b) => a - b);
  const span = ys[ys.length - 1] - ys[0];
  const merge = Math.max(span / 10.0, 2.0);
  const clusters: number[][] = [[ys[0]]];
  for (const y of ys.slice(1)) {
    if (y - clusters[clusters.length - 1][clusters[clusters.length - 1].length - 1] <= merge) {
      clusters[clusters.length - 1].push(y);
    } else {
      clusters.push([y]);
    }
  }
  if (clusters.length < 2) return new Map();
  const centers = clusters.map((c) => c.reduce((a, b) => a + b, 0) / c.length);

  const out = new Map<number, readonly [number, number]>();
  for (const ev of events) {
    if ((ev.units ?? 99.0) >= NARROW_UNITS) continue;
    const y = ev.y;
    if (y == null || !Number.isFinite(y)) continue;
    let j = 0;
    let bestD = Math.abs(y - centers[0]);
    for (let k = 1; k < centers.length; k++) {
      const d = Math.abs(y - centers[k]);
      if (d < bestD) {
        bestD = d;
        j = k;
      }
    }
    if (bestD <= merge * 1.5) out.set(round3(ev.t), [j, centers.length]);
  }
  return out;
}

/** play データ上で時刻 t に演奏動作が確認できるか */
function makeSupported(play: PlayData): (t: number) => boolean {
  const times = play.times;
  const energy = play.energy;
  const thr = SUPPORT_RATIO * play.p90;
  return (t: number) => {
    let maxE = -Infinity;
    for (let i = 0; i < times.length; i++) {
      if (times[i] >= t - SUPPORT_WIN && times[i] <= t + SUPPORT_WIN) {
        if (energy[i] > maxE) maxE = energy[i];
      }
    }
    return maxE >= thr;
  };
}

export interface GateNotesResult {
  notes: PerceptionNote[];
  dropped: number;
  laneHints: LaneHints;
  fretHints: FretHints;
}

/** 映像（演奏動作）に忠実にノートを選別する（旧 video.gate_notes） */
export function gateNotes(notes: PerceptionNote[], play: PlayData | null): GateNotesResult {
  const empty: GateNotesResult = {
    notes: [...notes],
    dropped: 0,
    laneHints: new Map(),
    fretHints: new Map(),
  };
  if (!notes.length) return { ...empty, notes: [] };
  // 映像から動作の情報が得られない（静止画等）場合は音声の結果をそのまま使う
  if (!play || play.p90 <= 0) return empty;

  const supported = makeSupported(play);
  const events = play.events ?? [];
  const ranks = laneRanks(events);

  const kept = notes.filter((n) => supported(n.start));
  let dropped = notes.length - kept.length;

  // 動作イベントごとにノートをまとめ、単弦ピッキングなら2声までに絞る
  const byEvent = new Map<number, PerceptionNote[]>();
  const loose: PerceptionNote[] = [];
  for (const n of kept) {
    let hit: PlayEvent | null = null;
    for (const ev of events) {
      if (Math.abs(ev.t - n.start) <= EVENT_MIN_DIST) {
        if (hit === null || Math.abs(ev.t - n.start) < Math.abs(hit.t - n.start)) hit = ev;
      }
    }
    if (hit !== null && (hit.units ?? 99.0) < NARROW_UNITS) {
      const key = round3(hit.t);
      const g = byEvent.get(key);
      if (g) g.push(n);
      else byEvent.set(key, [n]);
    } else {
      loose.push(n);
    }
  }

  const final: PerceptionNote[] = [...loose];
  for (const group of byEvent.values()) {
    if (group.length <= 2) {
      final.push(...group);
    } else {
      // 映像で単弦を弾いているのに声が多い → 音声の根拠が弱い声を落とす
      group.sort((a, b) => (b.evidence ?? 1) - (a.evidence ?? 1) || a.start - b.start);
      final.push(...group.slice(0, 2));
      dropped += group.length - 2;
    }
  }

  // 単弦ピッキングの弦位置（レーン）をタブ割当の手がかりに
  const laneHints: LaneHints = new Map();
  for (const [evKey, group] of byEvent) {
    if (group.length !== 1) continue;
    const h = ranks.get(evKey);
    if (h) laneHints.set(round3(group[0].start), h);
  }

  // 指板の黒丸マーカーから「何フレットを弾いているか」の手がかりに
  const fretHints: FretHints = new Map();
  const fmap = play.fret_map;
  if (fmap && play.neck_xs.length === play.times.length) {
    // neck_xs は動作解析フレーム（幅MOTION_W）基準 → マーカー座標系へ揃える
    const kx = fmap.w / MOTION_W;
    for (const n of final) {
      const vals: number[] = [];
      for (let i = 0; i < play.times.length; i++) {
        const t = play.times[i];
        const nx = play.neck_xs[i];
        if (t >= n.start - 0.25 && t <= n.start + 0.15 && nx != null && Number.isFinite(nx)) {
          vals.push(nx);
        }
      }
      if (vals.length >= 2) {
        vals.sort((a, b) => a - b);
        const mid = vals.length >> 1;
        const median = vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2;
        const fe = fretAt(median * kx, fmap);
        if (fe != null) fretHints.set(round3(n.start), fe);
      }
    }
  }

  final.sort((a, b) => a.start - b.start || a.midi - b.midi);
  return { notes: final, dropped, laneHints, fretHints };
}

export interface GateChordsResult {
  chords: PerceptionChord[];
  dropped: number;
}

/** 映像（演奏動作）に忠実にコードを選別する（ストラムが見えない区間は出さない） */
export function gateChords(chords: PerceptionChord[], play: PlayData | null): GateChordsResult {
  if (!chords.length) return { chords: [], dropped: 0 };
  if (!play || play.p90 <= 0) return { chords: [...chords], dropped: 0 };
  const supported = makeSupported(play);
  const kept = chords.filter((c) => supported(c.start));
  return { chords: kept, dropped: chords.length - kept.length };
}
