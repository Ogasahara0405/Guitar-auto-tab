/**
 * 映像ゲート（gate.ts）のテスト
 * 旧: tests/test_pipeline.py の test_video_gate（選別・声の絞り込み・レーン反映）と
 *     test_fret_markers（フレット推定の反映）を、合成 play データで移植
 * （映像からの play 生成そのものは Python 側 test_dsp.py が検証する）。
 */
import { describe, expect, it } from "vitest";
import { fretAt, gateChords, gateNotes } from "../server/core/gate";
import type { PlayData, PerceptionNote } from "../shared/schema";

function synthPlay(overrides: Partial<PlayData> = {}): PlayData {
  const times: number[] = [];
  const energy: number[] = [];
  for (let i = 0; i < 48; i++) {
    const t = i / 12;
    times.push(t);
    // 動作バースト1: 0.5〜0.9秒 / バースト2: 1.8〜2.2秒 / 2.6〜3.6秒は無動作
    const burst = (t >= 0.5 && t < 0.9) || (t >= 1.8 && t < 2.2);
    energy.push(burst ? 0.2 : 0.0);
  }
  return {
    times,
    energy,
    events: [
      { t: 0.7, strength: 0.2, y: 40, width: 8, units: 0.5 },
      { t: 2.0, strength: 0.2, y: 200, width: 8, units: 0.5 },
    ],
    band: [20, 220],
    p90: 0.15,
    neck_xs: times.map(() => null),
    fret_map: null,
    ...overrides,
  };
}

const notes: PerceptionNote[] = [
  { start: 0.7, end: 1.0, midi: 52, evidence: 1.0, tone: 1.0 },
  { start: 2.0, end: 2.3, midi: 64, evidence: 1.0, tone: 1.0 },
  { start: 3.1, end: 3.4, midi: 57, evidence: 1.0, tone: 1.0 }, // 映像で演奏なし
];

describe("gateNotes", () => {
  it("映像で演奏動作が確認できない位置のノートを除去する", () => {
    const play = synthPlay();
    const { notes: kept, dropped } = gateNotes(notes, play);
    expect(kept.map((n) => n.start)).toEqual([0.7, 2.0]);
    expect(dropped).toBe(1);
  });

  it("単弦ピッキングの映像に3声が乗った場合は弱い声を絞る", () => {
    const play = synthPlay();
    const voices: PerceptionNote[] = [
      { start: 0.7, end: 1.0, midi: 52, evidence: 1.0, tone: 1.0 },
      { start: 0.72, end: 1.0, midi: 57, evidence: 1.0, tone: 1.0 },
      { start: 0.74, end: 1.0, midi: 59, evidence: 0.3, tone: 1.0 },
    ];
    const { notes: kept } = gateNotes(voices, play);
    expect(kept.map((n) => n.start)).toEqual([0.7, 0.72]);
  });

  it("単弦ピッキングの弦位置（レーン）を手がかりとして返す", () => {
    const play = synthPlay();
    const { laneHints } = gateNotes(notes, play);
    expect(laneHints.size).toBe(2);
    expect(laneHints.get(0.7)).toEqual([0, 2]);
    expect(laneHints.get(2.0)).toEqual([1, 2]);
  });

  it("映像に動きがない（情報がない）場合は選別しない（安全側）", () => {
    const play = synthPlay({ p90: 0 });
    const { notes: kept, dropped } = gateNotes(notes, play);
    expect(kept).toHaveLength(3);
    expect(dropped).toBe(0);
  });

  it("映像が無い（null）場合は選別しない", () => {
    const { notes: kept, dropped } = gateNotes(notes, null);
    expect(kept).toHaveLength(3);
    expect(dropped).toBe(0);
  });

  it("指板マーカーのフレット推定を手がかりとして返す", () => {
    // ナット位置a=40・スケール長b=580（幅640基準）の指板座標系
    const fmap = { a: 40, b: 580, w: 640, inliers: 8, residual: 1.0 };
    const xOf = (f: number) => 40 + 580 * (1 - 2 ** (-f / 12));
    // neck_xs は動作解析フレーム（幅320）基準なので半分の座標
    const times: number[] = [];
    const energy: number[] = [];
    const neck_xs: (number | null)[] = [];
    for (let i = 0; i < 48; i++) {
      const t = i / 12;
      times.push(t);
      const inBurst1 = t >= 0.5 && t < 0.9;
      const inBurst2 = t >= 1.8 && t < 2.2;
      energy.push(inBurst1 || inBurst2 ? 0.2 : 0.0);
      neck_xs.push(inBurst1 ? (xOf(7) * 320) / 640 : inBurst2 ? (xOf(17) * 320) / 640 : null);
    }
    const play = synthPlay({ times, energy, neck_xs, fret_map: fmap });
    const { notes: kept, fretHints } = gateNotes(notes, play);
    expect(kept).toHaveLength(2);
    expect(Math.abs((fretHints.get(0.7) ?? 99) - 7)).toBeLessThanOrEqual(1.5);
    expect(Math.abs((fretHints.get(2.0) ?? 99) - 17)).toBeLessThanOrEqual(1.5);
  });
});

describe("fretAt", () => {
  const fmap = { a: 40, b: 580, w: 640, inliers: 8, residual: 1.0 };
  it("指板座標をフレット番号に変換する", () => {
    const x7 = 40 + 580 * (1 - 2 ** (-7 / 12));
    expect(fretAt(x7, fmap)).toBe(7);
    const x17 = 40 + 580 * (1 - 2 ** (-17 / 12));
    expect(fretAt(x17, fmap)).toBe(17);
  });
  it("ネック外・音域外は null", () => {
    expect(fretAt(10, fmap)).toBeNull(); // ナットより前
    expect(fretAt(619, fmap)).toBeNull(); // スケール長の75%以上
  });
});

describe("gateChords", () => {
  it("ストラムが見えない区間のコードを出さない", () => {
    const play = synthPlay();
    const chords = [
      { start: 0.7, end: 1.5, label: "Am" },
      { start: 3.1, end: 3.9, label: "E" }, // 映像で演奏なし
    ];
    const { chords: kept, dropped } = gateChords(chords, play);
    expect(kept.map((c) => c.label)).toEqual(["Am"]);
    expect(dropped).toBe(1);
  });
});
