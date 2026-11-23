"""OCRワークフローの出力（フレームごとのカーソル位置の音）を正解ポイントに変換する

使い方:
    python tests\ocr_to_ref.py _ref\ocr_frames.json _ref\ref_points.json

入力: {"frames": [{"n": フレーム番号, "cursor_notes": [{"string","fret"},...], "events": [...]}, ...]}
出力: [{"t": 秒, "notes": [{"string","fret"},...]}, ...]
    t = (n-1) * 2 秒（tf_NNNN.jpg の時刻）
    同一の音が連続フレームに現れる場合は最初の1点に集約（長い音の重複計数を防ぐ）
"""
import json
import sys
from pathlib import Path


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))
    frames = sorted(data.get("frames", []), key=lambda f: f.get("n", 0))

    points = []
    recent = []  # (t, string, fret) 直近の集約済み音（3秒以内の重複を除く）
    for f in frames:
        n = f.get("n", 0)
        t = (n - 1) * 2
        notes = []
        for rn in f.get("cursor_notes", []):
            s, fret = int(rn["string"]), int(rn["fret"])
            dup = any(
                abs(t - pt) <= 3.0 and ps == s and pf == fret for pt, ps, pf in recent
            )
            if dup:
                continue
            notes.append({"string": s, "fret": fret})
            recent.append((t, s, fret))
        if notes:
            points.append({"t": t, "notes": notes})
    dst.write_text(json.dumps(points, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"frames: {len(frames)} -> reference points: {len(points)} (notes: {sum(len(p['notes']) for p in points)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
