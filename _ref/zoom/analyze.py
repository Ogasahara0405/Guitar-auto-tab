import sys
from PIL import Image

STAFF = [69, 84, 98, 112.5, 127, 141]

def nearest_string(ymid):
    dists = [abs(ymid - s) for s in STAFF]
    return dists.index(min(dists)) + 1

def analyze(path, verbose=True):
    im = Image.open(path).convert('RGB')
    W, H = im.size
    px = im.load()
    gp = im.convert('L').load()

    # ---- cursor ----
    warm = []
    for x in range(W):
        cnt = sum(1 for y in range(30, 158)
                  if px[x, y][0] > px[x, y][2] + 10 and px[x, y][0] > 35 and px[x, y][0] >= px[x, y][1])
        if cnt > 10:
            warm.append(x)
    cur = sum(warm)/len(warm) if warm else None

    # ---- digit mask: bright vs local horizontal median ----
    y0s, y1s = 60, 156
    mask = [[False]*W for _ in range(H)]
    for y in range(y0s, y1s):
        row = [gp[x, y] for x in range(W)]
        for x in range(W):
            a, b = max(0, x-12), min(W, x+13)
            win = sorted(row[a:b])
            med = win[len(win)//2]
            v = row[x]
            if v > med + 20 and v > 85:
                mask[y][x] = True

    seen = [[False]*W for _ in range(H)]
    blobs = []
    for y in range(y0s, y1s):
        for x in range(W):
            if mask[y][x] and not seen[y][x]:
                st = [(x, y)]
                seen[y][x] = True
                pts = []
                while st:
                    cx, cy = st.pop()
                    pts.append((cx, cy))
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx+dx, cy+dy
                            if 0 <= nx < W and y0s <= ny < y1s and mask[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                st.append((nx, ny))
                if len(pts) < 8:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
                w, h = bx1-bx0+1, by1-by0+1
                if h < 5 or h > 22 or w > 24:
                    continue
                blobs.append([bx0, bx1, by0, by1])

    blobs.sort(key=lambda b: b[0])
    numbers = []
    for b in blobs:
        ymid = (b[2]+b[3]) / 2
        s = nearest_string(ymid)
        if numbers:
            n = numbers[-1]
            if n[3] == s and b[0] - n[1] <= 5 and abs(ymid - n[2]) <= 6:
                numbers[-1] = [n[0], b[1], (n[2]+ymid)/2, s, n[4]+1]
                continue
        numbers.append([b[0], b[1], ymid, s, 1])

    clusters = []
    for n in numbers:
        if clusters and n[0] - clusters[-1][1] <= 12:
            c = clusters[-1]
            clusters[-1] = [min(c[0], n[0]), max(c[1], n[1]), c[2]+[n]]
        else:
            clusters.append([n[0], n[1], [n]])

    if verbose:
        print(f"== {path.split('/')[-1]}")
        print(f"cursor_x = {None if cur is None else round(cur,1)}  warm={warm[:1]}..{warm[-1:]}")
        for cx0, cx1, ns in clusters:
            ns = sorted(ns, key=lambda t: t[3])
            desc = ", ".join(f"s{t[3]}:{'?'*t[4]}(x{round((t[0]+t[1])/2,1)})" for t in ns)
            print(f"  CL mid_x={round((cx0+cx1)/2,1)} [{cx0}..{cx1}]: {desc}")
    return cur, clusters

if __name__ == '__main__':
    for p in sys.argv[1:]:
        analyze(p)
