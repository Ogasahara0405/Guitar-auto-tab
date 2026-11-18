<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import type { TimeSource } from "~/composables/useTimeSource";
import { frameUrl } from "~/utils/api";

const props = defineProps<{
  result: AnalysisResult;
  timeSource: TimeSource;
}>();

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
const entries = computed<FrameEntry[]>(() => {
  const out: FrameEntry[] = [];
  if (props.result.meta.mode === "melody") {
    for (const n of props.result.notes || []) {
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
    for (const c of props.result.chords || []) {
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
});

const current = ref<FrameEntry | null>(null);
let timer = 0;

onMounted(() => {
  timer = window.setInterval(() => {
    const t = props.timeSource.current?.() ?? 0;
    let cur: FrameEntry | null = null;
    for (const e of entries.value) {
      if (t >= e.start - 0.05 && t < e.end + 0.4) {
        cur = e;
        if (t < e.end) break;
      }
    }
    if (current.value?.frame !== cur?.frame) current.value = cur;
  }, 160);
});

onBeforeUnmount(() => window.clearInterval(timer));
watch(
  () => props.result.id,
  () => (current.value = null),
);

const caption = computed(() => {
  const cur = current.value;
  if (!cur) {
    return "再生すると、その位置の映像フレーム（ブリッジ側で弦の確認が可能）が表示されます";
  }
  const cells = cur.cells.map((c) => `${c.string}弦/${c.fret}`).join(" ");
  const parts = [`${cur.start.toFixed(2)}秒`, cells];
  if (cur.label) parts.unshift(cur.label);
  if (cur.muted.length) {
    parts.push(`ミュート(音声確認で不鳴): ${cur.muted.join(",")}弦`);
  }
  return parts.join(" — ");
});
</script>

<template>
  <div v-if="entries.length" class="frame-link">
    <div class="frame-img">
      <img
        v-if="current"
        :key="current.frame"
        :src="frameUrl(result.id, current.frame)"
        :alt="`映像フレーム ${current.start.toFixed(2)}秒`"
      />
      <div v-else class="frame-placeholder">映像フレーム</div>
    </div>
    <div class="frame-caption">{{ caption }}</div>
  </div>
</template>
