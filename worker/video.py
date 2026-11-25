"""映像の知覚: フレーム抽出・演奏動作解析・指板マーカー校正

どの弦を弾いているかは映像のブリッジ側から確認できるため、
採譜した各ノートの開始時刻に合わせてフレーム画像を切り出す（extract_frames）。
映像の演奏動作（ピッキング/ストラム）と指板の黒丸マーカーからは
play データ（動きの包絡線・動作イベント・ネック横位置・フレット座標）を
計算して返す（analyze_play）。ノートの選別（ゲート）やフレット割当は
この play データを使って web 側（web/server/core/gate.ts）が行う。
"""
import os
import re
import subprocess

import numpy as np

from . import audio

# 同一視するフレーム間隔（この範囲のイベントは同じフレームを参照）
FRAME_DUP_SEC = 0.25
MAX_FRAMES = 400


def has_video(path: str) -> bool:
    """ファイルに映像ストリームが含まれるか（ffprobe不要・ffmpegの出力から判定）"""
    if not path or not os.path.exists(path):
        return False
    try:
        ff = audio.get_ffmpeg_exe()
        res = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True)
        return bool(re.search(r"^\s*Stream #.*Video:", res.stderr, re.MULTILINE))
    except Exception:
        return False


def extract_frames(src: str, times, outdir: str, max_frames: int = MAX_FRAMES) -> dict:
    """指定時刻（秒）のフレームをJPEGで切り出す。

    戻り値: {時刻(秒, 小数2桁): ファイル名}。映像が無い/失敗時は {}。
    フレーム数が max_frames を超える場合は等間隔に間引く。
    """
    if not has_video(src):
        return {}
    os.makedirs(outdir, exist_ok=True)
    ff = audio.get_ffmpeg_exe()

    uniq = sorted({round(float(t), 2) for t in times if t is not None and float(t) >= 0})
    if not uniq:
        return {}
    # 近接する時刻は同じフレームにまとめる
    picked = []
    for t in uniq:
        if not picked or t - picked[-1] >= FRAME_DUP_SEC:
            picked.append(t)
    uniq = picked
    if len(uniq) > max_frames:
        step = len(uniq) / max_frames
        uniq = sorted({uniq[int(i * step)] for i in range(max_frames)})

    out = {}
    for t in uniq:
        name = f"frame_{t:07.2f}.jpg"
        dst = os.path.join(outdir, name)
        if not os.path.exists(dst):
            cmd = [
                ff, "-y", "-ss", f"{t:.3f}", "-i", src,
                "-frames:v", "1", "-q:v", "4", "-vf", "scale='min(1280,iw)':-2",
                dst,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not os.path.exists(dst):
                continue
        out[round(t, 2)] = name
    return out


# --- 映像動作解析: 映像を主・音声を従にしてタブを出力するための演奏動作検出 ---
MOTION_FPS = 12          # 動き解析のサンプリングレート
MOTION_W, MOTION_H = 320, 240
EVENT_PEAK_RATIO = 0.30  # ピッキング/ストラムのイベント検出閾値（p90比）
EVENT_MIN_DIST = 0.15    # 動作イベント間の最小間隔（秒）

# --- フレットポジションマーク（指板の黒丸）からフレット位置を推定 ---
# 黒丸があるフレット: 3, 5, 7, 9, 12, 15, 17, 19, 21（12フレットのみ黒丸2つ）
# 映像で黒丸が見えているとナット〜ブリッジの座標を校正でき、
# 演奏中の左手の位置から「何フレットを弾いているか」を推定できる。
MARKER_FRETS = (3, 5, 7, 9, 12, 15, 17, 19, 21)
MARKER_W, MARKER_H = 480, 320  # マーカー検出フレーム（検出座標はこの幅基準）
MARKER_SAMPLES = 6             # 動画全体から等間隔にサンプリングする枚数
MARKER_MIN_DOTS = 3            # 信頼するのに必要なマーカー数
DOT_AREA = (6, 400)            # 黒丸1つの画素数の範囲
DOT_FIT_TOL = 3.5              # スケール長モデルに合う許容誤差（ピクセル）
NECK_PAD = 0.05                # ネック領域のナット側の余裕（スケール長比）
NECK_FRAC = 0.75               # ネック領域のブリッジ側の端（スケール長比）


def analyze_play(src: str, fps: int = MOTION_FPS) -> dict | None:
    """映像から演奏動作（ピッキング/ストラム）を検出する。

    フレーム差分で動きの強度と位置を推定し、
    - times/energy: 動きの包絡線（ノートの映像的な裏付け判定に使う）
    - events: 動作のピーク（ピッキング/ストラム）と縦位置・広がり
    を返す。映像が無ければ None。
    「映像に忠実なタブ」のための根拠で、音声より先にこれを確認する。
    """
    if not has_video(src):
        return None
    # 指板の黒丸マーカーが見えている場合はフレット座標を校正しておく（無ければNone）
    fmap = analyze_fret_map(src)
    neck = None
    if fmap:
        kx = MOTION_W / float(fmap["w"])
        # 指板軸（斜めでも可）上のネック領域を x 範囲に変換する
        u0 = fmap["a"] - NECK_PAD * fmap["b"]
        u1 = fmap["a"] + NECK_FRAC * fmap["b"]
        x0 = fmap["cx"] + fmap["dx"] * u0
        x1 = fmap["cx"] + fmap["dx"] * u1
        neck = (min(x0, x1) * kx, max(x0, x1) * kx)
    ff = audio.get_ffmpeg_exe()
    cmd = [
        ff, "-i", src,
        "-vf", f"fps={fps},scale={MOTION_W}:{MOTION_H}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    frame_size = MOTION_W * MOTION_H
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 6)
    except Exception:
        return None

    times: list = []
    energy: list = []
    ys: list = []
    widths: list = []
    neck_xs: list = []
    neck_ys: list = []
    row_hist = np.zeros(MOTION_H, dtype=np.float64)
    prev = None
    i = 0
    try:
        while True:
            buf = proc.stdout.read(frame_size)
            if not buf or len(buf) < frame_size:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(MOTION_H, MOTION_W)
            if prev is not None:
                d = np.abs(frame.astype(np.int16) - prev.astype(np.int16))
                thr = max(10.0, float(np.median(d)) * 3.0)
                act = d > thr
                rows = act.sum(axis=1).astype(float)  # 行ごとの動きの量
                n_act = int(act.sum())
                # ネック側の動き（押弦中の左手）の位置 = 何フレットあたりかの手がかり
                x_neck = float("nan")
                y_neck = float("nan")
                if neck is not None and n_act:
                    xi0 = max(int(neck[0]), 0)
                    xi1 = min(int(neck[1]) + 1, MOTION_W)
                    if xi1 - xi0 >= 8:
                        sub = act[:, xi0:xi1]
                        if int(sub.sum()) >= 8:
                            col = sub.sum(axis=0).astype(float)
                            x_neck = float((col * np.arange(xi0, xi1)).sum() / col.sum())
                            row = sub.sum(axis=1).astype(float)
                            y_neck = float((row * np.arange(MOTION_H)).sum() / row.sum())
                if n_act:
                    row_hist += rows
                    total = float(rows.sum())
                    y_c = float((rows * np.arange(MOTION_H)).sum() / total)
                    csum = np.cumsum(rows)
                    lo = int(np.searchsorted(csum, 0.05 * total))
                    hi = int(np.searchsorted(csum, 0.95 * total))
                    width = float(max(hi - lo, 1))
                else:
                    y_c, width = float("nan"), 0.0
                times.append(i / fps)
                energy.append(n_act / frame_size)
                ys.append(y_c)
                widths.append(width)
                neck_xs.append(x_neck)
                neck_ys.append(y_neck)
            prev = frame
            i += 1
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass

    if not times:
        return None

    e = np.asarray(energy, dtype=float)
    p90 = float(np.percentile(e, 90))

    # 弦が通る帯（動きが観測された縦範囲）。弦1本分の幅の目安にする
    band = None
    total_rows = float(row_hist.sum())
    if total_rows > 0:
        c = np.cumsum(row_hist)
        y0 = int(np.searchsorted(c, 0.02 * total_rows))
        y1 = int(np.searchsorted(c, 0.98 * total_rows))
        band = (y0, max(y1, y0 + 1))
    band_span = float(band[1] - band[0]) if band else 0.0
    unit = band_span / 6.0 if band_span >= 6.0 else 0.0  # 弦1本分のピクセル幅

    # 動作イベント（ピッキング/ストラム）= 強い動きのピーク
    events = []
    if p90 > 0:
        idx = np.where(e >= EVENT_PEAK_RATIO * p90)[0]
        runs = []
        for k in idx:
            if runs and k == runs[-1][-1] + 1:
                runs[-1].append(int(k))
            else:
                runs.append([int(k)])
        for run in runs:
            k = run[int(np.argmax(e[run]))]
            t = float(times[k])
            if events and t - events[-1]["t"] < EVENT_MIN_DIST:
                if e[k] > events[-1]["strength"]:
                    events[-1] = {"t": t, "strength": float(e[k]), "y": ys[k], "width": widths[k]}
                continue
            events.append({"t": t, "strength": float(e[k]), "y": ys[k], "width": widths[k]})
        for ev in events:
            # 広がりを「弦何本分」で表す（1.0未満 ≒ 単弦のピッキング）
            ev["units"] = round(ev["width"] / unit, 2) if unit > 0 else 99.0

    return {
        "times": [float(t) for t in times],
        "energy": [float(v) for v in e],
        "events": events,
        "band": band,
        "p90": p90,
        "neck_xs": [float(v) for v in neck_xs],
        "neck_ys": [float(v) for v in neck_ys],
        "fret_map": fmap,
    }


# --- フレットポジションマーク（指板の黒丸）検出とフレット推定 ---
def _scale_u(n: float) -> float:
    """ナットからの距離（スケール長比）: フレット n の位置 = 1 - 2^(-n/12)"""
    return 1.0 - 2.0 ** (-float(n) / 12.0)


def _probe_duration(src: str) -> float:
    """動画の長さ（秒）を取得する（失敗時は 0）"""
    try:
        ff = audio.get_ffmpeg_exe()
        res = subprocess.run([ff, "-hide_banner", "-i", src], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def _gray_frame(src: str, t: float, w: int = MARKER_W, h: int = MARKER_H):
    """時刻 t のフレームをグレースケールのnumpy配列で得る（失敗時は None）"""
    ff = audio.get_ffmpeg_exe()
    cmd = [
        ff, "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or len(res.stdout) < w * h:
        return None
    return np.frombuffer(res.stdout[: w * h], dtype=np.uint8).reshape(h, w)


def _detect_dots(gray) -> list:
    """指板の黒丸（暗い丸状の領域）を検出する → [(x, y, area), ...]"""
    img = gray.astype(np.float32)
    k = 7
    pad = np.pad(img, k // 2, mode="edge")
    integral = np.pad(pad, ((1, 0), (1, 0)), mode="edge").cumsum(0).cumsum(1)
    box = (integral[k:, k:] - integral[:-k, k:] - integral[k:, :-k] + integral[:-k, :-k]) / (k * k)
    mask = ((box - img) > 9.0) & (img < float(np.percentile(img, 70)))
    h, w = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    dots = []
    for y0 in range(h):
        for x0 in np.nonzero(mask[y0] & ~seen[y0])[0]:
            x0 = int(x0)
            if seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            pts = []
            while stack:
                y, x = stack.pop()
                pts.append((y, x))
                if len(pts) > DOT_AREA[1]:
                    break
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            area = len(pts)
            if not (DOT_AREA[0] <= area <= DOT_AREA[1]):
                continue
            ys = [p[0] for p in pts]
            xs = [p[1] for p in pts]
            bw = max(xs) - min(xs) + 1
            bh = max(ys) - min(ys) + 1
            if not (0.4 <= bw / bh <= 2.5):
                continue
            if area / (bw * bh) < 0.45:  # 丸っぽさ（細長い領域・輪郭だけの領域を除外）
                continue
            dots.append((float(np.mean(xs)), float(np.mean(ys)), area))
    return dots


def _fit_fret_map(dots: list) -> dict | None:
    """黒丸の画素位置から指板の軸（斜めのネックでも可）とナット位置 a・スケール長 b を推定する。

    モデル: 指板軸上の座標 u(n) = a + b * (1 - 2^(-n/12))
    （フレットが高くなるほど間隔が 2^(-n/12) で詰まるギターの物理配置）
    黒丸はネック上にほぼ一直線に並ぶため、まず主成分分析で指板軸（単位ベクトル
    dx,dy）と原点（重心 cx,cy）を決め、軸に投影した1次元座標 u で格子当てを行う。
    水平なネックでは軸が水平になり、従来の x 座標フィットに一致する。
    2つの黒丸がどのフレットのマークかの組み合わせを仮定して候補を作り、
    その格子に乗る黒丸の数（インライア）が最大のものを最小二乗で採る。
    """
    if len(dots) < MARKER_MIN_DOTS:
        return None
    # 黒丸はネック上（画面上部側）にある。画面下のタブ表示領域など
    # 他の暗い領域を誤検出した場合は候補から外す
    pts = sorted(((float(x), float(y)) for x, y, _ in dots), key=lambda p: p[0])[:12]
    pts = [(x, y) for x, y in pts if y < 200.0]
    if len(pts) < MARKER_MIN_DOTS:
        return None
    xy = np.array([[x, y] for x, y in pts], dtype=float)
    # 指板軸: 重心まわりの主成分（分散最大方向 = ネックの向き）
    c = xy.mean(axis=0)
    cov = np.cov((xy - c).T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    d = eigvecs[:, int(np.argmax(eigvals))]
    if d[0] < 0:
        d = -d  # ナット側（x 小さい）を正の向きに揃える
    u_pts = (xy - c) @ d  # 軸に投影した1次元座標
    # 物理的妥当性: ネック軸がほぼ垂直（誤検出ドットの直線配列など）の場合は棄却する
    if abs(float(d[1])) > 0.85:
        return None
    us = {n: _scale_u(n) for n in MARKER_FRETS}

    def fit(a: float, b: float):
        if b < 30.0:  # スケール長は正（軸の向きはフレットが増える向き）
            return None
        inliers = []
        for k, u in enumerate(u_pts):
            best_d, best_n = None, None
            for n, uu in us.items():
                dd = abs(u - (a + b * uu))
                if best_d is None or dd < best_d:
                    best_d, best_n = dd, n
            if best_d <= DOT_FIT_TOL:
                inliers.append((float(u), best_n))
        if len(inliers) < MARKER_MIN_DOTS:
            return None
        A = np.array([[1.0, us[n]] for _u, n in inliers])
        uv = np.array([u for u, _n in inliers])
        sol, *_ = np.linalg.lstsq(A, uv, rcond=None)
        a2, b2 = float(sol[0]), float(sol[1])
        if b2 < 30.0:
            return None
        resid = float(np.mean([abs(u - (a2 + b2 * us[n])) for u, n in inliers]))
        if resid > DOT_FIT_TOL:
            return None
        return {
            "a": a2,
            "b": b2,
            "cx": float(c[0]),
            "cy": float(c[1]),
            "dx": float(d[0]),
            "dy": float(d[1]),
            "inliers": len(inliers),
            "residual": round(resid, 3),
        }

    best = None
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            du = float(u_pts[j] - u_pts[i])
            if abs(du) < 1e-6:
                continue
            for f1 in MARKER_FRETS:
                for f2 in MARKER_FRETS:
                    if f1 == f2:
                        continue
                    b = du / (us[f2] - us[f1])
                    if b < 30.0:  # スケール長は正（フレットが増える向きに軸を取る）
                        continue
                    r = fit(float(u_pts[i]) - b * us[f1], b)
                    if r and (
                        best is None
                        or (r["inliers"], -r["residual"]) > (best["inliers"], -best["residual"])
                    ):
                        best = r
    return best


def analyze_fret_map(src: str) -> dict | None:
    """映像からフレットポジションマークを探し、指板の座標系を推定する。

    見えている黒丸（3/5/7/9/12/15/17/19/21フレット）の並びがフレットの
    物理配置に合う場合のみ {"a", "b", "w", ...} を返す（a=ナット位置、
    b=スケール長、w=基準フレーム幅）。検出できなければ None。
    """
    if not has_video(src):
        return None
    dur = _probe_duration(src)
    if dur <= 0:
        return None
    best = None
    for i in range(MARKER_SAMPLES):
        t = dur * (i + 0.5) / MARKER_SAMPLES
        gray = _gray_frame(src, t)
        if gray is None:
            continue
        dots = _detect_dots(gray)
        if len(dots) < MARKER_MIN_DOTS:
            continue
        fmap = _fit_fret_map(dots)
        if fmap and (
            best is None
            or (fmap["inliers"], -fmap["residual"]) > (best["inliers"], -best["residual"])
        ):
            fmap["w"] = int(gray.shape[1])
            fmap["h"] = int(gray.shape[0])
            best = fmap
    return best
