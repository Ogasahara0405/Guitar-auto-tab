/**
 * タブ譜のPDF出力（pdfkitによるベクタ描画・日本語対応）
 *
 * 旧: app/core/pdf.py（reportlab）を移植。
 * 日本語フォントは Windows のシステムフォントを _pick_font と同じ順で試し、
 * 無ければ Helvetica（ASCIIのみ）にフォールバックする。
 */
import { createWriteStream } from "node:fs";
import PDFDocument from "pdfkit";
import type { AnalysisBody } from "../../shared/schema";
import { buildScore, type Measure } from "../../shared/grid";

const MM = 72 / 25.4; // 1mm = 2.8346pt
const STAFF_GAP = 3.2 * MM;
const SLOT_W = 3.4 * MM;
const CELL_H = 11 * MM;
const MARGIN_X = 14 * MM;

// Windowsの日本語TTF/TTC（PDFKit+fontkit は PostScript名/ファミリ名で面を選ぶ）
const JP_FONTS: [string, string[]][] = [
  ["C:/Windows/Fonts/YuGothM.ttc", ["Yu Gothic UI", "Yu Gothic", "YuGothic-Medium"]],
  ["C:/Windows/Fonts/YuGothR.ttc", ["Yu Gothic UI", "Yu Gothic", "YuGothic-Regular"]],
  ["C:/Windows/Fonts/meiryo.ttc", ["Meiryo UI", "Meiryo", "MeiryoUI-Regular", "Meiryo-Regular"]],
  ["C:/Windows/Fonts/msgothic.ttc", ["MS Gothic", "MS-Gothic", "MS PGothic", "MS-PGothic"]],
];

/** 日本語フォントを登録してフォント名を返す（無ければ Helvetica） */
function pickFont(doc: PDFKit.PDFDocument): string {
  for (const [path, families] of JP_FONTS) {
    try {
      // 同梱フォントが無ければ次へ（存在確認は登録試行で兼ねる）
      for (const family of families) {
        try {
          doc.registerFont("jp", path, family);
          doc.font("jp");
          if (doc.widthOfString("あ") > 0) return "jp";
        } catch {
          /* 次のファミリ名を試す */
        }
      }
    } catch {
      /* 次のフォントファイルを試す */
    }
  }
  return "Helvetica";
}

function measureW(m: Measure): number {
  return (m.slots + 2) * SLOT_W; // スロット + 左右のバー線余白
}

/** 解析結果を A4 横のタブ譜PDFとして outPath に書き出す */
export async function renderPdf(result: AnalysisBody, outPath: string): Promise<void> {
  const score = buildScore(result);
  const { measures, events, labels } = score;
  const meta = result.meta;

  await new Promise<void>((resolvePromise, reject) => {
    const doc = new PDFDocument({ size: "A4", layout: "landscape", margin: 0 });
    const stream = createWriteStream(outPath);
    // PDFDocumentはReadableStreamだが型定義上は流儀が揃わないため明示的に扱う
    const docStream = doc as unknown as NodeJS.ReadableStream;
    docStream.pipe(stream);
    stream.on("finish", () => resolvePromise());
    stream.on("error", reject);
    docStream.on("error", reject);

    const font = pickFont(doc);
    const W = doc.page.width;
    const H = doc.page.height;
    const usableW = W - MARGIN_X * 2;

    // ヘッダ
    // 座標系の注意: reportlab は下原点(y-up)・pdfkit は上原点(y-down)。
    // pdf.py の y_up は「y_down = H - y_up」で変換している。
    // doc.text(x, y) の y は行ボックスの上端なので、ベースライン目標から約 0.72*fontSize を引く。
    doc.font(font).fontSize(14);
    doc.text(String(meta.title ?? "(無題)"), MARGIN_X, 16 * MM - 10, { lineBreak: false });
    doc.fontSize(9);
    const mode = meta.mode === "melody" ? "メロディ(単音)" : "コード(バッキング)";
    doc.text(
      `${mode}   tempo=${meta.tempo ?? "?"} BPM   tuning=EADGBE`,
      MARGIN_X,
      22 * MM - 7,
      { lineBreak: false },
    );

    let y = 34 * MM; // 譜線（1弦）の上端: ページ上端から34mm
    let pageNo = 1;
    let sysTopIdx = 0;
    const perSystem = Math.max(1, Math.floor(usableW / measureW(measures[0])));
    const systems: Measure[][] = [];
    for (let i = 0; i < measures.length; i += perSystem) {
      systems.push(measures.slice(i, i + perSystem));
    }

    const drawPageNo = () => {
      doc.font(font).fontSize(8);
      const t = String(pageNo);
      const w = doc.widthOfString(t);
      doc.text(t, W - MARGIN_X - w, H - 10 * MM - 6, { lineBreak: false });
    };

    for (const sys of systems) {
      // ページ下端24mmを切ったら改ページ（pdf.py の y_up < 24mm に相当）
      if (y > H - 24 * MM) {
        drawPageNo();
        doc.addPage();
        pageNo += 1;
        y = 18 * MM;
      }

      const top = y;
      const staffW = sys.reduce((a, m) => a + measureW(m), 0);

      // 6本の譜線（1弦=上 → y-down では下方向に増える）
      doc.lineWidth(0.6);
      for (let r = 0; r < 6; r++) {
        const yy = top + r * STAFF_GAP;
        doc.moveTo(MARGIN_X, yy).lineTo(MARGIN_X + staffW, yy).stroke();
      }

      // 小節線
      const barXs = [MARGIN_X];
      let x = MARGIN_X;
      for (const m of sys) {
        x += measureW(m);
        barXs.push(x);
      }
      doc.lineWidth(0.9);
      for (const bx of barXs) {
        doc.moveTo(bx, top).lineTo(bx, top + 5 * STAFF_GAP).stroke();
      }

      const posX = (measureIdxGlobal: number, slot: number): number => {
        let base = MARGIN_X;
        for (let i = 0; i < measureIdxGlobal - sysTopIdx; i++) base += measureW(sys[i]);
        return base + (slot + 1.5) * SLOT_W;
      };

      // ノート/コードのフレット数字（各弦の譜線のやや下にベースラインを置く）
      doc.font(font).fontSize(8);
      for (const ev of events) {
        if (!(sysTopIdx <= ev.measure && ev.measure < sysTopIdx + sys.length)) continue;
        const x0 = posX(ev.measure, ev.slot);
        for (const [rowStr, textRaw] of Object.entries(ev.cells)) {
          const row = Number(rowStr);
          const t = String(textRaw);
          const tw = doc.widthOfString(t);
          const baseline = top + row * STAFF_GAP + 2.2;
          doc.text(t, x0 - tw / 2, baseline - 6, { lineBreak: false });
        }
      }

      // コード名（譜線の上側）
      doc.font(font).fontSize(9);
      for (const lb of labels) {
        if (!(sysTopIdx <= lb.measure && lb.measure < sysTopIdx + sys.length)) continue;
        const x0 = posX(lb.measure, lb.slot);
        const baseline = top - 3.2 * MM;
        doc.text(lb.text, x0 - 3, baseline - 7, { lineBreak: false });
      }

      y = top + CELL_H;
      sysTopIdx += sys.length;
    }

    drawPageNo();
    doc.end();
  });
}
