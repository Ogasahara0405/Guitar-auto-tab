"""DSP（音声・映像の知覚）のテスト: 採譜ワーカー（worker/）の検証

実行: .venv\\Scripts\\python.exe tests\\test_dsp.py

決定ロジック（弦/フレット割当・ボイシング・映像ゲート・譜面描画）と
契約スキーマのテストは web/tests/（vitest）側にある。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker import audio, chords, melody, tone, video  # noqa: E402

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


def synth_ks(f0, dur=0.8, pick=0.2, damp=0.9965, seed=0, vib_hz=0.0, vib_cents=0.0):
    """テスト用のギター音: Karplus-Strong弦モデルで合成する

    音色学習（tone.py の倍音プロファイル）とは別の方式で合成することで、
    判定が特定の合成条件にだけ依存しないことを確認する。
    """
    rng = np.random.default_rng(seed)
    N = max(2, int(round(SR / f0)))
    buf = rng.uniform(-1.0, 1.0, N)
    pk = max(1, int(N * pick))
    buf = buf - np.roll(buf, pk)  # ピッキング位置による明るさ
    out = np.zeros(int(dur * SR))
    out[:N] = buf
    for i in range(N, len(out)):
        out[i] = damp * 0.5 * (out[i - N] + out[i - N + 1])
    if vib_hz > 0:
        t = np.arange(len(out)) / SR
        rate = 2.0 ** ((vib_cents / 1200.0) * np.sin(2 * np.pi * vib_hz * t))
        read = np.cumsum(rate)
        out = np.interp(read, np.arange(len(out)), out)
    out = out / (np.abs(out).max() + 1e-9)
    return out.astype(np.float32)


def synth_vocal(f0, dur=0.8):
    """テスト用のボーカル風音: フォルマント＋スローアタック＋ビブラート"""
    t = np.arange(int(dur * SR)) / SR
    vib = 25.0 * np.sin(2 * np.pi * 5.2 * t)  # セント
    ph = 2 * np.pi * f0 * np.cumsum(2.0 ** (vib / 1200.0)) / SR
    y = np.zeros_like(t)
    for k in range(1, 14):
        fk = k * f0
        fm = (
            1.0
            + 1.2 * np.exp(-((np.log2(fk / 700.0)) ** 2) / 0.8)
            + 1.0 * np.exp(-((np.log2(fk / 1220.0)) ** 2) / 0.6)
            + 0.7 * np.exp(-((np.log2(fk / 2600.0)) ** 2) / 0.5)
        )
        y += (k ** -0.9) * fm * np.sin(k * ph + 0.3 * k)
    y *= np.minimum(t / 0.12, 1.0)  # スローアタック
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def synth_pad(f0, dur=0.8):
    """テスト用の持続音（パッド）: 減衰しない倍音＋スローアタック"""
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    for k in range(1, 12):
        y += (k ** -1.1) * np.sin(2 * np.pi * k * f0 * t + 0.7 * k)
    y *= np.minimum(t / 0.25, 1.0)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def test_melody():
    """メロディ（単音）の採譜"""
    expected = [45, 48, 50, 52, 55, 57, 55, 52, 50, 48]  # A2 C3 D3 E3 G3 A3 ...
    y = synth_seq(expected)
    notes = melody.extract_notes(y, SR)
    got = [n["midi"] for n in notes]
    print(f"  抽出ノート: {got}")
    assert got == expected, f"メロディ抽出が不一致: {got} != {expected}"
    print("test_melody OK")


def test_repick_split():
    """歪み（コンプレッション）で音量ディップが浅い同音連打も分割されること"""
    SR_ = SR

    def hit(m0, dur=0.45):
        t = np.arange(int(dur * SR_)) / SR_
        f = 440.0 * 2 ** ((m0 - 69) / 12)
        y = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)
        return (0.35 * y * np.exp(-t * 1.2) * np.minimum(t / 0.003, 1)).astype("float32")

    # 同音（E4）を5連打。前の音の減衰と重ねてディップを浅くする（歪みギター風）
    stride = 0.22
    total = int((stride * 5 + 0.5) * SR_)
    y = np.zeros(total, dtype="float32")
    for i in range(5):
        h = hit(64)
        off = int(i * stride * SR_)
        y[off: off + len(h)] += h
    notes = melody.extract_notes(y, SR_)
    ns = [n for n in notes if n["midi"] == 64]
    print(f"  同音連打: {[(round(n['start'], 2), n['midi']) for n in notes]}")
    assert len(ns) >= 4, f"同音連打が分割されていない: {notes}"
    print("test_repick_split OK")


def test_bend_vibrato():
    """チョーキング・深いビブラートで音が細切れにならず、属性として記録されること"""
    SR_ = SR

    def note_glide(m0, semis, dur=0.8):
        t = np.arange(int(dur * SR_)) / SR_
        prog = np.minimum(t / (dur * 0.7), 1.0)
        m = m0 + semis * prog
        f = 440.0 * 2 ** ((m - 69) / 12)
        ph = 2 * np.pi * np.cumsum(f) / SR_
        y = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
        # 末尾は滑らかにフェードして減衰の尾による再検出を防ぐ
        fade = np.minimum((dur - t) / 0.06, 1.0)
        env = np.exp(-t * 1.2) * np.minimum(t / 0.004, 1) * np.maximum(fade, 0.0)
        return (0.35 * y * env).astype("float32")

    def note_vib(m0, dur=1.0, vib_semi=0.5, vib_hz=5.5):
        t = np.arange(int(dur * SR_)) / SR_
        m = m0 + vib_semi * np.sin(2 * np.pi * vib_hz * t)
        f = 440.0 * 2 ** ((m - 69) / 12)
        ph = 2 * np.pi * np.cumsum(f) / SR_
        y = np.sin(ph) + 0.4 * np.sin(2 * ph)
        return (0.35 * y * np.exp(-t * 1.0) * np.minimum(t / 0.004, 1)).astype("float32")

    g = np.zeros(int(0.08 * SR_), dtype="float32")

    # 1) +2半音のチョーキング → 1ノート・bend=+2・開始音高を保持
    r1 = melody.extract_notes(np.concatenate([g, note_glide(64, +2), g]), SR_)
    assert len(r1) == 1, f"チョーキングが細切れになっている: {r1}"
    assert r1[0]["midi"] == 64, f"ベンドの開始音高が不正: {r1}"
    assert abs(r1[0].get("bend", 0) - 2.0) <= 0.5, f"ベンド量が不正: {r1}"

    # 2) 深いビブラート（±0.5半音） → 1ノート・vibrato 属性
    r2 = melody.extract_notes(np.concatenate([g, note_vib(60), g]), SR_)
    assert len(r2) == 1, f"ビブラートで細切れになっている: {r2}"
    assert r2[0]["midi"] == 60
    assert r2[0].get("vibrato") is True, f"ビブラート属性が無い: {r2}"

    print("test_bend_vibrato OK")


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
    print("test_polyphony OK")


def test_mute_filter():
    """ミュート（弾いていない弦）が音声確認で除去されること"""
    # Amの押さえ方のうち 5弦(A2)/4弦(E3)/3弦(A3) だけ鳴らす（2弦・1弦はミュート）
    # 押さえ方 [None,0,2,2,1,0] は web/server/core/voicing.ts の定型フォームと同一
    am_shape = [
        {"string": 5, "fret": 0}, {"string": 4, "fret": 2}, {"string": 3, "fret": 2},
        {"string": 2, "fret": 1}, {"string": 1, "fret": 0},
    ]
    y = synth_chord([45, 52, 57], dur=1.5, strum=0.0)
    kept, muted = chords.filter_muted(y, SR, 0.05, 1.4, am_shape)
    kept_strings = sorted(st["string"] for st in kept)
    print(f"  押さえ方: {am_shape} → 鳴り: {kept_strings} / ミュート: {sorted(muted)}")
    assert kept_strings == [3, 4, 5], f"鳴っている弦の判定が不正: {kept_strings}"
    assert sorted(muted) == [1, 2], f"ミュート判定が不正: {muted}"

    # 全弦鳴っている場合は何も除去されない（Eコード: 40,47,52,56,59,64）
    e_shape = [
        {"string": 6, "fret": 0}, {"string": 5, "fret": 2}, {"string": 4, "fret": 2},
        {"string": 3, "fret": 1}, {"string": 2, "fret": 0}, {"string": 1, "fret": 0},
    ]
    y2 = synth_chord([40, 47, 52, 56, 59, 64], dur=1.5, strum=0.012)
    _kept2, muted2 = chords.filter_muted(y2, SR, 0.05, 1.4, e_shape)
    assert not muted2, f"鳴っている弦を誤ってミュート判定: {muted2}"
    print("test_mute_filter OK")


def test_frames():
    """映像がある場合、ノート位置のフレームが切り出されること"""
    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "clip.mp4")
        ff = audio.get_ffmpeg_exe()
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
    print("test_frames OK")


def test_video_play():
    """映像から演奏動作（ピッキング/ストラム）が検出されること"""
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
        ff = audio.get_ffmpeg_exe()
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
        # web 側のゲート（gate.ts）が使う配列が揃っていること
        assert len(play["times"]) == len(play["energy"]) == len(play["neck_xs"])
    print("test_video_play OK")


def test_fret_markers_diagonal():
    """斜めのネック（指板軸が傾いている）でも黒丸からフレット座標を推定できること"""
    W, H, FPS, DUR = 640, 360, 30, 1.0
    n_frames = int(DUR * FPS)
    frames = np.full((n_frames, H, W, 3), 210, dtype=np.uint8)
    th = np.deg2rad(30.0)
    dx, dy = float(np.cos(th)), float(np.sin(th))
    cx, cy, b = 150.0, 200.0, 500.0

    def pos(f):
        u = b * (1 - 2 ** (-f / 12))
        return cx + dx * u, cy + dy * u

    for f in (3, 5, 7, 9, 12, 15, 17):
        x, y = (int(v) for v in pos(f))
        frames[:, y - 8: y + 8, x - 8: x + 8] = 25  # 黒丸

    with tempfile.TemporaryDirectory() as td:
        src = str(Path(td) / "diag.mp4")
        ff = audio.get_ffmpeg_exe()
        res = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src],
            input=frames.tobytes(), capture_output=True,
        )
        assert res.returncode == 0, f"テスト映像の生成に失敗: {res.stderr[-300:]}"

        fmap = video.analyze_fret_map(src)
        assert fmap, "斜めネックの黒丸から指板座標を推定できない"
        assert abs(fmap["dy"]) > 0.3, f"指板軸が水平に戻ってしまっている: {fmap}"
        # マーカー検出フレーム（480x320）へスケールしてから投影する
        kx, ky = 480.0 / W, 320.0 / H
        for f in (3, 7, 12, 17):
            x, y = pos(f)
            xm, ym = x * kx, y * ky
            u = (xm - fmap["cx"]) * fmap["dx"] + (ym - fmap["cy"]) * fmap["dy"]
            est = fmap["a"] + fmap["b"] * (1 - 2 ** (-f / 12))
            assert abs(u - est) <= 4.0, f"フレット{f}の投影位置がずれている: {u:.1f} vs {est:.1f}"
    print("test_fret_markers_diagonal OK")


def test_fret_markers():
    """指板の黒丸マーカー（3/5/7/9/12/15/17/19/21、12は黒丸2つ）からフレット位置を推定する"""
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
        ff = audio.get_ffmpeg_exe()
        res = subprocess.run(
            [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-pix_fmt", "yuv420p", src],
            input=frames.tobytes(), capture_output=True,
        )
        assert res.returncode == 0 and Path(src).exists(), f"テスト映像の生成に失敗: {res.stderr[-300:]}"

        fmap = video.analyze_fret_map(src)
        assert fmap, "黒丸マーカーから指板座標を推定できない"
        # 2D軸（指板軸）の投影座標で検証する（水平ネックでは軸が水平になる）
        k = 480.0 / W  # マーカー検出フレーム（幅480）へのスケール
        ky = 320.0 / H
        err = []
        for f in (3, 12, 21):
            xm, ym = x_of(f) * k, 178.0 * ky
            u = (xm - fmap["cx"]) * fmap["dx"] + (ym - fmap["cy"]) * fmap["dy"]
            err.append(abs(u - (fmap["a"] + fmap["b"] * (1 - 2 ** (-f / 12)))))
        print(f"  指板座標: a={fmap['a']:.1f} b={fmap['b']:.1f} インライア={fmap['inliers']} 誤差={[round(e, 1) for e in err]}")
        assert max(err) <= 4.0, f"マーカー位置の推定がずれている: {err}"

        play = video.analyze_play(src)
        assert play and play.get("fret_map"), "動作解析にフレット座標が引き継がれていない"

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


def test_tone_model():
    """ギター音色モデル（6弦1F〜1弦22Fの学習）がギター音と無関係な音を区別すること"""
    model = tone.load_model()
    mids = set(int(m) for m in model["midi"])
    assert set(range(41, 87)).issubset(mids), "学習範囲（6弦1F〜1弦22F）が不足している"
    assert 40 in mids, "開放弦が学習されていない"

    # 実機のポジション（6弦1F / 5弦12F / 3弦7F / 2弦14F / 1弦22F）のギター音
    cases = [
        (41, dict(seed=1, pick=0.20)),
        (57, dict(seed=2, pick=0.30)),
        (62, dict(seed=3, pick=0.15)),
        (73, dict(seed=4, pick=0.25)),
        (86, dict(seed=5, pick=0.12)),
    ]
    for midi, kw in cases:
        s = tone.guitar_likelihood(synth_ks(midi_to_f0(midi), **kw), SR, midi)
        print(f"  ギター midi={midi}: {s:.3f}")
        assert s >= 0.55, f"ギター音が弾き出されない: midi={midi} score={s:.3f}"

    # ビブラート付きのリードも落とさないこと
    s_vib = tone.guitar_likelihood(
        synth_ks(midi_to_f0(73), seed=6, pick=0.2, vib_hz=5.5, vib_cents=35), SR, 73
    )
    print(f"  ギター(ビブラート) midi=73: {s_vib:.3f}")
    assert s_vib >= 0.55, f"ビブラート付きのギター音が弾き出されない: {s_vib:.3f}"

    # 無関係な音（ボーカル風・持続音・ノイズ）は弾き出されること
    noise = np.random.default_rng(7).uniform(-1, 1, int(0.8 * SR)).astype(np.float32)
    for name, sig in (
        ("ボーカル風", synth_vocal(midi_to_f0(57))),
        ("持続音(パッド)", synth_pad(midi_to_f0(57))),
        ("ノイズ", noise),
    ):
        s = tone.guitar_likelihood(sig, SR, 57)
        print(f"  {name}: {s:.3f}")
        assert s < 0.50, f"無関係な音がギターとして残る: {name} score={s:.3f}"
    print("test_tone_model OK")


def test_chords_extract():
    """コード（バッキング）の抽出"""
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
    print("test_chords_extract OK")


def _run_worker(*args, stdin: str | None = None) -> dict:
    root = Path(__file__).resolve().parents[1]
    # worker は常にUTF-8で出力するため、デコードを明示する（コンソールcp932依存の回避）
    res = subprocess.run(
        [sys.executable, "-m", "worker", *args],
        cwd=str(root),
        input=(stdin.encode("utf-8") if stdin is not None else None),
        capture_output=True,
    )
    out = res.stdout.decode("utf-8", errors="replace")
    err = res.stderr.decode("utf-8", errors="replace")
    assert res.returncode == 0, f"worker {args[0]} が失敗: {err[-500:]}"
    # 結果JSONは __GAT_JSON__ マーカー行の後ろに置かれる（ノイズ耐性のため）。
    # web/server/worker/client.ts の parseWorkerOutput と同じ規則で解析する
    # （行頭アンカーで探すことで、JSONペイロード内に同文字列が含まれても誤検出しない）。
    from worker.__main__ import JSON_MARKER

    anchor = "\n" + JSON_MARKER
    idx = out.rfind(anchor)
    if idx >= 0:
        line = out[idx + len(anchor):]
    elif out.startswith(JSON_MARKER):
        line = out[len(JSON_MARKER):]
    else:
        line = out.strip().splitlines()[-1]
    return json.loads(line.split("\n", 1)[0].strip())


def test_worker_cli():
    """ワーカーCLI（web/ から呼ばれるJSON契約）の疎通確認"""
    with tempfile.TemporaryDirectory() as td:
        # acquire --file
        wav = Path(td) / "melody.wav"
        sf.write(wav, synth_seq([45, 48, 50, 52]), SR)
        acq = _run_worker("acquire", "--file", str(wav), "--out", td)
        assert set(acq) == {"wav", "title", "media"}, f"acquire の契約が不正: {acq}"
        assert Path(td, acq["wav"]).exists() and Path(td, acq["media"]).exists()

        # perceive --mode melody（音源分離はこのテストでは無効化して高速に確認）
        perc = _run_worker("perceive", "--src", str(Path(td) / acq["media"]), "--out", td,
                           "--mode", "melody", "--no-separate")
        for key in ("duration", "tempo", "chords_tempo", "separated", "mode", "audio_file",
                    "notes", "chords", "play", "beats", "barlines"):
            assert key in perc, f"perceive に {key} がない: {sorted(perc)}"
        got = [n["midi"] for n in perc["notes"]]
        print(f"  perceive のメロディ: {got}")
        assert got == [45, 48, 50, 52], f"perceive のメロディが不一致: {got}"
        assert all("tone" in n for n in perc["notes"]), "tone スコアが付いていない"

        # frames（時刻指定のフレーム抽出）— 映像が無くても契約どおり空で返る
        fr = _run_worker("frames", "--src", str(Path(td) / acq["media"]), "--out", td,
                         "--times", "-", stdin="[0.1, 0.5]")
        assert "frames" in fr, f"frames の契約が不正: {fr}"

        # verify-mutes
        req = json.dumps([{
            "start": 0.05, "end": 1.4,
            "shape": [{"string": 5, "fret": 0}, {"string": 4, "fret": 2},
                      {"string": 3, "fret": 2}, {"string": 2, "fret": 1},
                      {"string": 1, "fret": 0}],
        }])
        mute_wav = Path(td) / "chord.wav"
        sf.write(mute_wav, synth_chord([45, 52, 57], dur=1.5, strum=0.0), SR)
        mut = _run_worker("verify-mutes", "--audio", str(mute_wav), "--request", "-", stdin=req)
        assert mut.get("muted") == [[1, 2]], f"verify-mutes の結果が不正: {mut}"

        # コンソールエンコード非依存（μ 等のcp932外の文字を含むタイトル）
        tricky = Path(td) / "test_µ's_song.wav"
        sf.write(tricky, synth_seq([45, 48]), SR)
        acq2 = _run_worker("acquire", "--file", str(tricky), "--out", td)
        assert "µ" in acq2["title"] or "μ" in acq2["title"], f"タイトルの特殊文字が化けた: {acq2}"
    print("test_worker_cli OK")


if __name__ == "__main__":
    test_melody()
    test_bend_vibrato()
    test_repick_split()
    test_polyphony()
    test_mute_filter()
    test_frames()
    test_video_play()
    test_fret_markers()
    test_fret_markers_diagonal()
    test_tone_model()
    test_chords_extract()
    test_worker_cli()
    print("\nすべてのDSPテストに合格しました")
