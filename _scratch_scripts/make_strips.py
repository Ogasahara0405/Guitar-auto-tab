import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
import numpy as np
from PIL import Image
import os
import json

SRC = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes"
OUT = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes_zoom"

LINE_Y = [69, 84, 98, 112, 127, 141]  # s1..s6


def detect_frame(path):
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    g = arr.mean(axis=2)

    r, b = arr[:, :, 0], arr[:, :, 2]
    orange = (r - b > 12) & (r > 55)
    col_score = orange.sum(axis=0)
    cursor_x = None
    best = col_score.max()
    if best > 30:
        cands = np.where(col_score >= best - 5)[0]
        cursor_x = int(round(cands.mean()))

    band = g[60:155, :]
    mask = band > 70
    row_frac = mask.mean(axis=1)
    for y in range(mask.shape[0]):
        if row_frac[y] > 0.5:
            mask[y, :] = False

    lab = -np.ones(mask.shape, dtype=np.int32)
    comps = []
    ys, xs = np.where(mask)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0] != -1:
            continue
        idx = len(comps)
        stack = [(y0, x0)]
        lab[y0, x0] = idx
        pix = []
        while stack:
            cy, cx = stack.pop()
            pix.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1]:
                        if mask[ny, nx] and lab[ny, nx] == -1:
                            lab[ny, nx] = idx
                            stack.append((ny, nx))
        comps.append(pix)

    blobs = []
    for pix in comps:
        pys = [p[0] + 60 for p in pix]
        pxs = [p[1] for p in pix]
        x_min, x_max = min(pxs), max(pxs)
        y_min, y_max = min(pys), max(pys)
        area = len(pix)
        w = x_max - x_min + 1
        h = y_max - y_min + 1
        # skip bar lines: tall thin
        if h > 55 and w < 6:
            continue
        if area < 12:
            continue
        if w > 50:
            continue
        blobs.append({
            "x0": int(x_min), "x1": int(x_max),
            "y0": int(y_min), "y1": int(y_max),
            "cx": float((x_min + x_max) / 2),
            "cy": float((y_min + y_max) / 2),
            "area": int(area),
        })
    blobs.sort(key=lambda b: b["cx"])
    return cursor_x, blobs


def merge_digits(blobs):
    """Merge fragments into digits: same x-range overlap and y proximity."""
    used = [False] * len(blobs)
    digits = []
    for i, b in enumerate(blobs):
        if used[i]:
            continue
        used[i] = True
        x0, x1, y0, y1 = b["x0"], b["x1"], b["y0"], b["y1"]
        area = b["area"]
        changed = True
        while changed:
            changed = False
            for j, c in enumerate(blobs):
                if used[j]:
                    continue
                # overlap in x or gap <= 2, and y overlap or gap <= 3
                if (c["x0"] <= x1 + 2 and c["x1"] >= x0 - 2) and (c["y0"] <= y1 + 3 and c["y1"] >= y0 - 3):
                    used[j] = True
                    x0 = min(x0, c["x0"]); x1 = max(x1, c["x1"])
                    y0 = min(y0, c["y0"]); y1 = max(y1, c["y1"])
                    area += c["area"]
                    changed = True
        digits.append({
            "x0": x0, "x1": x1, "y0": y0, "y1": y1,
            "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
            "area": area,
        })
    # second pass: merge adjacent digits of 2-digit numbers (same y, x gap <= 2, width each < 12)
    used = [False] * len(digits)
    merged = []
    for i, d in enumerate(digits):
        if used[i]:
            continue
        used[i] = True
        x0, x1, y0, y1 = d["x0"], d["x1"], d["y0"], d["y1"]
        area = d["area"]
        changed = True
        while changed:
            changed = False
            for j, c in enumerate(digits):
                if used[j]:
                    continue
                if (c["x0"] <= x1 + 2 and c["x1"] >= x0 - 2) and abs(c["cy"] - (y0 + y1) / 2) < 5:
                    used[j] = True
                    x0 = min(x0, c["x0"]); x1 = max(x1, c["x1"])
                    y0 = min(y0, c["y0"]); y1 = max(y1, c["y1"])
                    area += c["area"]
                    changed = True
        merged.append({
            "x0": x0, "x1": x1, "y0": y0, "y1": y1,
            "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2,
            "area": area,
        })
    merged.sort(key=lambda d: d["cx"])
    return merged


def make_strips(path, digits, cursor_x, n):
    img = Image.open(path).convert("RGB")
    # group digits into clusters by x proximity (gap > 18 splits)
    clusters = []
    cur = []
    for d in digits:
        if cur and d["x0"] - cur[-1]["x1"] > 18:
            clusters.append(cur)
            cur = []
        cur.append(d)
    if cur:
        clusters.append(cur)

    strips = []
    for cl in clusters:
        cx0 = min(d["x0"] for d in cl) - 22
        cx1 = max(d["x1"] for d in cl) + 22
        cx0 = max(0, cx0)
        cx1 = min(img.width, cx1)
        crop = img.crop((cx0, 55, cx1, 155))
        scale = 6
        up = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        # draw cursor line if inside this cluster
        if cursor_x is not None and cx0 - 5 <= cursor_x <= cx1 + 5:
            from PIL import ImageDraw
            d2 = ImageDraw.Draw(up)
            xc = (cursor_x - cx0) * scale
            d2.line([(xc, 0), (xc, up.height)], fill=(255, 80, 0), width=3)
        strips.append((cx0, up))

    gap = 16
    tw = sum(s.width + gap for _, s in strips) + gap
    th = max(s.height for _, s in strips) + 40
    montage = Image.new("RGB", (tw, th), (0, 0, 0))
    x = gap
    from PIL import ImageDraw
    dd = ImageDraw.Draw(montage)
    for cx0, s in strips:
        montage.paste(s, (x, 30))
        dd.text((x + 4, 6), f"x{cx0}", fill=(255, 255, 0))
        x += s.width + gap
    montage.save(os.path.join(OUT, f"tf_{n:04d}_strips.png"))
    return clusters


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    allres = {}
    for n in range(start, end + 1):
        path = os.path.join(SRC, f"tf_{n:04d}.jpg")
        cursor_x, blobs = detect_frame(path)
        digits = merge_digits(blobs)
        clusters = make_strips(path, digits, cursor_x, n)
        info = {"cursor_x": cursor_x, "digits": digits,
                "clusters": [[d["cx"] for d in cl] for cl in clusters]}
        allres[str(n)] = info
        print(f"frame {n}: cursor={cursor_x} ndigits={len(digits)} nclusters={len(clusters)}")
        for d in digits:
            s = min(range(6), key=lambda i: abs(LINE_Y[i] - d["cy"]))
            print(f"  x[{d['x0']:4d}..{d['x1']:4d}] y[{d['y0']:3d}..{d['y1']:3d}] cx={d['cx']:6.1f} cy={d['cy']:5.1f} s{s+1} w={d['x1']-d['x0']+1}")
    with open(os.path.join(OUT, "digits_71_84.json"), "w") as f:
        json.dump(allres, f, indent=1)


main()
