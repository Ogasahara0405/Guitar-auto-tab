import { useEffect, useMemo, useRef } from "react";
import type { AnalysisResult, TabEvent } from "../types";
import type { TimeSource } from "../App";

/* ===== 描画定数 ===== */
const PX_PER_SEC = 72;
const LEFT_PAD = 44;
const STAFF_TOP = 110;
const STAFF_GAP = 18;
const STRING_NAMES = ["e", "B", "G", "D", "A", "E"];

interface Props {
  result: AnalysisResult;
  timeSource: TimeSource;
}

function collectEvents(res: AnalysisResult): TabEvent[] {
  const evs: TabEvent[] = [];
  if (res.meta.mode === "melody") {
    for (const n of res.notes || []) {
      if (n.string == null || n.fret == null) continue;
      evs.push({
        start: n.start,
        end: n.end,
        cells: [{ row: n.string - 1, text: String(n.fret) }],
        label: null,
      });
    }
  } else {
    for (const c of res.chords || []) {
      const cells = (c.shape || []).map((s) => ({
        row: s.string - 1,
        text: String(s.fret),
      }));
      evs.push({ start: c.start, end: c.end, cells, label: c.label || null });
    }
  }
  evs.sort((a, b) => a.start - b.start);
  return evs;
}

export default function TabViewer({ result, timeSource }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef<SVGLineElement | null>(null);

  const events = useMemo(() => collectEvents(result), [result]);
  const dur = Math.max(result.meta.duration || 1, 1);
  const width = Math.max(900, Math.ceil(dur * PX_PER_SEC) + LEFT_PAD + 60);
  const height = STAFF_TOP + 5 * STAFF_GAP + 70;
  const bars = result.barlines.length ? result.barlines : [0, dur];

  // 結果が更新されたら先頭へスクロール
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollLeft = 0;
  }, [result.id]);

  // 再生位置の追従（カーソル・ハイライト・自動スクロール）— 60fpsで直接DOM操作
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const t = timeSource.current?.() ?? 0;
      const x = t * PX_PER_SEC + LEFT_PAD;

      const cursor = cursorRef.current;
      if (cursor) {
        cursor.setAttribute("x1", String(x));
        cursor.setAttribute("x2", String(x));
      }

      const sc = scrollRef.current;
      if (sc && (x - sc.scrollLeft > sc.clientWidth - 140 || x < sc.scrollLeft)) {
        sc.scrollLeft = Math.max(0, x - sc.clientWidth / 3);
      }

      const svg = svgRef.current;
      if (svg) {
        svg.querySelectorAll<SVGRectElement>("rect.ev").forEach((rect) => {
          const s = Number(rect.dataset.start);
          const e = Number(rect.dataset.end);
          rect.classList.toggle("active", t >= s && t < e);
        });
      }

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [result.id, timeSource]);

  return (
    <div className="tab-scroll" ref={scrollRef}>
      <svg
        ref={svgRef}
        className="tab-svg"
        xmlns="http://www.w3.org/2000/svg"
        width={width}
        height={height}
      >
        {/* イベント背景ハイライト */}
        {events.map((ev, i) => {
          const x = ev.start * PX_PER_SEC + LEFT_PAD;
          const w = Math.max(30, (Math.max(ev.end, ev.start + 0.15) - ev.start) * PX_PER_SEC);
          return (
            <rect
              key={`bg${i}`}
              className="ev"
              data-start={ev.start}
              data-end={ev.end}
              x={x - 8}
              y={STAFF_TOP - 34}
              width={w}
              height={5 * STAFF_GAP + 52}
              rx={5}
            />
          );
        })}

        {/* 譜線 */}
        {STRING_NAMES.map((name, r) => (
          <g key={`st${r}`}>
            <line
              x1={LEFT_PAD - 8}
              y1={STAFF_TOP + r * STAFF_GAP}
              x2={width}
              y2={STAFF_TOP + r * STAFF_GAP}
              className="staff"
            />
            <text x={12} y={STAFF_TOP + r * STAFF_GAP + 5} className="sname">
              {name}
            </text>
          </g>
        ))}

        {/* 小節線 */}
        {bars.map((b, i) => (
          <line
            key={`bar${i}`}
            x1={b * PX_PER_SEC + LEFT_PAD}
            y1={STAFF_TOP}
            x2={b * PX_PER_SEC + LEFT_PAD}
            y2={STAFF_TOP + 5 * STAFF_GAP}
            className="bar"
          />
        ))}

        {/* ノート / コード */}
        {events.map((ev, i) => {
          const x = ev.start * PX_PER_SEC + LEFT_PAD;
          return (
            <g key={`ev${i}`}>
              {ev.cells.map((c, j) =>
                c.row >= 0 && c.row <= 5 ? (
                  <text
                    key={j}
                    x={x}
                    y={STAFF_TOP + c.row * STAFF_GAP + 5}
                    className="fret"
                    textAnchor="middle"
                  >
                    {c.text}
                  </text>
                ) : null
              )}
              {ev.label && (
                <text x={x} y={STAFF_TOP - 38} className="chlabel">
                  {ev.label}
                </text>
              )}
            </g>
          );
        })}

        {/* 再生カーソル */}
        <line
          ref={cursorRef}
          x1={LEFT_PAD}
          y1={STAFF_TOP - 34}
          x2={LEFT_PAD}
          y2={STAFF_TOP + 5 * STAFF_GAP + 30}
          className="cursor"
        />
      </svg>
    </div>
  );
}
