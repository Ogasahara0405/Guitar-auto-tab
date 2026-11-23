/**
 * 画面用タブ譜レイアウト（Guitar Pro 風の標準様式）
 *
 * 従来の「曲全体が横1本に伸びる時刻軸」ではなく、
 * 小節単位で折り返した複数段（システム）＋音価ステム/ビームという
 * 一般的なタブ譜の様式で配置する。配置計算は shared/grid.ts の
 * 小節・スロット量子化をそのまま使い、PDF/ASCII出力と整合させる。
 */
import type { AnalysisBody } from "./schema";
import { buildScore, type Score, type ScoreEvent, type Measure } from "./grid";

/** 1スロットの幅（px）。slots_per_beat=2 でも 4 でも同じ実幅になる */
export const SLOT_W = 14;
/** 譜線の間隔（px） */
export const STAFF_GAP = 17;
/** スタッフ上端の余白（px、弦名・コード名用） */
export const TOP_PAD = 56;
/** スタッフ下端の余白（px、ステム/ビーム用） */
export const BOTTOM_PAD = 52;
/** 1段に収める小節数の既定値（幅が足りれば自動で増える） */
export const DEFAULT_MEASURES_PER_SYSTEM = 4;

/** 音価の分類（ステム/フラグの描画に使う） */
export type RhythmValue = "whole" | "half" | "quarter" | "eighth" | "sixteenth" | "thirtysecond";

export interface LayoutEvent {
  /** ソート済みのイベント通し番号（ハイライト用） */
  index: number;
  system: number;
  measure: number;
  /** 段内スロット位置 */
  slot: number;
  /** スタッフ上端を原点とするセル位置 */
  x: number;
  /** フレット数字の行（0=1弦） */
  rows: { row: number; text: string }[];
  label: string | null;
  /** このイベントの開始時刻（カーソル追従の照合用） */
  time: number;
  /** 次のイベントまでの音価 */
  rhythm: RhythmValue;
  /** スロット数で見た長さ（ビーム単位の判定用） */
  slotsLen: number;
  start: number;
  end: number;
}

export interface LayoutSystem {
  index: number;
  measures: { index: number; x: number; width: number; start: number; end: number }[];
  events: LayoutEvent[];
  width: number;
}

export interface TabLayout {
  score: Score;
  systems: LayoutSystem[];
  /** すべてのイベント（時刻順） */
  events: LayoutEvent[];
  /** 小節のスロット数から見た拍子（現状 4/4 表示） */
  timeSignature: string;
  systemHeight: number;
  /** イベントの実時間 → 画面 x 座標（段内。補間はスロット中心間の線形） */
  timeToX(t: number): { system: number; x: number } | null;
}

function measureWidth(m: Measure): number {
  return (m.slots + 2) * SLOT_W;
}

/** 次イベントまでの長さ（スロット）から音価を決める */
export function rhythmOf(slotsLen: number, slotsPerBeat: number): RhythmValue {
  const beats = slotsLen / Math.max(slotsPerBeat, 1);
  if (beats >= 4) return "whole";
  if (beats >= 2) return "half";
  if (beats >= 1) return "quarter";
  if (beats >= 0.5) return "eighth";
  if (beats >= 0.25) return "sixteenth";
  return "thirtysecond";
}

const FLAG_COUNT: Record<RhythmValue, number> = {
  whole: 0,
  half: 0,
  quarter: 0,
  eighth: 1,
  sixteenth: 2,
  thirtysecond: 3,
};

/** 音価のフラグ本数（ビーム描画でも使う） */
export function flagCount(r: RhythmValue): number {
  return FLAG_COUNT[r];
}

/** 連続する音符をビームでつなぐ単位（同じ音価・8分以下・1拍以上まとめて） */
export function beamGroups(events: LayoutEvent[], slotsPerBeat: number): LayoutEvent[][] {
  const groups: LayoutEvent[][] = [];
  let cur: LayoutEvent[] = [];
  const flush = () => {
    if (cur.length >= 2) groups.push(cur);
    cur = [];
  };
  for (const ev of events) {
    const flags = flagCount(ev.rhythm);
    const prev = cur[cur.length - 1];
    const sameValue = prev && flagCount(prev.rhythm) === flags;
    const contiguous = prev && ev.slot === prev.slot + prev.slotsLen && ev.measure === prev.measure;
    const beatBreak = prev && Math.floor(ev.slot / slotsPerBeat) !== Math.floor((prev.slot + prev.slotsLen - 1) / slotsPerBeat);
    if (flags === 0 || !sameValue || !contiguous || beatBreak) {
      flush();
      if (flags > 0) cur = [ev];
      continue;
    }
    cur.push(ev);
  }
  flush();
  return groups;
}

/**
 * 解析結果を標準タブ譜レイアウトに変換する。
 * measuresPerSystem を省略すると containerWidth に収まるだけの小節を並べる。
 */
export function buildTabLayout(
  result: AnalysisBody,
  opts?: { measuresPerSystem?: number; containerWidth?: number },
): TabLayout {
  const score = buildScore(result);
  const measures = score.measures;
  const slotsPerBeat =
    measures.length && result.notes.length
      ? Math.round((measures[0].slots * 60) / ((measures[0].end - measures[0].start) * (result.meta.tempo || 120))) || 2
      : 2;

  // 1段の小節数: 明示指定 or コンテナ幅に収まる数（既定4）
  let perSystem = opts?.measuresPerSystem ?? 0;
  if (!perSystem && opts?.containerWidth) {
    perSystem = Math.max(1, Math.floor((opts.containerWidth - 24) / measureWidth(measures[0])));
    perSystem = Math.min(perSystem, 8);
  }
  if (!perSystem) perSystem = DEFAULT_MEASURES_PER_SYSTEM;

  // イベントを時刻順に（スロット順を保証）
  const sortedEvents = [...score.events].sort(
    (a, b) => measures[a.measure].start - measures[b.measure].start || a.slot - b.slot,
  );
  // 音価: 次イベントの開始（同一小節内はスロット、小節をまたぐ場合は小節末）
  const events: LayoutEvent[] = sortedEvents.map((ev, i) => {
    const next = sortedEvents[i + 1];
    const m = measures[ev.measure];
    let slotsLen: number;
    if (next && next.measure === ev.measure) {
      slotsLen = Math.max(1, next.slot - ev.slot);
    } else {
      slotsLen = Math.max(1, m.slots - ev.slot);
    }
    return {
      index: i,
      system: Math.floor(ev.measure / perSystem),
      measure: ev.measure,
      slot: ev.slot,
      x: 0,
      rows: Object.entries(ev.cells).map(([row, text]) => ({ row: Number(row), text })),
      label: ev.label,
      time: measureTimeOf(m, ev.slot),
      rhythm: rhythmOf(slotsLen, slotsPerBeat),
      slotsLen,
      start: m.start,
      end: m.end,
    };
  });

  // システム（段）の組み立て
  const systems: LayoutSystem[] = [];
  for (let mi = 0; mi < measures.length; mi += perSystem) {
    const chunk = measures.slice(mi, mi + perSystem);
    const sysIndex = systems.length;
    let x = 12; // 左余白（弦名）
    const ms = chunk.map((m, k) => {
      const entry = { index: mi + k, x, width: measureWidth(m), start: m.start, end: m.end };
      x += entry.width;
      return entry;
    });
    systems.push({ index: sysIndex, measures: ms, events: [], width: x + 12 });
    for (const ev of events) {
      if (ev.measure >= mi && ev.measure < mi + chunk.length) {
        const local = ev.measure - mi;
        // セル位置: 小節内 (slot+1.5)*SLOT_W（PDF/ASCIIと同じ規則）
        ev.x = ms[local].x + (ev.slot + 1.5) * SLOT_W;
        systems[sysIndex].events.push(ev);
      }
    }
  }

  return {
    score,
    systems,
    events,
    timeSignature: "4/4",
    systemHeight: TOP_PAD + 5 * STAFF_GAP + BOTTOM_PAD,
    timeToX(t: number) {
      for (let mi = 0; mi < measures.length; mi++) {
        const m = measures[mi];
        if (t >= m.start && t < m.end) {
          const pos = (t - m.start) / Math.max(m.end - m.start, 1e-6);
          const sysIndex = Math.floor(mi / perSystem);
          const local = mi - sysIndex * perSystem;
          const mx = systems[sysIndex].measures[local].x;
          return { system: sysIndex, x: mx + (pos * (m.slots - 1) + 1.5) * SLOT_W };
        }
      }
      return null;
    },
  };
}

/** 小節内のスロット位置の実時間（カーソル補間用） */
function measureTimeOf(m: Measure, slot: number): number {
  const pos = m.slots > 1 ? slot / (m.slots - 1) : 0;
  return m.start + pos * (m.end - m.start);
}
