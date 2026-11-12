"""パイプライン自己テスト: 既知の音を合成して採譜→タブ変換を検証する
実行: .venv\\Scripts\\python.exe tests\\test_pipeline.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import melody, tabassign, voicing, chords, render, pipeline, video  # noqa: E402

SR = 22050


def midi_to_f0(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def synth_note(f0: float, dur: float, amp: float = 0.35) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    for h, a in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.1)):
        y += a * np.sin(2 * np.pi * f0 * h * t)
    env = np.exp(-t * 4.0) * np.minimum(t / 0.004, 1.0)
    return (amp * y * env).astype(np.float32)


def synth_seq(midis, note_dur=0.42, gap=0.06) -> np.ndarray:
    parts = [synth_note(midi_to_f0(m), note_dur) for m in midis]
    g = np.zeros(int(gap * SR), dtype=np.float32)
    out = [g]
    for p in parts:
        out.append(p)
        out.append(g)
    return np.concatenate(out)


def synth_chord(midis, dur=1.8, strum=0.012) -> np.ndarray:
    t_total = int((dur + strum * len(midis)) * SR)
    y = np.zeros(t_total, dtype=np.float32)
    for i, m in enumerate(midis):
        note = synth_note(midi_to_f0(m), dur, amp=0.22)
        off = int(i * strum * SR)
        y[off: off + len(note)] += note
    return y


def synth_double(midis, dur=0.5) -> np.ndarray:
    """複数本指の同時発音（ダブルストップ等）を合成"""
    y = np.zeros(int(dur * SR), dtype=np.float32)
    for m in midis:
        note = synth_note(midi_to_f0(m), dur, amp=0.30)
        y[: len(note)] += note
    return y


def test_melody():
    expected = [45, 48, 50, 52, 55, 57, 55, 52, 50, 48]  # A2 C3 D3 E3 G3 A3 ...
    y = synth_seq(expected)
    notes = melody.extract_notes(y, SR)
    got = [n["midi"] for n in notes]
    print(f"  抽出ノート: {got}")
    assert got == expected, f"メロディ抽出が不一致: {got} != {expected}"

    notes = tabassign.assign_frets(notes)
    for n in notes:
        assert "string" in n and "fret" in n, f"タブ変換されていない: {n}"
        open_midi = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}[n["string"]]
        assert open_midi + n["fret"] == n["midi"], f"フレット割当が不正: {n}"
    print(f"  タブ: {[(n['string'], n['fret']) for n in notes]}")
    print("test_melody OK")


def test_polyphony():
    """複数本指（ダブルストップ・オクターブ）の同時発音を検出し、単音に誤検出しないこと"""
    y = np.concatenate([
        synth_double([59, 64]),           # ダブルストップ（4度）
        np.zeros(int(0.12 * SR), dtype=np.float32),
        synth_double([57, 69]),           # オクターブ奏法
        np.zeros(int(0.12 * SR), dtype=np.float32),
        synth_note(midi_to_f0(64), 0.5),  # 単音（余計な声を足さないこと）
    ])
    notes = melody.extract_notes(y, SR)
    print(f"  抽出ノート: {[(n['start'], n['end'], n['midi']) for n in notes]}")

    groups = []
    for n in sorted(notes, key=lambda x: x["start"]):
        if groups and n["start"] - groups[-1][0] <= 0.06:
            groups[-1][1].append(n["midi"])
        else:
            groups.append((n["start"], [n["midi"]]))
    pitch_sets = [sorted(m) for _, m in groups]
    assert pitch_sets[0] == [59, 64], f"ダブルストップ(B3+E4)が不一致: {pitch_sets}"
    assert pitch_sets[1] == [57, 69], f"オクターブ(A3+A4)が不一致: {pitch_sets}"
    assert pitch_sets[2] == [64], f"単音に余計な音が乗っている: {pitch_sets}"
    assert len(pitch_sets) == 3, f"イベント数が不正: {pitch_sets}"

    # 同時発音は異なる弦に割り当てられる
    assigned = tabassign.assign_frets(notes)
    first = [n for n in assigned if abs(n["start"] - groups[0][0]) <= 0.06]
    strings = {n["string"] for n in first}
    assert len(strings) == 2, f"同時発音が同じ弦に割り当てられた: {first}"
    print(f"  ダブルストップのタブ: {[(n['string'], n['fret']) for n in first]}")
    print("test_polyphony OK")


def test_mute_filter():
    """ミュート（弾いていない弦）が音声確認で除去されること"""
    # Amの押さえ方のうち 5弦(A2)/4弦(E3)/3弦(A3) だけ鳴らす（2弦・1弦はミュート）
    y = synth_chord([45, 52, 57], dur=1.5, strum=0.0)
    shape = voicing.shape_for("Am", "chord", 0.0)["shape"]  # [None,0,2,2,1,0] 相当
    kept, muted = chords.filter_muted(y, SR, 0.05, 1.4, shape)
    kept_strings = sorted(st["string"] for st in kept)
    print(f"  押さえ方: {shape} → 鳴り: {kept_strings} / ミュート: {sorted(muted)}")
    assert kept_strings == [3, 4, 5], f"鳴っている弦の判定が不正: {kept_strings}"
    assert sorted(muted) == [1, 2], f"ミュート判定が不正: {muted}"

    # 全弦鳴っている場合は何も除去されない（Eコード: 40,47,52,56,59,64）
    y2 = synth_chord([40, 47, 52, 56, 59, 64], dur=1.5, strum=0.012)
    kept2, muted2 = chords.filter_muted(y2, SR, 0.05, 1.4, voicing.shape_for("E", "chord", 0.0)["shape"])
    assert not muted2, f"鳴っている弦を誤ってミュート判定: {muted2}"
    print("test_mute_filter OK")


def test_frames():
    """映像がある場合、ノート位置のフレームが切り出されること"""
    import subprocess
    from app.core import audio as core_audio

    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "clip.mp4")
        ff = core_audio.get_ffmpeg_exe()
        res = subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i", "color=c=blue:size=320x240:duration=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-shortest", "-pix_fmt", "yuv420p", src],
            capture_output=True, text=True,
        )
        assert res.returncode == 0 and Path(src).exists(), f"テスト動画の生成に失敗: {res.stderr[-300:]}"
        assert video.has_video(src), "映像検出に失敗"

        outdir = str(Path(td) / "frames")
        frames = video.extract_frames(src, [0.5, 1.5, 1.55], outdir)
        print(f"  フレーム: {frames}")
        assert len(frames) == 2, f"フレーム数が不正（重複時刻の間引きミス）: {frames}"
        for name in frames.values():
            assert (Path(outdir) / name).exists(), f"フレーム画像がない: {name}"
        assert video.frame_for(frames, 0.52) is not None, "近い時刻のフレーム参照に失敗"
    print("test_frames OK")


def test_chords():
    y = np.concatenate(
        [
            synth_chord([45, 48, 52, 57]),  # Am
            np.zeros(int(0.1 * SR), dtype=np.float32),
            synth_chord([40, 44, 47, 52]),  # E
        ]
    )
    out = chords.extract_chords(y, SR)
    labels = [c["label"] for c in out["chords"]]
    print(f"  抽出コード: {labels}")
    non_nc = [l for l in labels if l != "N.C."]
    assert non_nc, "コードが検出されない"
    assert non_nc[0].startswith("A"), f"1つ目がAmでない: {non_nc}"
    assert any(l.startswith("E") for l in non_nc), f"Eが検出されない: {non_nc}"

    s_pow = voicing.shape_for("A", "power", 0.0)
    s_full = voicing.shape_for("Am", "chord", 0.0)
    assert s_pow and s_full, "ボイシング生成に失敗"
    print(f"  A5形状: {s_pow['shape']} / Am形状: {s_full['shape']}")
    print("test_chords OK")


def test_full_pipeline():
    expected = [45, 48, 50, 52, 55, 57]
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "melody.wav"
        sf.write(wav, synth_seq(expected), SR)

        result = pipeline.analyze(str(wav), mode="melody")
        got = [n["midi"] for n in result["notes"]]
        print(f"  メロディ採譜: {got}")
        assert got == expected, f"不一致: {got}"

        job_dir = pipeline.OUTPUT_DIR / result["id"]
        for name in ("analysis.json", "tab.txt", "tab.pdf"):
            assert (job_dir / name).exists(), f"{name} が生成されていない"
        txt = (job_dir / "tab.txt").read_text(encoding="utf-8")
        assert "e|" in txt and "E|" in txt, "ASCIIタブの形式がおかしい"
        print(txt)

        # analysis.json → import（Claude Code磨き上げフロー）の疎通確認
        imported = pipeline.import_analysis(str(job_dir / "analysis.json"))
        assert imported["notes"], "取り込みに失敗"

        # コードモードのフルパイプライン
        wav2 = Path(td) / "chords.wav"
        sf.write(
            wav2,
            np.concatenate([synth_chord([45, 48, 52, 57]), synth_chord([40, 44, 47, 52])]),
            SR,
        )
        result2 = pipeline.analyze(str(wav2), mode="chords", chord_style="power")
        assert result2["chords"], "コードモードで何も出ない"
        print(f"  コード出力: {[(c['label'], c['shape']) for c in result2['chords']]}")
    print("test_full_pipeline OK")


def test_ascii_render():
    result = {
        "meta": {"title": "sample", "duration": 4.0, "tempo": 120.0, "mode": "melody"},
        "notes": [
            {"start": 0.0, "end": 0.5, "midi": 64, "string": 3, "fret": 5},
            {"start": 0.5, "end": 1.0, "midi": 67, "string": 3, "fret": 7},
        ],
        "chords": [],
        "beats": [0.0, 0.5, 1.0, 1.5, 2.0],
        "barlines": [0.0, 2.0, 4.0],
    }
    txt = render.score_to_ascii(result)
    assert "5" in txt and "7" in txt
    print(txt)
    print("test_ascii_render OK")


if __name__ == "__main__":
    test_ascii_render()
    test_melody()
    test_polyphony()
    test_mute_filter()
    test_frames()
    test_chords()
    test_full_pipeline()
    print("\nすべてのテストに合格しました")
