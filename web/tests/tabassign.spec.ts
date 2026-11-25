/**
 * 弦/フレット割当（tabassign.ts）のテスト
 * 旧: tests/test_pipeline.py の test_melody（割当部）・test_hand_position・
 *     test_polyphony（割当部）・test_video_gate/test_fret_markers（ヒント反映部）を移植。
 */
import { describe, expect, it } from "vitest";
import { assignFrets, candidates, type FretHints, type LaneHints, type RawNote } from "../server/core/tabassign";

const OPEN_MIDI: Record<number, number> = { 6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64 };

function spanOf(ns: { fret?: number }[]): number {
  const fr = ns.map((n) => n.fret ?? 0).filter((f) => f > 0);
  return fr.length >= 2 ? Math.max(...fr) - Math.min(...fr) : 0;
}

function checkTab(ns: { string?: number; fret?: number; midi: number }[]) {
  for (const n of ns) {
    expect(n.string, `タブ変換されていない: ${JSON.stringify(n)}`).toBeDefined();
    expect(OPEN_MIDI[n.string!] + n.fret!, `フレット割当が不正: ${JSON.stringify(n)}`).toBe(n.midi);
  }
}

describe("assignFrets", () => {
  it("メロディをすべてタブ変換する", () => {
    const midis = [45, 48, 50, 52, 55, 57, 55, 52, 50, 48];
    const notes: RawNote[] = midis.map((m, i) => ({ start: i * 0.5, end: i * 0.5 + 0.4, midi: m }));
    const assigned = assignFrets(notes);
    expect(assigned).toHaveLength(midis.length);
    checkTab(assigned);
  });

  it("同時発音は異なる弦に割り当てられる（ダブルストップ）", () => {
    const notes: RawNote[] = [
      { start: 0.1, end: 0.6, midi: 59, evidence: 1.0 },
      { start: 0.1, end: 0.6, midi: 64, evidence: 1.0 },
    ];
    const a = assignFrets(notes);
    expect(a).toHaveLength(2);
    expect(new Set(a.map((n) => n.string)).size).toBe(2);
    checkTab(a);
  });

  it("1手で押さえられる3声は、開き3以内の割当に収まる", () => {
    const notes: RawNote[] = [
      { start: 0.1, end: 0.6, midi: 52, evidence: 1.0 }, // E3
      { start: 0.1, end: 0.6, midi: 59, evidence: 0.6 }, // B3
      { start: 0.1, end: 0.6, midi: 64, evidence: 0.5 }, // E4
    ];
    const a = assignFrets(notes);
    expect(a).toHaveLength(3);
    expect(spanOf(a)).toBeLessThanOrEqual(3);
    checkTab(a);
  });

  it("開放弦は開きに数えない", () => {
    const notes: RawNote[] = [
      { start: 1.0, end: 1.5, midi: 40, evidence: 1.0 }, // 6弦開放
      { start: 1.0, end: 1.5, midi: 76, evidence: 0.7 }, // 1弦12F
    ];
    const a = assignFrets(notes);
    expect(a).toHaveLength(2);
    expect(spanOf(a)).toBeLessThanOrEqual(3);
    checkTab(a);
  });

  it("1手で押さえられない同時発音は根拠の弱い声が除かれる", () => {
    const notes: RawNote[] = [
      { start: 2.0, end: 2.5, midi: 41, evidence: 1.0 }, // 6弦1F
      { start: 2.0, end: 2.5, midi: 86, evidence: 0.4 }, // 1弦22F
    ];
    const a = assignFrets(notes);
    expect(a.map((n) => n.midi)).toEqual([41]);
  });

  it("3声のうち1声だけが届かない場合は、その弱い声だけが除かれる", () => {
    const notes: RawNote[] = [
      { start: 3.0, end: 3.5, midi: 52, evidence: 1.0 },
      { start: 3.0, end: 3.5, midi: 57, evidence: 0.8 },
      { start: 3.0, end: 3.5, midi: 86, evidence: 0.3 },
    ];
    const a = assignFrets(notes);
    expect(a.map((n) => n.midi).sort((x, y) => x - y)).toEqual([52, 57]);
    expect(spanOf(a)).toBeLessThanOrEqual(3);
    checkTab(a);
  });

  it("映像の弦レーンの手がかりが弦割当に反映される", () => {
    const notes: RawNote[] = [
      { start: 0.7, end: 1.0, midi: 52, evidence: 1.0 },
      { start: 2.0, end: 2.3, midi: 52, evidence: 1.0 },
    ];
    const laneHints: LaneHints = new Map([
      [0.7, [0, 2]],
      [2.0, [1, 2]],
    ]);
    const assigned = assignFrets(notes, laneHints);
    expect(assigned).toHaveLength(2);
    checkTab(assigned);
    // 映像で別の弦を弾いているのに同じ弦にならない
    expect(new Set(assigned.map((n) => n.string)).size).toBe(2);
  });

  it("指板マーカーのフレット推定が割当に反映される", () => {
    const notes: RawNote[] = [
      { start: 0.7, end: 1.0, midi: 52, evidence: 1.0 }, // 7フレット付近で演奏
      { start: 2.0, end: 2.3, midi: 64, evidence: 1.0 }, // 17フレット付近で演奏
    ];
    const fretHints: FretHints = new Map([
      [0.7, 7],
      [2.0, 17],
    ]);
    const assigned = assignFrets(notes, null, fretHints);
    const by = new Map(assigned.map((n) => [Math.round(n.start * 100) / 100, n]));
    expect(Math.abs((by.get(0.7)!.fret ?? 99) - 7)).toBeLessThanOrEqual(2);
    expect(Math.abs((by.get(2.0)!.fret ?? 99) - 17)).toBeLessThanOrEqual(2);
    checkTab(assigned);
  });

  it("押さえられない割当を強制する映像仮説は棄却される（回帰: 4弦0F+5弦12F問題）", () => {
    // ほぼ同時の2音に、人間の手では同時に押さえられないフレット位置を強制する仮説
    const fretHints: FretHints = new Map([
      [204.3, 12],
      [204.39, 2],
    ]);
    const assigned = assignFrets(
      [
        { start: 204.3, end: 205.6, midi: 50, evidence: 0.43 },
        { start: 204.39, end: 205.6, midi: 57, evidence: 1.0 },
      ],
      null,
      fretHints,
    );
    expect(assigned).toHaveLength(2);
    checkTab(assigned);
    const frets = assigned.map((n) => n.fret!);
    expect(Math.max(...frets) - Math.min(...frets)).toBeLessThanOrEqual(3);
  });

  it("候補（弦/フレット）が音域を正しく表す", () => {
    expect(candidates(40)).toEqual([[0, 0]]);
    expect(candidates(41)).toEqual([[0, 1]]);
    expect(candidates(86)).toEqual([[5, 22]]);
    expect(candidates(39)).toEqual([]); // ギター音域外
  });
});
