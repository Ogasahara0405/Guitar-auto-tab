/**
 * 譜面レイアウト（grid.ts）とASCIIタブ（render.ts）のテスト
 * 旧: tests/test_pipeline.py の test_ascii_render を移植。
 */
import { describe, expect, it } from "vitest";
import { buildScore } from "../server/core/grid";
import { scoreToAscii } from "../server/core/render";
import { AnalysisBody } from "../shared/schema";

const result = AnalysisBody.parse({
  meta: { title: "sample", duration: 4.0, tempo: 120.0, mode: "melody" },
  notes: [
    { start: 0.0, end: 0.5, midi: 64, string: 3, fret: 5 },
    { start: 0.5, end: 1.0, midi: 67, string: 3, fret: 7 },
  ],
  chords: [],
  beats: [0.0, 0.5, 1.0, 1.5, 2.0],
  barlines: [0.0, 2.0, 4.0],
});

describe("scoreToAscii", () => {
  it("フレット数字を含むASCIIタブを出力する", () => {
    const txt = scoreToAscii(result);
    expect(txt).toContain("5");
    expect(txt).toContain("7");
    expect(txt).toContain("e|");
    expect(txt).toContain("E|");
    expect(txt).toContain("# sample");
    expect(txt).toContain("tempo=120");
  });

  it("コードモードはラベルを描画する", () => {
    const chordResult = AnalysisBody.parse({
      meta: { title: "chords", duration: 4.0, tempo: 120.0, mode: "chords" },
      notes: [],
      chords: [
        {
          start: 0.0,
          end: 2.0,
          label: "Am",
          shape: [
            { string: 5, fret: 0 },
            { string: 4, fret: 2 },
            { string: 3, fret: 2 },
            { string: 2, fret: 1 },
            { string: 1, fret: 0 },
          ],
        },
      ],
      beats: [0.0, 1.0, 2.0, 3.0],
      barlines: [0.0, 2.0, 4.0],
    });
    const txt = scoreToAscii(chordResult);
    expect(txt).toContain("Am");
  });
});

describe("buildScore", () => {
  it("小節・スロットへノートを配置する", () => {
    const score = buildScore(result);
    expect(score.measures).toHaveLength(2);
    expect(score.events).toHaveLength(2);
  });

  it("同時発音（開始時刻が近いノート）は1イベントにまとまる", () => {
    const duet = AnalysisBody.parse({
      ...result,
      notes: [
        { start: 0.0, end: 0.5, midi: 59, string: 4, fret: 2 },
        { start: 0.02, end: 0.5, midi: 64, string: 3, fret: 5 },
      ],
    });
    const score2 = buildScore(duet);
    expect(score2.events).toHaveLength(1);
    expect(Object.keys(score2.events[0].cells)).toHaveLength(2);
  });
});
