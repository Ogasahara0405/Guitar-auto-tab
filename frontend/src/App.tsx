import { useRef, useState } from "react";
import type { AnalysisResult } from "./types";
import { analyze, importAnalysis } from "./api";
import type { ChordStyle, Mode } from "./api";
import ModeSelector from "./components/ModeSelector";
import SourceForm from "./components/SourceForm";
import PlayerPanel from "./components/PlayerPanel";
import TabToolbar from "./components/TabToolbar";
import TabViewer from "./components/TabViewer";

interface StatusState {
  msg: string;
  error: boolean;
}

/** 再生位置（秒）を返す関数。プレイヤーが差し替えられるため ref で保持する */
export type TimeSource = { current: (() => number) | null };

export default function App() {
  const [mode, setMode] = useState<Mode>("melody");
  const [chordStyle, setChordStyle] = useState<ChordStyle>("chord");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [playerUrl, setPlayerUrl] = useState("");
  const [status, setStatus] = useState<StatusState>({ msg: "", error: false });
  const timeSource = useRef<(() => number) | null>(null);

  const failWith = (e: unknown) =>
    setStatus({ msg: "失敗: " + (e instanceof Error ? e.message : String(e)), error: true });

  const handleAnalyze = async (file: File | null) => {
    const trimmed = url.trim();
    if (!trimmed && !file) {
      setStatus({ msg: "YouTube URL かファイルを指定してください", error: true });
      return;
    }
    setBusy(true);
    setStatus({ msg: "解析中… 30秒〜数分かかることがあります", error: false });
    try {
      const res = await analyze({ mode, chordStyle, url: trimmed, file });
      setResult(res);
      // ファイル入力時はアップロードしたメディアを再生、URL入力時はYouTube埋め込み
      setPlayerUrl(file ? "" : trimmed);
      setStatus({
        msg: `完了: ${res.meta.title}（${res.meta.duration.toFixed(1)}秒）`,
        error: false,
      });
    } catch (e) {
      failWith(e);
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async (file: File) => {
    setStatus({ msg: "JSONを取り込み中…", error: false });
    try {
      const res = await importAnalysis(file);
      setResult(res);
      setPlayerUrl(url.trim());
      setStatus({ msg: "取り込み完了: " + res.meta.title, error: false });
    } catch (e) {
      failWith(e);
    }
  };

  return (
    <>
      <header>
        <h1>🎸 Guitar Auto Tab</h1>
        <p className="sub">
          YouTube・音声/動画ファイルからギタータブ譜を自動生成（個人利用・完全無料）
        </p>
      </header>

      <main>
        <section className="panel controls">
          <ModeSelector
            mode={mode}
            chordStyle={chordStyle}
            onModeChange={setMode}
            onChordStyleChange={setChordStyle}
          />
          <SourceForm url={url} busy={busy} onUrlChange={setUrl} onAnalyze={handleAnalyze} />
          <div className={"status" + (status.error ? " error" : "")}>{status.msg}</div>
        </section>

        {result && (
          <section className="panel viewer">
            <PlayerPanel result={result} sourceUrl={playerUrl} timeSource={timeSource} />
            <TabToolbar result={result} onImport={handleImport} />
            <TabViewer result={result} timeSource={timeSource} />
            <p className="hint">
              ▶ 再生するとカーソルがタブ譜の現在位置に追従します。
              <br />
              精度を上げたいときは「analysis.json書き出し」でデータを保存し、Claude Code
              に渡して採譜を磨いてもらってから 「磨き上げJSONを取り込み」で読み込むと、表示・PDF/TXT保存に反映されます。
            </p>
          </section>
        )}
      </main>
    </>
  );
}
