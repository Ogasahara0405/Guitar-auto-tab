import type { AnalysisResult } from "./types";

export type Mode = "melody" | "chords";
export type ChordStyle = "chord" | "power";

export interface AnalyzeParams {
  mode: Mode;
  chordStyle: ChordStyle;
  url: string;
  file: File | null;
}

async function toResult(res: Response): Promise<AnalysisResult> {
  if (!res.ok) {
    let msg = res.statusText || `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* JSON でないエラーボディはそのまま扱う */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function analyze(p: AnalyzeParams): Promise<AnalysisResult> {
  const fd = new FormData();
  fd.append("mode", p.mode);
  fd.append("chord_style", p.chordStyle);
  if (p.url) fd.append("url", p.url);
  if (p.file) fd.append("file", p.file);
  return toResult(await fetch("/api/analyze", { method: "POST", body: fd }));
}

/** Claude Code で磨いた analysis.json の取り込み */
export async function importAnalysis(file: File): Promise<AnalysisResult> {
  const fd = new FormData();
  fd.append("file", file);
  return toResult(await fetch("/api/import", { method: "POST", body: fd }));
}

export type ArtifactName = "tab.pdf" | "tab.txt" | "analysis.json";

export function jobUrl(id: string, name: ArtifactName): string {
  return `/api/jobs/${id}/${name}`;
}

export function mediaUrl(id: string): string {
  return `/api/jobs/${id}/media`;
}

/** 映像フレーム画像（ブリッジ側の弦の確認用） */
export function frameUrl(id: string, name: string): string {
  return `/api/jobs/${id}/frames/${encodeURIComponent(name)}`;
}
