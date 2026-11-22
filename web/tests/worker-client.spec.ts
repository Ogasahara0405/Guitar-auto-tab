/**
 * worker 出力パーサ（parseWorkerOutput）のテスト
 * 本障害（yt-dlp進捗ノイズによるJSON解析破壊）の再発防止と、
 * マーカー抽出のエッジケース検証。
 */
import { describe, expect, it } from "vitest";
import { parseWorkerOutput } from "../server/worker/client";

const MARKER = "__GAT_JSON__";

describe("parseWorkerOutput", () => {
  it("正常時: マーカー行のJSONを読む", () => {
    const out = `\n${MARKER}{"wav": "a.wav", "title": "t", "media": "a.mp4"}\r\n`;
    expect(parseWorkerOutput(out)).toEqual({ wav: "a.wav", title: "t", media: "a.mp4" });
  });

  it("yt-dlp進捗ノイズ（改行なし）が混ざっても読む", () => {
    const out =
      "[download]  0.0% of 4.5MiB at 1MiB/s ETA 00:05\r" +
      "[download] 100% of 4.5MiB in 00:00:00   \n" +
      `${MARKER}{"wav": "a.wav", "title": "t", "media": "a.webm"}`;
    expect(parseWorkerOutput(out)).toEqual({ wav: "a.wav", title: "t", media: "a.webm" });
  });

  it("ペイロード内にマーカー文字列を含むタイトルでも、行頭アンカーの本物を採る", () => {
    const title = `foo ${MARKER} bar`;
    const out = `\n${MARKER}{"wav": "a.wav", "title": "foo ${MARKER} bar", "media": "a.mp4"}\n`;
    const parsed = parseWorkerOutput(out) as { title: string };
    expect(parsed.title).toBe(title);
  });

  it("マーカーが複数あれば最後のものを採る", () => {
    const out = `\n${MARKER}{"old": 1}\nnoise\n${MARKER}{"new": 2}\n`;
    expect(parseWorkerOutput(out)).toEqual({ new: 2 });
  });

  it("マーカーが無ければ最終行をフォールバックで読む（後方互換）", () => {
    const out = "some log line\n{\"fallback\": true}\n";
    expect(parseWorkerOutput(out)).toEqual({ fallback: true });
  });

  it("JSONの直後にノイズが続いてもマーカー行の1行だけで読む", () => {
    const out = `\n${MARKER}{"a": 1}\ntrailing noise here`;
    expect(parseWorkerOutput(out)).toEqual({ a: 1 });
  });

  it("空出力・不正出力では例外を投げる（呼び出し側が捕捉）", () => {
    expect(() => parseWorkerOutput("")).toThrow();
    expect(() => parseWorkerOutput("not json at all")).toThrow();
  });
});
