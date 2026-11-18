/**
 * ノートイベント共通ユーティリティ（tabassign / grid / TabViewer で共有）
 *
 * 旧構成では grid.py と TabViewer.tsx に「開始時刻がほぼ同じノートを
 * 同時発音としてまとめる」処理が重複していたため、ここへ集約した。
 */
import type { NoteEvent } from "./schema";

/** 同時発音（複数本指・ダブルストップ）とみなす開始時刻の誤差（秒） */
export const GROUP_TOL = 0.05;

/** 時刻のキー正規化（lane_hints / fret_hints / フレーム照合で使用） */
export function round3(t: number): number {
  return Math.round(t * 1000) / 1000;
}

/**
 * 開始時刻がほぼ同じアイテムを1グループにまとめる。
 * start 昇順（同着は入力順のまま）に並べて GROUP_TOL 以内を連結する。
 */
export function groupByStart<T extends { start: number }>(items: T[]): T[][] {
  const sorted = [...items].sort((a, b) => a.start - b.start);
  const groups: T[][] = [];
  for (const it of sorted) {
    const last = groups[groups.length - 1];
    if (last && it.start - last[0].start <= GROUP_TOL) {
      last.push(it);
    } else {
      groups.push([it]);
    }
  }
  return groups;
}

/** タブ1セル（弦行・フレット数字） */
export interface TabCell {
  row: number; // 0 = 1弦(高音e) … 5 = 6弦(低音E)
  text: string;
}

/** タブ譜の1イベント（同時発音は複数セル） */
export interface TabEvent {
  start: number;
  end: number;
  cells: TabCell[];
  label: string | null;
}

/** 弦/フレット割当済みノートを TabEvent にまとめる（TabViewer 用） */
export function toTabEvents(notes: NoteEvent[]): TabEvent[] {
  const evs: TabEvent[] = [];
  const sorted = [...notes].sort((a, b) => a.start - b.start);
  for (const n of sorted) {
    if (n.string == null || n.fret == null) continue;
    const cell: TabCell = { row: n.string - 1, text: String(n.fret) };
    const g = evs[evs.length - 1];
    if (g && !g.label && n.start - g.start <= GROUP_TOL) {
      g.cells.push(cell);
      g.end = Math.max(g.end, n.end);
    } else {
      evs.push({ start: n.start, end: n.end, cells: [cell], label: null });
    }
  }
  return evs;
}
