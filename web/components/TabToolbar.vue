<script setup lang="ts">
import { computed } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import { jobUrl, type ArtifactName } from "~/utils/api";

const props = defineProps<{
  result: AnalysisResult;
}>();

const emit = defineEmits<{
  (e: "import", file: File): void;
}>();

const title = computed(() => {
  const modeLabel = props.result.meta.mode === "melody" ? "メロディ(単音)" : "コード(バッキング)";
  const sepLabel = props.result.meta.separated ? " / 音源分離: ON" : "";
  return `${props.result.meta.title} — ${modeLabel} / ${props.result.meta.tempo} BPM${sepLabel}`;
});

function save(name: ArtifactName) {
  window.location.href = jobUrl(props.result.id, name);
}

function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const f = input.files?.[0];
  if (f) emit("import", f);
  input.value = "";
}
</script>

<template>
  <div class="tab-toolbar">
    <span class="tab-title">{{ title }}</span>
    <div class="spacer" />
    <button @click="save('tab.pdf')">PDF保存</button>
    <button @click="save('tab.txt')">TXT保存</button>
    <button @click="save('analysis.json')">analysis.json書き出し</button>
    <label class="file-btn">
      磨き上げJSONを取り込み
      <input
        type="file"
        accept=".json,application/json"
        hidden
        @change="onImportFile"
      />
    </label>
  </div>
</template>
