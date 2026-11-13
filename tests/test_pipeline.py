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


def test_api_contract():
    """APIスキーマ（app/schemas.py）と frontend/openapi.json の同期チェック

    言語をまたぐ型契約のずれを検出する。失敗したら
    `.venv\\Scripts\\python.exe app\\export_openapi.py` を実行してコミットする。
    """
    import json

    from app.main import app

    root = Path(__file__).resolve().parents[1]
    saved_path = root / "frontend" / "openapi.json"
    assert saved_path.exists(), "frontend/openapi.json がありません（app/export_openapi.py を実行してください）"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    current = app.openapi()
    assert saved == current, (
        "APIスキーマが frontend/openapi.json とずれています。"
        "`.venv\\Scripts\\python.exe app\\export_openapi.py` を実行し、"
        "npm run build（gen:api）で TS 型を再生成してください"
    )
    types_path = root / "frontend" / "src" / "api-types.ts"
    assert types_path.exists(), "frontend/src/api-types.ts がありません（npm run gen:api を実行してください）"
    print("test_api_contract OK")


def test_video_gate():
    """映像に忠実な選別: 動作のない位置のノートは除去され、映像の弦位置が割当に反映される"""
    import subprocess
    from app.core import audio as core_audio

    W, H, FPS, DUR = 320, 240, 30, 4.0
    n_frames = int(DUR * FPS)
    frames = np.zeros((n_frames, H, W, 3), dtype=np.uint8)
    frames[:, 100:124, 100:124] = 255  # 常に静止している物体（動作にならない）

    def move_square(t0, t1, x0, y0, dx):
        for f in range(int(t0 * FPS), int(t1 * FPS)):
            x = x0 + (f - int(t0 * FPS)) * dx
            frames[f, y0: y0 + 24, x: x + 24] = 255

    move_square(0.5, 0.9, 60, 24, 6)    # 動作バースト1（画面上側）
    move_square(1.8, 2.2, 200, 160, 6)  # 動作バースト2（画面下側）
    # 2.6〜3.6秒は無動作（関係ない音が混ざる区間の想定）

    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "clip.mp4")
        ff = core_audio.get_ffmpeg_exe()
        res = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src],
            input=frames.tobytes(), capture_output=True,
        )
        assert res.returncode == 0 and Path(src).exists(), f"テスト映像の生成に失敗: {res.stderr[-300:]}"

        play = video.analyze_play(src)
        assert play and play["p90"] > 0, "映像動作を解析できない"
        evs = [(round(e["t"], 2), round(e["units"], 1)) for e in play["events"]]
        print(f"  映像イベント(時刻, 弦本数換算の広がり): {evs}")
        assert any(0.4 <= t <= 1.1 for t, _ in evs), f"動作バースト1が検出されない: {evs}"
        assert any(1.7 <= t <= 2.4 for t, _ in evs), f"動作バースト2が検出されない: {evs}"
        assert not any(2.7 <= t <= 3.5 for t, _ in evs), f"無動作区間にイベントがある: {evs}"

        notes = [
            {"start": 0.7, "end": 1.0, "midi": 52, "evidence": 1.0},
            {"start": 2.0, "end": 2.3, "midi": 64, "evidence": 1.0},
            {"start": 3.1, "end": 3.4, "midi": 57, "evidence": 1.0},  # 映像で演奏なし
        ]
        kept, info = video.gate_notes(notes, play)
        got = sorted(round(n["start"], 2) for n in kept)
        print(f"  採用: {got} / 除去: {info['dropped']}")
        assert got == [0.7, 2.0], f"映像に忠実な選別になっていない: {got}"
        assert info["dropped"] == 1, f"除去数が不正: {info}"

        # 単弦ピッキングの映像に3声が乗った場合は弱い声を落とす
        voice_notes = [
            {"start": 0.70, "end": 1.0, "midi": 52, "evidence": 1.0},
            {"start": 0.72, "end": 1.0, "midi": 57, "evidence": 1.0},
            {"start": 0.74, "end": 1.0, "midi": 59, "evidence": 0.3},
        ]
        kept_v, _ = video.gate_notes(voice_notes, play)
        got_v = sorted(round(n["start"], 2) for n in kept_v)
        print(f"  声の絞り込み後: {got_v}")
        assert got_v == [0.70, 0.72], f"弱い声が残っている: {got_v}"

        # 映像の弦レーン（上/下で別の弦）が弦割当に反映される
        lane_notes = [
            {"start": 0.7, "end": 1.0, "midi": 52, "evidence": 1.0},
            {"start": 2.0, "end": 2.3, "midi": 52, "evidence": 1.0},
        ]
        kept_l, info_l = video.gate_notes(lane_notes, play)
        assert len(info_l["lane_hints"]) == 2, f"弦レーンの手がかりがない: {info_l}"
        assigned = tabassign.assign_frets(kept_l, lane_hints=info_l["lane_hints"])
        strs = [n["string"] for n in assigned]
        print(f"  レーン反映後のタブ: {[(n['string'], n['fret']) for n in assigned]}")
        for n in assigned:
            open_midi = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}[n["string"]]
            assert open_midi + n["fret"] == n["midi"], f"フレット割当が不正: {n}"
        assert len(set(strs)) == 2, f"映像で別の弦を弾いているのに同じ弦になった: {assigned}"

        # 映像に動きがない（情報がない）場合は選別しない（安全側）
        static = np.zeros((n_frames, H, W, 3), dtype=np.uint8)
        static[:, 100:124, 100:124] = 255
        src2 = str(Path(td) / "static.mp4")
        res2 = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src2],
            input=static.tobytes(), capture_output=True,
        )
        assert res2.returncode == 0, f"静止映像の生成に失敗: {res2.stderr[-300:]}"
        play_s = video.analyze_play(src2)
        kept_s, info_s = video.gate_notes(notes, play_s)
        assert len(kept_s) == 3 and info_s["dropped"] == 0, f"動作のない映像で誤って除去: {info_s}"
    print("test_video_gate OK")


def test_fret_markers():
    """指板の黒丸マーカー（3/5/7/9/12/15/17/19/21、12は黒丸2つ）からフレット位置を推定する"""
    import subprocess
    from app.core import audio as core_audio

    W, H, FPS, DUR = 640, 360, 30, 4.0
    n_frames = int(DUR * FPS)
    frames = np.full((n_frames, H, W, 3), 210, dtype=np.uint8)  # 明るい指板
    nut_x, scale_px = 40.0, 580.0

    def x_of(f):
        return nut_x + scale_px * (1 - 2 ** (-f / 12))

    for f in (3, 5, 7, 9, 15, 17, 19, 21):
        x = int(x_of(f))
        frames[:, 170:186, x - 8: x + 8] = 25  # 黒丸
    x12 = int(x_of(12))
    frames[:, 150:166, x12 - 8: x12 + 8] = 25   # 12フレットは黒丸2つ
    frames[:, 190:206, x12 - 8: x12 + 8] = 25

    def move_square(t0, t1, cx, y0=170):
        # 小刻みに往復させ、位置を変えずに動き続ける（位置の中心 = 弾いているフレット）
        for f in range(int(t0 * FPS), int(t1 * FPS)):
            x = int(cx) + (6 if (f // 2) % 2 == 0 else -6)
            frames[f, y0: y0 + 24, x: x + 24] = 30

    move_square(0.5, 0.9, x_of(7) - 12)    # 7フレット付近で演奏
    move_square(1.8, 2.2, x_of(17) - 12)   # 17フレット付近で演奏

    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "clip.mp4")
        ff = core_audio.get_ffmpeg_exe()
        res = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src],
            input=frames.tobytes(), capture_output=True,
        )
        assert res.returncode == 0 and Path(src).exists(), f"テスト映像の生成に失敗: {res.stderr[-300:]}"

        fmap = video.analyze_fret_map(src)
        assert fmap, "黒丸マーカーから指板座標を推定できない"
        k = 480.0 / W  # マーカー検出フレーム（幅480）へのスケール
        err = [
            abs((fmap["a"] + fmap["b"] * (1 - 2 ** (-f / 12))) - x_of(f) * k)
            for f in (3, 12, 21)
        ]
        print(f"  指板座標: a={fmap['a']:.1f} b={fmap['b']:.1f} インライア={fmap['inliers']} 誤差={[round(e, 1) for e in err]}")
        assert max(err) <= 4.0, f"マーカー位置の推定がずれている: {err}"

        play = video.analyze_play(src)
        assert play and play.get("fret_map"), "動作解析にフレット座標が引き継がれていない"
        notes = [
            {"start": 0.7, "end": 1.0, "midi": 52, "evidence": 1.0},   # 7フレット付近で演奏
            {"start": 2.0, "end": 2.3, "midi": 64, "evidence": 1.0},   # 17フレット付近で演奏
        ]
        kept, info = video.gate_notes(notes, play)
        fh = info["fret_hints"]
        print(f"  フレット推定: {fh}")
        assert abs(fh.get(0.7, 99) - 7) <= 1.5, f"7フレット付近の推定がずれている: {fh}"
        assert abs(fh.get(2.0, 99) - 17) <= 1.5, f"17フレット付近の推定がずれている: {fh}"

        # マーカーのフレット位置が割当に反映される（音声だけなら開放弦寄りになる音高）
        assigned = tabassign.assign_frets(kept, fret_hints=fh)
        by = {round(n["start"], 2): n for n in assigned}
        n1, n2 = by[0.7], by[2.0]
        print(f"  マーカー反映後のタブ: {[(round(n['start'], 1), n['string'], n['fret']) for n in assigned]}")
        assert abs(n1["fret"] - 7) <= 2, f"7フレットの割当が反映されていない: {n1}"
        assert abs(n2["fret"] - 17) <= 2, f"17フレットの割当が反映されていない: {n2}"
        for n in assigned:
            open_midi = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}[n["string"]]
            assert open_midi + n["fret"] == n["midi"], f"フレット割当が不正: {n}"

        # マーカーが無い映像では推定が発生しない（従来どおりの音声側の割当）
        static = np.full((n_frames, H, W, 3), 210, dtype=np.uint8)
        src2 = str(Path(td) / "nomark.mp4")
        res2 = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src2],
            input=static.tobytes(), capture_output=True,
        )
        assert res2.returncode == 0
        assert video.analyze_fret_map(src2) is None, "マーカーの無い映像で誤って検出"
    print("test_fret_markers OK")


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
    test_video_gate()
    test_fret_markers()
    test_chords()
    test_api_contract()
    test_full_pipeline()
    print("\nすべてのテストに合格しました")
