/**
 * 型付きAPIクライアント（Nitro サーバーの /api/ を呼び出す）
 *
 * 旧: frontend/src/api.ts（fetch版）を移植。エラーメッセージは
 * Nitro のエラー応答（message / statusMessage）から取り出す。
 */
import type { AnalysisResult, ChordStyle, Mode } from "~/shared/schema";

export type { Mode, ChordStyle };

export interface AnalyzeParams {
  mode: Mode;
  chordStyle: ChordStyle;
  url: string;
  file: File | null;
}

export type ArtifactName = "tab.pdf" | "tab.txt" | "analysis.json";

async function apiCall<T>(url: string, opts?: Record<string, unknown>): Promise<T> {
  try {
    return await $fetch<T>(url, opts);
  } catch (e: unknown) {
    const data = (e as { data?: { message?: string; statusMessage?: string } }).data;
    const msg = data?.message || data?.statusMessage;
    throw new Error(msg || (e instanceof Error ? e.message : String(e)));
  }
}

export function analyze(p: AnalyzeParams): Promise<AnalysisResult> {
  const fd = new FormData();
  fd.append("mode", p.mode);
  fd.append("chord_style", p.chordStyle);
  if (p.url) fd.append("url", p.url);
  if (p.file) fd.append("file", p.file);
  return apiCall<AnalysisResult>("/api/analyze", { method: "POST", body: fd });
}

/** Claude Code で磨いた analysis.json の取り込み */
export function importAnalysis(file: File): Promise<AnalysisResult> {
  const fd = new FormData();
  fd.append("file", file);
  return apiCall<AnalysisResult>("/api/import", { method: "POST", body: fd });
}

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
