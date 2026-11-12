import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisResult } from "../types";
import type { TimeSource } from "../App";
import { frameUrl } from "../api";

interface Props {
  result: AnalysisResult;
  timeSource: TimeSource;
}

interface FrameEntry {
  start: number;
  end: number;
  frame: string;
  /** 弦番号(6..1)とフレット */
  cells: { string: number; fret: number }[];
  label: string | null;
  muted: number[];
}

/** ノート/コードとリンクした映像フレーム表示
 * ブリッジ側の映像を見ればどの弦を弾いているか確認できるので、
 * 再生位置に対応するフレームを並べて表示し、タブ譜の弦割当と照合できるようにする。
 */
export default function FrameLink({ result, timeSource }: Props) {
  const [current, setCurrent] = useState<FrameEntry | null>(null);
  const entriesRef = useRef<FrameEntry[]>([]);

  const entries = useMemo<FrameEntry[]>(() => {
    const out: FrameEntry[] = [];
    if (result.meta.mode === "melody") {
      for (const n of result.notes || []) {
        if (!n.frame || n.string == null || n.fret == null) continue;
        out.push({
          start: n.start,
          end: n.end,
          frame: n.frame,
          cells: [{ string: n.string, fret: n.fret }],
          label: null,
          muted: [],
        });
      }
    } else {
      for (const c of result.chords || []) {
        if (!c.frame) continue;
        out.push({
          start: c.start,
          end: c.end,
          frame: c.frame,
          cells: (c.shape || []).map((s) => ({ string: s.string, fret: s.fret })),
          label: c.label || null,
          muted: c.muted || [],
        });
      }
    }
    return out.sort((a, b) => a.start - b.start);
  }, [result]);

  entriesRef.current = entries;

  useEffect(() => {
    const id = window.setInterval(() => {
      const t = timeSource.current?.() ?? 0;
      const list = entriesRef.current;
      let cur: FrameEntry | null = null;
      for (const e of list) {
        if (t >= e.start - 0.05 && t < e.end + 0.4) {
          cur = e;
          if (t < e.end) break;
        }
      }
      setCurrent((prev) => (prev === cur || (prev && cur && prev.frame === cur.frame) ? prev : cur));
    }, 160);
    return () => window.clearInterval(id);
  }, [timeSource]);

  if (!entries.length) return null;

  const caption = (() => {
    if (!current) return "再生すると、その位置の映像フレーム（ブリッジ側で弦の確認が可能）が表示されます";
    const cells = current.cells
      .map((c) => `${c.string}弦/${c.fret}`)
      .join(" ");
    const parts = [`${current.start.toFixed(2)}秒`, cells];
    if (current.label) parts.unshift(current.label);
    if (current.muted.length) {
      parts.push(`ミュート(音声確認で不鳴): ${current.muted.join(",")}弦`);
    }
    return parts.join(" — ");
  })();

  return (
    <div className="frame-link">
      <div className="frame-img">
        {current ? (
          <img
            src={frameUrl(result.id, current.frame)}
            alt={`映像フレーム ${current.start.toFixed(2)}秒`}
            key={current.frame}
          />
        ) : (
          <div className="frame-placeholder">映像フレーム</div>
        )}
      </div>
      <div className="frame-caption">{caption}</div>
    </div>
  );
}
