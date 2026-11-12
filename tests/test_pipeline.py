"""パイプライン自己テスト: 既知の音を合成して採譜→タブ変換を検証する
実行: .venv\\Scripts\\python.exe tests\\test_pipeline.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import melody, tabassign, voicing, chords, render, pipeline  # noqa: E402

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
    test_chords()
    test_full_pipeline()
    print("\nすべてのテストに合格しました")
