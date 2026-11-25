/**
 * 不要音クリーニング（clean.ts）のテスト
 * 実測で観測されたジャンク（断片・弱い短音・混入音由来の副次声・
 * 開始がずれた弱い声・孤児グループ）が除去され、
 * 確かな演奏（ダブルストップ・オクターブ・小コード）は残ることを検証する。
 */
import { describe, expect, it } from "vitest";
import {
  cleanMelodyNotes,
  MIN_DURATION,
  SHORT_DURATION,
  SIMULTANEOUS_EVIDENCE,
  STRICT_EVIDENCE,
} from "../server/core/clean";
import type { PerceptionNote } from "../shared/schema";

const n = (
  start: number,
  end: number,
  midi: number,
  evidence = 1.0,
): PerceptionNote => ({ start, end, midi, evidence, tone: 1.0, bend: null, vibrato: null });

describe("cleanMelodyNotes", () => {
  it("断片ノート（極端に短い）を除去する", () => {
    const notes = [n(0.0, MIN_DURATION - 0.01, 60, 1.0), n(1.0, 1.5, 62, 1.0)];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept.map((x) => x.midi)).toEqual([62]);
    expect(dropped).toBe(1);
  });

  it("弱い短音を除去し、強い短音は残す", () => {
    const notes = [
      n(0.0, SHORT_DURATION - 0.01, 60, STRICT_EVIDENCE - 0.1), // 弱い短音 → 除去
      n(1.0, 1.1, 62, 0.95), // 強い短音 → 残す
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept.map((x) => x.midi)).toEqual([62]);
    expect(dropped).toBe(1);
  });

  it("同時に弾かれた根拠の弱い副次声を除去し、主音は残す", () => {
    const notes = [
      n(0.0, 0.5, 52, 1.0), // 主音
      n(0.01, 0.5, 57, 0.32), // 同時・閾値未満 → 除去
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept.map((x) => x.midi)).toEqual([52]);
    expect(dropped).toBe(1);
  });

  it("しっかり鳴っている同時発音（ダブルストップ・オクターブ）は残す", () => {
    const notes = [
      n(0.0, 0.5, 57, 1.0),
      n(0.01, 0.5, 69, 0.8), // オクターブ（強い根拠）→ 残す
      n(2.0, 2.5, 59, 1.0),
      n(2.02, 2.5, 64, 0.7), // ダブルストップ（強い根拠）→ 残す
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept).toHaveLength(4);
    expect(dropped).toBe(0);
  });

  it("控えめな根拠のオクターブ・ダブルストップ（同時弾き）も残す", () => {
    // 回帰テスト: melody.py の evidence 尺度では本物の同時発音も 0.3〜0.5 になり得る
    const notes = [
      n(0.0, 0.5, 57, 1.0),
      n(0.02, 0.5, 69, SIMULTANEOUS_EVIDENCE), // 控えめなオクターブ → 残す
      n(2.0, 2.5, 52, 1.0),
      n(2.01, 2.5, 59, 0.45), // 控えめな4度 → 残す
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept).toHaveLength(4);
    expect(dropped).toBe(0);
  });

  it("開始が大きくずれた弱い副次声（混入音の倍音の実測パターン）を除去する", () => {
    // 回帰テスト: 開始が0.26秒以上ずれて重なるだけの弱い声は除去される
    const notes = [
      n(0.0, 1.0, 60, 1.0), // 主音
      n(0.26, 0.9, 72, 0.42), // オクターブ上の倍音誤検出（非同時）→ 除去
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept.map((x) => x.midi)).toEqual([60]);
    expect(dropped).toBe(1);
  });

  it("主音の無い孤児クラスタは弱い声を残さない", () => {
    // 回帰テスト: tone除去で主音だけ落ちた副次声の残骸を除去する
    const notes = [
      n(0.0, 0.8, 60, 0.8), // 主音は無い（evidence 1.0 が無い）→ 強い声は残す
      n(0.05, 0.7, 72, 0.45), // 孤児の弱い声 → 除去
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept.map((x) => x.midi)).toEqual([60]);
    expect(dropped).toBe(1);
  });

  it("孤児クラスタで全員が弱ければ全員除去する", () => {
    const notes = [n(0.0, 0.6, 60, 0.45), n(0.1, 0.6, 72, 0.4)];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept).toHaveLength(0);
    expect(dropped).toBe(2);
  });

  it("単音の主音（evidence 1.0）は一切減らない", () => {
    const notes = [n(0.0, 0.3, 45, 1.0), n(0.5, 0.8, 48, 1.0), n(1.0, 1.4, 50, 1.0)];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept).toHaveLength(3);
    expect(dropped).toBe(0);
  });

  it("重なりのない連続する単音はまとめて処理されない", () => {
    // 旋律の連続音がクラスタ化されて副次声扱いされないこと
    const notes = [
      n(0.0, 0.3, 45, 1.0),
      n(0.4, 0.7, 47, 1.0),
      n(0.8, 1.1, 48, 0.9), // 主音でなくても単独（孤児だが evidence 高い）→ 残す
    ];
    const [kept, dropped] = cleanMelodyNotes(notes);
    expect(kept).toHaveLength(3);
    expect(dropped).toBe(0);
  });
});
