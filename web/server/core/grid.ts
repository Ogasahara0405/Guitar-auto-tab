/**
 * タブ譜のグリッド配置計算（ASCII描画・PDF描画の共通レイアウト）
 *
 * 旧: app/core/grid.py を移植。
 */
import type { AnalysisBody, ChordEvent, NoteEvent } from "../../shared/schema";
import { groupByStart } from "../../shared/events";

export interface Measure {
  start: number;
  end: number;
  slots: number;
}

/** row: 0 = 1弦(高音e/上) … 5 = 6弦(低音E/下) */
export interface ScoreEvent {
  measure: number;
  slot: number;
  cells: Record<number, string>;
  label: string | null;
}

export interface ScoreLabel {
  measure: number;
  slot: number;
  text: string;
}

export interface Score {
  measures: Measure[];
  events: ScoreEvent[];
  labels: ScoreLabel[];
  slots_per_measure_max: number;
}

/**
 * 解析結果JSON → 描画用スコア情報。
 * slots_per_beat を省略するとノート密度から自動選択（2分割/16分グリッド）。
 */
export function buildScore(result: AnalysisBody, slotsPerBeat?: number): Score {
  const meta = result.meta;
  const duration = Number(meta.duration || 0.0);
  const tempo = Number(meta.tempo || 120.0);
  const beatDur = 60.0 / Math.max(tempo, 1.0);

  let barlines = [...(result.barlines || [])];
  if (!barlines.length || barlines[0] > 0.05) barlines = [0.0, ...barlines];
  if (barlines[barlines.length - 1] < duration - 0.05) barlines.push(duration);

  const notes = result.notes || [];
  const chords = result.chords || [];

  if (slotsPerBeat == null) {
    // ノート密度が高いときは16分グリッドへ
    slotsPerBeat = notes.length && duration > 0 && notes.length / duration > 3.5 ? 4 : 2;
  }

  const measures: Measure[] = [];
  for (let i = 0; i + 1 < barlines.length; i++) {
    const a = barlines[i];
    const b = barlines[i + 1];
    if (b - a <= 0.01) continue;
    const slots = Math.max(2, Math.round(((b - a) / beatDur) * slotsPerBeat));
    measures.push({ start: a, end: b, slots });
  }
  if (!measures.length) {
    measures.push({ start: 0.0, end: Math.max(duration, 1.0), slots: 8 });
  }

  const bounds = measures.map((m) => m.start);
  const occupied: Set<number>[] = measures.map(() => new Set());
  const events: ScoreEvent[] = [];
  const labels: ScoreLabel[] = [];

  const place = (t: number): [number, number] => {
    // bisect_right(bounds, t) - 1
    let mi = 0;
    for (let i = 0; i < bounds.length; i++) {
      if (bounds[i] <= t) mi = i;
    }
    mi = Math.max(0, Math.min(mi, measures.length - 1));
    const m = measures[mi];
    const pos = (t - m.start) / Math.max(m.end - m.start, 1e-6);
    let slot = Math.round(pos * (m.slots - 1));
    slot = Math.max(0, Math.min(slot, m.slots - 1));
    while (occupied[mi].has(slot) && slot < m.slots - 1) slot += 1;
    occupied[mi].add(slot);
    return [mi, slot];
  };

  // 開始時刻がほぼ同じノートは同時発音として1イベント（複数弦のセル）にまとめる
  const assigned = notes.filter((n) => n.string != null && n.fret != null);
  for (const group of groupByStart(assigned)) {
    const cells: Record<number, string> = {};
    for (const n of group) {
      const row = (n as NoteEvent).string! - 1; // 1弦→row0(上)
      if (0 <= row && row <= 5) cells[row] = String(Math.round((n as NoteEvent).fret!));
    }
    const [mi, slot] = place(group[0].start);
    events.push({ measure: mi, slot, cells, label: null });
  }

  for (const c of chords as ChordEvent[]) {
    const shape = c.shape || [];
    if (shape.length) {
      const cells: Record<number, string> = {};
      for (const st of shape) {
        const row = st.string - 1;
        if (0 <= row && row <= 5) cells[row] = String(Math.round(st.fret));
      }
      const [mi, slot] = place(c.start);
      events.push({ measure: mi, slot, cells, label: c.label ?? null });
    }
    if (c.label && c.label !== "N.C.") {
      const [mi, slot] = place(c.start);
      labels.push({ measure: mi, slot, text: c.label });
    }
  }

  return {
    measures,
    events,
    labels,
    slots_per_measure_max: Math.max(...measures.map((m) => m.slots)),
  };
}
