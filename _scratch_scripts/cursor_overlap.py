import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
import numpy as np
from PIL import Image
import os
import json

SRC = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes"
OUT = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes_zoom"
LINE_Y = [69, 84, 98, 112, 127, 141]

with open(os.path.join(OUT, "digits_71_84.json")) as f:
    data = json.load(f)

for n in range(71, 85):
    path = os.path.join(SRC, f"tf_{n:04d}.jpg")
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    r, b = arr[:, :, 0], arr[:, :, 2]
    orange = (r - b > 10) & (r > 50)
    col_score = orange.sum(axis=0)
    cols = np.where(col_score > 15)[0]
    # contiguous runs
    runs = []
    if len(cols):
        start = cols[0]
        prev = cols[0]
        for c in cols[1:]:
            if c > prev + 1:
                runs.append((int(start), int(prev)))
                start = c
            prev = c
        runs.append((int(start), int(prev)))
    print(f"frame {n}: cursor runs {runs}")
    info = data[str(n)]
    for d in info["digits"]:
        for (ra, rb_2) in runs:
            if d["x0"] - 1 <= rb_2 and d["x1"] + 1 >= ra:
                s = min(range(6), key=lambda i: abs(LINE_Y[i] - d["cy"]))
                print(f"   overlap digit x[{d['x0']}..{d['x1']}] y[{d['y0']}..{d['y1']}] cy={d['cy']} s{s+1}")
