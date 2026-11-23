import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
import numpy as np
from PIL import Image

SRC = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes"

def analyze(frame, x_lo, x_hi):
    path = f"{SRC}\\tf_{frame:04d}.jpg"
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    g = arr.mean(axis=2)
    r, b = arr[:, :, 0], arr[:, :, 2]
    orange = (r - b > 8) & (r > 45)
    print(f"frame {frame}, x {x_lo}..{x_hi}")
    for x in range(x_lo, x_hi + 1):
        o = orange[:, x].sum()
        bright = (g[60:155, x] > 55).sum()
        bright70 = (g[60:155, x] > 70).sum()
        print(f"  x={x}: orange_rows={o:3d} bright55={bright:3d} bright70={bright70:3d}")

# frame 75: digit x[377..385], cursor 388-391
analyze(75, 380, 396)
# frame 73: digit x[664..671], cursor 675-679
analyze(73, 668, 682)
# frame 77: cursor 843-847, digit x[853..861]
analyze(77, 840, 858)
