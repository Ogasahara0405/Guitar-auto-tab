import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
import numpy as np
from PIL import Image

img = Image.open(r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes\tf_0071.jpg").convert("RGB")
arr = np.asarray(img, dtype=np.float32)
g = arr.mean(axis=2)

# brightness histogram in tab band (y 60..155) excluding line rows
band = g[60:155, :]
hist, edges = np.histogram(band, bins=20, range=(0, 255))
for i, c in enumerate(hist):
    print(f"{edges[i]:5.0f}-{edges[i+1]:5.0f}: {c}")

# max brightness overall
print("max", band.max(), "mean", band.mean())

# sample a known digit region: from zoomed c0, "5" was around original x=46, y=125
patch = g[118:132, 38:56]
print("patch around supposed '5':")
print(patch.astype(int))

# orange cursor: compute r-b stats per column
r = arr[:, :, 0]; b = arr[:, :, 2]
rb = r - b
colmax = rb.max(axis=0)
cands = np.argsort(colmax)[-10:]
print("top cols by r-b:", [(int(c), float(colmax[c])) for c in sorted(cands)])
colscores = (rb > 15).sum(axis=0)
top = np.argsort(colscores)[-15:]
print("top cols by orange count:", [(int(c), int(colscores[c])) for c in sorted(top)])
