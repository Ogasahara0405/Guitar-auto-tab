/**
 * 画面用タブ譜レイアウト（shared/tabLayout.ts）のテスト
 * 標準様式（小節単位の段折り返し・音価ステム・ビーム・拍子）の配置計算を検証する。
 */
import { describe, expect, it } from "vitest";
import { buildTabLayout, rhythmOf, flagCount, beamGroups, SLOT_W, type LayoutEvent } from "../shared/tabLayout";
import { AnalysisBody } from "../shared/schema";

const result = AnalysisBody.parse({
  meta: { title: "t", duration: 8.0, tempo: 120.0, mode: "melody" },
  notes: [
    { start: 0.0, end: 0.5, midi: 64, string: 3, fret: 5 },
    { start: 0.5, end: 1.0, midi: 67, string: 3, fret: 7 },
    { start: 1.0, end: 1.5, midi: 64, string: 3, fret: 5 },
    { start: 1.5, end: 2.0, midi: 62, string: 4, fret: 2 },
  ],
  chords: [],
  beats: [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5],
  barlines: [0.0, 2.0, 4.0, 6.0, 8.0],
});

describe("rhythmOf", () => {
  it("スロット長から音価を分類する（8分グリッド）", () => {
    expect(rhythmOf(8, 2)).toBe("whole"); // 4拍
    expect(rhythmOf(4, 2)).toBe("half"); // 2拍
    expect(rhythmOf(2, 2)).toBe("quarter"); // 1拍
    expect(rhythmOf(1, 2)).toBe("eighth"); // 1/2拍
    expect(rhythmOf(1, 4)).toBe("sixteenth"); // 16分グリッドの1スロット
    expect(rhythmOf(2, 4)).toBe("eighth");
  });

  it("フラグ本数が音価に対応する", () => {
    expect(flagCount("whole")).toBe(0);
    expect(flagCount("quarter")).toBe(0);
    expect(flagCount("eighth")).toBe(1);
    expect(flagCount("sixteenth")).toBe(2);
    expect(flagCount("thirtysecond")).toBe(3);
  });
});

describe("buildTabLayout", () => {
  it("小節単位の段（システム）に折り返す", () => {
    const layout = buildTabLayout(result, { measuresPerSystem: 2 });
    expect(layout.systems).toHaveLength(2); // 4小節 → 2段
    expect(layout.systems[0].measures).toHaveLength(2);
    expect(layout.systems[1].measures).toHaveLength(2);
    expect(layout.events).toHaveLength(4);
    expect(layout.timeSignature).toBe("4/4");
  });

  it("イベントが段と小節に正しく配置され、時刻が復元できる", () => {
    const layout = buildTabLayout(result, { measuresPerSystem: 4 });
    const ev0 = layout.events[0];
    expect(ev0.system).toBe(0);
    expect(ev0.x).toBeGreaterThan(0);
    // 時刻 → x 変換がイベント位置と近いこと（スロット中心との整合）
    const loc = layout.timeToX(0.0);
    expect(loc).not.toBeNull();
    expect(Math.abs(loc!.x - ev0.x)).toBeLessThanOrEqual(SLOT_W);
  });

  it("音価が次イベントまでの長さで決まる", () => {
    const layout = buildTabLayout(result, { measuresPerSystem: 4 });
    // tempo 120・8分グリッド: 0.5秒 = 1拍 = quarter
    expect(layout.events[0].rhythm).toBe("quarter");
    expect(layout.events[3].rhythm).toBe("quarter");
  });

  it("コンテナ幅から1段の小節数を自動計算できる", () => {
    const layout = buildTabLayout(result, { containerWidth: 500 });
    // 1小節(2スロット)= (2+2)*14 = 56px → 500pxなら8小節ぶん→上限8だが小節は4
    expect(layout.systems.length).toBeGreaterThanOrEqual(1);
    expect(layout.systems[0].measures.length).toBeLessThanOrEqual(8);
  });
});

describe("beamGroups", () => {
  const mk = (index: number, measure: number, slot: number, slotsLen: number, rhythm: LayoutEvent["rhythm"]): LayoutEvent => ({
    index,
    system: 0,
    measure,
    slot,
    x: 0,
    rows: [{ row: 0, text: "1" }],
    label: null,
    time: slot * 0.25,
    rhythm,
    slotsLen,
    start: 0,
    end: 10,
  });

  it("連続する同音価（8分以下）をビームでつなぐ", () => {
    const evs = [
      mk(0, 0, 0, 1, "eighth"),
      mk(1, 0, 1, 1, "eighth"),
      mk(2, 0, 2, 1, "eighth"),
      mk(3, 0, 3, 1, "eighth"),
    ];
    const groups = beamGroups(evs, 2);
    // 1拍目2つ・2拍目2つ（拍単位でビームを切る）
    expect(groups).toHaveLength(2);
    expect(groups[0].map((e) => e.index)).toEqual([0, 1]);
  });

  it("音価が違う・4分以上・小節をまたぐ場合はビームを切る", () => {
    const evs = [
      mk(0, 0, 0, 1, "eighth"),
      mk(1, 0, 1, 1, "sixteenth"), // 音価違い
      mk(2, 0, 2, 2, "quarter"), // フラグ無し
    ];
    expect(beamGroups(evs, 2)).toHaveLength(0);
  });
});
