import sys
sys.path.insert(0, r"C:\Users\iniad\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\site-packages")
from PIL import Image, ImageDraw
import os

SRC = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes"
OUT = r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes_zoom"

LINE_Y = [69, 84, 98, 112, 127, 141]

def crop_region(frame, x0, x1, y0=55, y1=155, scale=10, name=None, mark_lines=True):
    path = os.path.join(SRC, f"tf_{frame:04d}.jpg")
    img = Image.open(path).convert("RGB")
    crop = img.crop((max(0, x0), y0, min(img.width, x1), y1))
    up = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    if mark_lines:
        d = ImageDraw.Draw(up)
        for i, ly in enumerate(LINE_Y):
            if y0 <= ly <= y1:
                yy = (ly - y0) * scale
                d.line([(0, yy), (up.width, yy)], fill=(0, 90, 0), width=1)
                d.text((2, yy - 12), f"s{i+1}", fill=(0, 200, 0))
    fn = name or f"tf_{frame:04d}_crop_{x0}_{x1}.png"
    up.save(os.path.join(OUT, fn))
    print("saved", fn)

if __name__ == "__main__":
    # frame 71: verify pair at x=525 ("7/6"?), pairs at 859-926 ("2/0"), singles 974/1002
    crop_region(71, 505, 545, name="f71_pair_525.png")
    crop_region(71, 840, 945, name="f71_pairs_855_926.png")
    crop_region(71, 955, 1015, name="f71_singles.png")
    crop_region(71, 1060, 1160, name="f71_pairs_1077_1143.png")
