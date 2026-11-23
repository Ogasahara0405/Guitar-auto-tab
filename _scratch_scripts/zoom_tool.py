import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
from PIL import Image
import os

src_dir = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes"
dst_dir = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes_zoom"
os.makedirs(dst_dir, exist_ok=True)

args = sys.argv[1:]
start = int(args[0]) if len(args) > 0 else 71
end = int(args[1]) if len(args) > 1 else 84
nchunks = int(args[2]) if len(args) > 2 else 3
scale = int(args[3]) if len(args) > 3 else 4

for n in range(start, end + 1):
    fn = f"tf_{n:04d}.jpg"
    img = Image.open(os.path.join(src_dir, fn))
    w, h = img.size
    chunk_w = w // nchunks
    for i in range(nchunks):
        x0 = max(0, i * chunk_w - 15)
        x1 = min(w, (i + 1) * chunk_w + 15)
        crop = img.crop((x0, 0, x1, h))
        up = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        up.save(os.path.join(dst_dir, f"{fn[:-4]}_c{i}.png"))
print("done", start, end)
