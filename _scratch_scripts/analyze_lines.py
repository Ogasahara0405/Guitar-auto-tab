import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
import numpy as np
from PIL import Image

img = Image.open(r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes\tf_0071.jpg").convert("L")
a = np.asarray(img, dtype=np.float32)
print("shape", a.shape)
# row brightness profile: horizontal lines should be brighter rows
rows = a.mean(axis=1)
for y in range(a.shape[0]):
    bar = "#" * int(rows[y] / 2)
    print(f"{y:3d} {rows[y]:6.1f} {bar}")
