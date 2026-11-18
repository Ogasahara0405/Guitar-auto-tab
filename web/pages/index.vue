<script setup lang="ts">
import { reactive, ref } from "vue";
import type { AnalysisResult, ChordStyle, Mode } from "~/shared/schema";
import { analyze, importAnalysis, type AnalyzeParams } from "~/utils/api";
import { useTimeSource } from "~/composables/useTimeSource";

const mode = ref<Mode>("melody");
const chordStyle = ref<ChordStyle>("chord");
const url = ref("");
const busy = ref(false);
const result = ref<AnalysisResult | null>(null);
const playerUrl = ref("");
const status = reactive<{ msg: string; error: boolean }>({ msg: "", error: false });
const timeSource = useTimeSource();

function failWith(e: unknown) {
  status.msg = "失敗: " + (e instanceof Error ? e.message : String(e));
  status.error = true;
}

async function handleAnalyze(file: File | null) {
  const trimmed = url.value.trim();
  if (!trimmed && !file) {
    status.msg = "YouTube URL かファイルを指定してください";
    status.error = true;
    return;
  }
  busy.value = true;
  status.msg = "解析中… 30秒〜数分かかることがあります";
  status.error = false;
  try {
    const params: AnalyzeParams = { mode: mode.value, chordStyle: chordStyle.value, url: trimmed, file };
    const res = await analyze(params);
    result.value = res;
    // ファイル入力時はアップロードしたメディアを再生、URL入力時はYouTube埋め込み
    playerUrl.value = file ? "" : trimmed;
    status.msg = `完了: ${res.meta.title}（${res.meta.duration.toFixed(1)}秒）`;
    status.error = false;
  } catch (e) {
    failWith(e);
  } finally {
    busy.value = false;
  }
}

async function handleImport(file: File) {
  status.msg = "JSONを取り込み中…";
  status.error = false;
  try {
    const res = await importAnalysis(file);
    result.value = res;
    playerUrl.value = url.value.trim();
    status.msg = "取り込み完了: " + res.meta.title;
    status.error = false;
  } catch (e) {
    failWith(e);
  }
}
</script>

<template>
  <div>
    <header>
      <h1>🎸 Guitar Auto Tab</h1>
      <p class="sub">YouTube・音声/動画ファイルからギタータブ譜を自動生成（個人利用・完全無料）</p>
    </header>

    <main>
      <section class="panel controls">
        <ModeSelector
          :mode="mode"
          :chord-style="chordStyle"
          @update:mode="mode = $event"
          @update:chord-style="chordStyle = $event"
        />
        <SourceForm
          :url="url"
          :busy="busy"
          @update:url="url = $event"
          @analyze="handleAnalyze"
        />
        <div class="status" :class="{ error: status.error }">{{ status.msg }}</div>
      </section>

      <section v-if="result" class="panel viewer">
        <PlayerPanel :result="result" :source-url="playerUrl" :time-source="timeSource" />
        <FrameLink :result="result" :time-source="timeSource" />
        <TabToolbar :result="result" @import="handleImport" />
        <TabViewer :result="result" :time-source="timeSource" />
        <p class="hint">
          ▶ 再生するとカーソルがタブ譜の現在位置に追従します。
          <br />
          精度を上げたいときは「analysis.json書き出し」でデータを保存し、Claude Code
          に渡して採譜を磨いてもらってから
          「磨き上げJSONを取り込み」で読み込むと、表示・PDF/TXT保存に反映されます。
        </p>
      </section>
    </main>
  </div>
</template>
