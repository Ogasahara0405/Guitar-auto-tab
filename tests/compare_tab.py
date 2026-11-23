r"""採譜結果と正解タブ（参考動画から読み取ったカーソル位置の音）を比較するベンチマーク

使い方:
    python tests\compare_tab.py _ref\ref_points.json _ref\ours.json

ref_points.json: [{"t": 秒, "notes": [{"string": 1..6, "fret": 0..22}, ...]}, ...]
    （参考動画のタブ譜で再生カーソルが重なっていた音 = その時刻に鳴っている音）

判定:
  strict  … 同じ弦・同じフレットのノートが ±TOL 秒以内にある
  pitch  … 同じ音高（どの弦でも）のノートが ±TOL 秒以内にある
            （押さえ方の選択は弾き手の好みで異なり得るため、まず音高一致を見る）
"""
import json
import sys
from pathlib import Path

TOL = float(__import__("os").environ.get("CMP_TOL", "0.45"))  # 秒

# 弦(1..6) + フレット → MIDI（標準チューニング）
OPEN = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}


def fret_to_midi(string: int, fret: int) -> int:
    return OPEN[string] + fret


def main() -> int:
    ref_path, ours_path = Path(sys.argv[1]), Path(sys.argv[2])
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    ours = json.loads(ours_path.read_text(encoding="utf-8"))
    notes = ours["notes"] if "notes" in ours else ours

    strict_ok = pitch_ok = total = 0
    misses = []
    for pt in ref:
        t = float(pt["t"])
        for rn in pt.get("notes", []):
            total += 1
            s, f = int(rn["string"]), int(rn["fret"])
            rmidi = fret_to_midi(s, f)
            window = [n for n in notes if abs(n["start"] - t) <= TOL or (n["start"] - TOL <= t <= n["end"] + TOL)]
            strict = any(n.get("string") == s and n.get("fret") == f for n in window)
            pitch = any(n["midi"] == rmidi for n in window)
            if strict:
                strict_ok += 1
            if pitch:
                pitch_ok += 1
            if not strict:
                got = [(n.get("string"), n.get("fret"), n["midi"]) for n in window][:4]
                misses.append({"t": t, "ref": (s, f, rmidi), "pitch_ok": pitch, "ours": got})

    print(f"reference points: {total}")
    print(f"strict match (same string+fret): {strict_ok}/{total} = {100.0 * strict_ok / max(total, 1):.1f}%")
    print(f"pitch match (same midi):        {pitch_ok}/{total} = {100.0 * pitch_ok / max(total, 1):.1f}%")
    print()
    print("misses (first 40):")
    for m in misses[:40]:
        tag = "PITCH_OK_POS_DIFF" if m["pitch_ok"] else "MISS"
        print(f"  [{tag}] t={m['t']:.1f}s ref={m['ref']} ours={m['ours']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
