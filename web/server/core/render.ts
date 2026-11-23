/**
 * タブ譜のASCIIテキスト出力（Ultimate Guitar風）
 *
 * 旧: app/core/render.py を移植。
 */
import type { AnalysisBody } from "../../shared/schema";
import { buildScore } from "../../shared/grid";

const STRING_NAMES = ["e", "B", "G", "D", "A", "E"]; // 上から1弦..6弦
const CELL_W = 4;
const MEASURES_PER_LINE = 4;

export function scoreToAscii(result: AnalysisBody): string {
  const score = buildScore(result);
  const { measures, events, labels } = score;
  const meta = result.meta;

  const lines: string[] = [];
  lines.push(`# ${meta.title || "(無題)"}`);
  const tempo = meta.tempo ?? "?";
  if (meta.mode === "melody") {
    lines.push(`# メロディ(単音) / tempo=${tempo} BPM / tuning=EADGBE`);
  } else {
    lines.push(`# コード(バッキング) / tempo=${tempo} BPM`);
  }
  lines.push("");

  for (let lineStart = 0; lineStart < measures.length; lineStart += MEASURES_PER_LINE) {
    const chunk = measures.slice(lineStart, lineStart + MEASURES_PER_LINE);

    // 1小節 = [バー線1列 + スロット slots列]。最終小節の後ろに締めバー線が1列
    const measureWidths = chunk.map((m) => m.slots + 1);
    const totalCols = measureWidths.reduce((a, b) => a + b, 0) + 1;

    const rows: string[][] = Array.from({ length: 6 }, () => Array(totalCols * CELL_W).fill("-"));
    const labelLine = Array(totalCols * CELL_W).fill(" ");

    // バー線の列位置
    const barCols: number[] = [];
    let col = 0;
    for (const w of measureWidths) {
      barCols.push(col);
      col += w;
    }
    barCols.push(col); // 締め
    for (const bc of barCols) {
      const x = bc * CELL_W + Math.floor(CELL_W / 2);
      for (let r = 0; r < 6; r++) rows[r][x] = "|";
    }

    const cellX = (measureIdx: number, slot: number): number => {
      let base = 0;
      for (let i = 0; i < measureIdx - lineStart; i++) base += measureWidths[i];
      return (base + 1 + slot) * CELL_W;
    };

    for (const ev of events) {
      if (!(lineStart <= ev.measure && ev.measure < lineStart + chunk.length)) continue;
      const x0 = cellX(ev.measure, ev.slot);
      for (const [rowStr, textRaw] of Object.entries(ev.cells)) {
        const row = Number(rowStr);
        const text = String(textRaw).slice(0, CELL_W - 1);
        const pad = Math.floor((CELL_W - 1 - text.length) / 2);
        for (let k = 0; k < text.length; k++) {
          const x = x0 + pad + k;
          if (0 <= x && x < totalCols * CELL_W) rows[row][x] = text[k];
        }
      }
    }

    for (const lb of labels) {
      if (!(lineStart <= lb.measure && lb.measure < lineStart + chunk.length)) continue;
      const x0 = cellX(lb.measure, lb.slot);
      for (let k = 0; k < lb.text.length; k++) {
        const x = x0 + k;
        if (0 <= x && x < labelLine.length) labelLine[x] = lb.text[k];
      }
    }

    if (labelLine.some((c) => c !== " ")) lines.push(labelLine.join("").replace(/\s+$/, ""));
    for (let r = 0; r < 6; r++) {
      lines.push(`${STRING_NAMES[r]}|${rows[r].join("")}`);
    }
    lines.push("");
  }

  return lines.join("\n") + "\n";
}
