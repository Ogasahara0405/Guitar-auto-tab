/**
 * 契約スキーマ（shared/schema.ts）のテスト
 * 旧: tests/test_pipeline.py の test_api_contract（Pydantic↔OpenAPI↔TS型の同期検査）は
 * zod 一元管理により不要になった。代わりに契約の検証挙動をここに置く。
 */
import { describe, expect, it } from "vitest";
import { AnalysisResult, PerceptionResult } from "../shared/schema";

describe("AnalysisResult", () => {
  it("解析結果を検証できる", () => {
    const parsed = AnalysisResult.parse({
      id: "abcd1234",
      meta: { title: "t", duration: 10, tempo: 120, mode: "melody" },
      notes: [{ start: 0, end: 1, midi: 60, string: 3, fret: 5 }],
      chords: [],
      beats: [0, 0.5],
      barlines: [0, 2],
    });
    expect(parsed.notes[0].fret).toBe(5);
  });

  it("磨き上げフローの未知キーを落とさない", () => {
    const parsed = AnalysisResult.parse({
      id: "abcd1234",
      meta: { title: "t", duration: 10, tempo: 120, mode: "melody", custom_meta: 1 },
      notes: [{ start: 0, end: 1, midi: 60, string: 3, fret: 5, memo: "bend!" }],
      chords: [],
      beats: [],
      barlines: [],
    });
    expect((parsed.notes[0] as Record<string, unknown>).memo).toBe("bend!");
    expect((parsed.meta as Record<string, unknown>).custom_meta).toBe(1);
  });

  it("欠落した任意フィールドは null になる", () => {
    const parsed = AnalysisResult.parse({
      id: "abcd1234",
      meta: { title: "t", duration: 10, tempo: 120, mode: "chords" },
      notes: [{ start: 0, end: 1, midi: 60 }],
      chords: [],
      beats: [],
      barlines: [],
    });
    expect(parsed.notes[0].string).toBeNull();
    expect(parsed.notes[0].tone).toBeNull();
  });

  it("不正な値は拒否する", () => {
    expect(() =>
      AnalysisResult.parse({
        id: "abcd1234",
        meta: { title: "t", duration: 10, tempo: 120, mode: "hoge" },
        notes: [],
        chords: [],
        beats: [],
        barlines: [],
      }),
    ).toThrow();
  });
});

describe("PerceptionResult", () => {
  it("ワーカー出力を検証できる（NaN→null の play データを含む）", () => {
    const parsed = PerceptionResult.parse({
      duration: 10,
      tempo: 120,
      chords_tempo: null,
      separated: true,
      mode: "melody",
      audio_file: "guitar_mono.wav",
      notes: [{ start: 0, end: 1, midi: 60, evidence: 1, tone: 0.8 }],
      chords: [],
      play: {
        times: [0, 0.1],
        energy: [0.1, 0.2],
        events: [{ t: 0.05, strength: 0.2, y: null, width: 4, units: 0.5 }],
        band: [10, 200],
        p90: 0.15,
        neck_xs: [null, 12.5],
        fret_map: { a: 40, b: 580, w: 640, inliers: 6, residual: 1.2 },
      },
      beats: [0],
      barlines: [0],
    });
    expect(parsed.play!.events[0].y).toBeNull();
    expect(parsed.play!.fret_map!.b).toBe(580);
  });
});
