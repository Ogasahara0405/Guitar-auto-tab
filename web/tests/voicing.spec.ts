/**
 * ボイシング（voicing.ts）のテスト
 * 旧: tests/test_pipeline.py の test_hand_position（押さえ方の制約）・
 *     test_chords（ボイシング生成）を移植。
 */
import { describe, expect, it } from "vitest";
import { shapeFor } from "../server/core/voicing";

describe("shapeFor", () => {
  it("主要なコードの押さえ方を生成する", () => {
    const sPow = shapeFor("A", "power", 0.0);
    const sFull = shapeFor("Am", "chord", 0.0);
    expect(sPow).not.toBeNull();
    expect(sFull).not.toBeNull();
    // Am: [None,0,2,2,1,0] 相当（6弦→1弦の定型フォーム）
    expect(sFull!.shape).toEqual([
      { string: 5, fret: 0 },
      { string: 4, fret: 2 },
      { string: 3, fret: 2 },
      { string: 2, fret: 1 },
      { string: 1, fret: 0 },
    ]);
  });

  it("すべての押さえ方が開放弦以外のフレット開き3以内（1手で押さえられる）", () => {
    for (const label of ["E", "Em", "E7", "A", "Am", "D", "Dm", "C", "G", "Gm", "F", "B7", "C#m"]) {
      for (const style of ["chord", "power"]) {
        const r = shapeFor(label, style, 0.0);
        if (r === null) continue;
        const frets = r.shape.map((st) => st.fret).filter((f) => f > 0);
        const span = frets.length ? Math.max(...frets) - Math.min(...frets) : 0;
        expect(span, `${label}/${style} の押さえ方が開きすぎ: ${JSON.stringify(r.shape)}`).toBeLessThanOrEqual(3);
      }
    }
  });

  it("前のポジションに近い押さえ方を選ぶ", () => {
    const low = shapeFor("C", "chord", 0.0);
    const high = shapeFor("C", "chord", 10.0);
    expect(low!.pos).toBeLessThan(high!.pos);
  });

  it("判定不能なラベルは null", () => {
    expect(shapeFor("N.C.", "chord", 0.0)).toBeNull();
    expect(shapeFor("Xyzz", "chord", 0.0)).toBeNull();
  });
});
