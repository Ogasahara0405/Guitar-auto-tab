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

    # cursor: orange vertical line
    r, b = arr[:, :, 0], arr[:, :, 2]
    orange = (r - b > 12) & (r > 55)
    col_score = orange.sum(axis=0)
    cursor_x = None
    best = col_score.max()
    if best > 30:
        cands = np.where(col_score >= best - 5)[0]
        cursor_x = int(round(cands.mean()))

    # number blobs
    band = g[60:155, :]
    mask = band > 70

    # remove horizontal string-line rows (bright across >55% width)
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
        if area < 12:
            continue
        w = x_max - x_min + 1
        h = y_max - y_min + 1
        if h > 26 and w < 5:
            continue  # vertical bar line
        if w > 50:
            continue  # horizontal leftover / text
        if y_max < 66 or y_min > 150:
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


def digit_image(path, blob, pad=3):
    img = Image.open(path).convert("L")
    x0 = max(0, int(blob["x0"]) - pad)
    x1 = min(img.width, int(blob["x1"]) + pad + 1)
    y0 = max(0, int(blob["y0"]) - pad)
    y1 = min(img.height, int(blob["y1"]) + pad + 1)
    return img.crop((x0, y0, x1, y1))


def main():
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    results = {}
    for n in range(start, end + 1):
        path = os.path.join(SRC, f"tf_{n:04d}.jpg")
        cursor_x, blobs = detect_frame(path)
        results[str(n)] = {"cursor_x": cursor_x, "blobs": blobs}
        print(f"--- frame {n} cursor_x={cursor_x} nblobs={len(blobs)}")
        for b in blobs:
            nearest = min(range(6), key=lambda i: abs(LINE_Y[i] - b["cy"]))
            print(f"  x[{b['x0']:4d}..{b['x1']:4d}] y[{b['y0']:3d}..{b['y1']:3d}] cy={b['cy']:5.1f} s{nearest+1} area={b['area']}")

        crops = [digit_image(path, b) for b in blobs]
        if crops:
            scale = 7
            gap = 10
            tw = sum(c.width * scale + gap for c in crops) + 20
            th = max(c.height for c in crops) * scale + 20
            montage = Image.new("L", (tw, th), 0)
            x = 10
            for c in crops:
                up = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
                montage.paste(up, (x, 10))
                x += up.width + gap
            montage.save(os.path.join(OUT, f"tf_{n:04d}_digits.png"))
    with open(os.path.join(OUT, "blobs_71_84.json"), "w") as f:
        json.dump(results, f, indent=1)


main()
