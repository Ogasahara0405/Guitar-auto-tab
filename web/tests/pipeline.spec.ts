/**
 * パイプライン統括（pipeline.ts）のテスト — ワーカーをスタブ化したE2E相当。
 * tone閾値 → 映像ゲート → 割当 → 成果物保存、コードモードのボイシング＋
 * ミュート確認、磨き上げJSON取り込みの流れを検証する。
 * 実音声での DSP 検証は Python 側 tests/test_dsp.py が担う。
 */
import { mkdtemp, mkdir, writeFile, readFile, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { analyze, importAnalysis } from "../server/core/pipeline";
import type { WorkerCtx, WorkerRunner } from "../server/worker/client";

function stubCtx(root: string, responses: Record<string, unknown>): WorkerCtx {
  const runner: WorkerRunner = async (args) => {
    const key = args[0];
    const r = responses[key];
    if (r === undefined) throw new Error(`スタブにないコマンド: ${key}`);
    return r;
  };
  return { root, python: "python", runner };
}

describe("analyze（メロディモード）", () => {
  it("tone閾値で無関係な音を落とし、タブを割り当てて成果物を保存する", async () => {
    const root = await mkdtemp(join(tmpdir(), "gat-test-"));
    const ctx = stubCtx(root, {
      acquire: { wav: "source.wav", title: "sample曲", media: "source_original.wav" },
      perceive: {
        duration: 4.0,
        tempo: 120.0,
        chords_tempo: null,
        separated: true,
        mode: "melody",
        audio_file: "guitar_mono.wav",
        notes: [
          { start: 0.0, end: 0.5, midi: 52, evidence: 1.0, tone: 0.9 },
          { start: 1.0, end: 1.5, midi: 57, evidence: 1.0, tone: 0.3 }, // 無関係な音
          { start: 2.0, end: 2.5, midi: 64, evidence: 1.0, tone: 0.8 },
        ],
        chords: [],
        play: null,
        beats: [0, 1, 2, 3],
        barlines: [0, 2, 4],
      },
      frames: { frames: { "0": "frame_0000.00.jpg", "2": "frame_0002.00.jpg" } },
    });

    const result = await analyze(ctx, {
      mode: "melody",
      chordStyle: "chord",
      source: { kind: "file", path: "dummy.wav", filename: "sample曲.wav" },
    });

    // tone フィルタ: 0.3 のノートだけが除去される
    expect(result.meta.tone_dropped).toBe(1);
    expect(result.notes.map((n) => n.midi)).toEqual([52, 64]);
    // 弦/フレットが割り当てられている
    for (const n of result.notes) {
      expect(n.string).not.toBeNull();
      expect(n.fret).not.toBeNull();
    }
    // フレームがリンクされる（時刻0と2のノート）
    expect(result.notes[0].frame).toBe("frame_0000.00.jpg");
    expect(result.notes[1].frame).toBe("frame_0002.00.jpg");
    expect(result.meta.video_frames).toBe(2);
    expect(result.meta.title).toBe("sample曲");
    expect(result.meta.media_file).toBe("source_original.wav");

    // 成果物が保存される
    const dir = join(root, "output", result.id);
    await access(join(dir, "analysis.json"));
    await access(join(dir, "tab.txt"));
    await access(join(dir, "tab.pdf"));
    const txt = await readFile(join(dir, "tab.txt"), "utf-8");
    expect(txt).toContain("e|");
  });
});

describe("analyze（コードモード）", () => {
  it("ボイシングを決め、ミュート弦を除去して保存する", async () => {
    const root = await mkdtemp(join(tmpdir(), "gat-test-"));
    const responses: Record<string, unknown> = {
      acquire: { wav: "source.wav", title: "backing", media: "source_original.mp3" },
      perceive: {
        duration: 4.0,
        tempo: 120.0,
        chords_tempo: 128.0,
        separated: false,
        mode: "chords",
        audio_file: "mix.wav",
        notes: [],
        chords: [
          { start: 0.0, end: 2.0, label: "Am" },
          { start: 2.0, end: 4.0, label: "E" },
        ],
        play: null,
        beats: [0, 1, 2, 3],
        barlines: [0, 2, 4],
      },
      frames: { frames: {} },
      "verify-mutes": { muted: [[1, 2], []] },
    };
    const ctx = stubCtx(root, responses);

    const result = await analyze(ctx, {
      mode: "chords",
      chordStyle: "chord",
      source: { kind: "file", path: "dummy.mp3", filename: "backing.mp3" },
    });

    expect(result.chords).toHaveLength(2);
    // Am はミュート弦(1,2)が押さえ方から除かれ、muted に記録される
    const am = result.chords[0];
    expect(am.muted?.sort()).toEqual([1, 2]);
    expect(am.shape.map((s) => s.string)).not.toContain(1);
    expect(am.shape.map((s) => s.string)).not.toContain(2);
    // E は全弦
    expect(result.chords[1].muted).toBeNull();
    expect(result.chords[1].shape.length).toBeGreaterThan(3);
    // chords モードのテンポはコード抽出側の値
    expect(result.meta.tempo).toBe(128.0);
  });
});

describe("importAnalysis", () => {
  it("磨き上げJSONを取り込み、元ジョブのフレームを引き継ぐ", async () => {
    const root = await mkdtemp(join(tmpdir(), "gat-test-"));
    // 磨き上げ元ジョブのフレーム
    await mkdir(join(root, "output", "abcd1234", "frames"), { recursive: true });
    await writeFile(join(root, "output", "abcd1234", "frames", "frame_0000.70.jpg"), "x");
    const ctx = stubCtx(root, {});

    const jsonText = JSON.stringify({
      meta: {
        title: "磨いた曲",
        duration: 4.0,
        tempo: 120.0,
        mode: "melody",
        source_job: "abcd1234",
      },
      notes: [{ start: 0.7, end: 1.0, midi: 52, string: 3, fret: 7, frame: "frame_0000.70.jpg", memo: "bend" }],
      chords: [],
      beats: [],
      barlines: [0, 2, 4],
    });
    const result = await importAnalysis(ctx, jsonText);

    expect(result.meta.title).toBe("磨いた曲");
    expect(result.notes[0].fret).toBe(7);
    // 未知キー（memo）は落とされない
    expect((result.notes[0] as Record<string, unknown>).memo).toBe("bend");
    // フレーム引き継ぎ
    await access(join(root, "output", result.id, "frames", "frame_0000.70.jpg"));
    await access(join(root, "output", result.id, "analysis.json"));
  });

  it("meta の無いJSONは拒否する", async () => {
    const root = await mkdtemp(join(tmpdir(), "gat-test-"));
    const ctx = stubCtx(root, {});
    await expect(importAnalysis(ctx, JSON.stringify({ notes: [] }))).rejects.toThrow(/meta/);
  });
});
