<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import { toTabEvents, type TabEvent } from "~/shared/events";
import type { TimeSource } from "~/composables/useTimeSource";

const props = defineProps<{
  result: AnalysisResult;
  timeSource: TimeSource;
}>();

/* ===== 描画定数 ===== */
const PX_PER_SEC = 72;
const LEFT_PAD = 44;
const STAFF_TOP = 110;
const STAFF_GAP = 18;
const STRING_NAMES = ["e", "B", "G", "D", "A", "E"];

/** 同時発音（複数本指・ダブルストップ）をまとめたタブイベント（共通ロジックは shared/events.ts） */
const events = computed<TabEvent[]>(() => {
  if (props.result.meta.mode === "melody") {
    return toTabEvents(props.result.notes || []);
  }
  const evs: TabEvent[] = (props.result.chords || []).map((c) => ({
    start: c.start,
    end: c.end,
    cells: (c.shape || []).map((s) => ({ row: s.string - 1, text: String(s.fret) })),
    label: c.label || null,
  }));
  return evs.sort((a, b) => a.start - b.start);
});

const dur = computed(() => Math.max(props.result.meta.duration || 1, 1));
const width = computed(() => Math.max(900, Math.ceil(dur.value * PX_PER_SEC) + LEFT_PAD + 60));
const height = STAFF_TOP + 5 * STAFF_GAP + 70;
const bars = computed(() => (props.result.barlines.length ? props.result.barlines : [0, dur.value]));

const svgEl = ref<SVGSVGElement | null>(null);
const scrollEl = ref<HTMLElement | null>(null);
const cursorEl = ref<SVGLineElement | null>(null);

// 結果が更新されたら先頭へスクロール
watch(
  () => props.result.id,
  () => {
    if (scrollEl.value) scrollEl.value.scrollLeft = 0;
  },
);

// 再生位置の追従（カーソル・ハイライト・自動スクロール）— 60fpsで直接DOM操作
let raf = 0;
function tick() {
  const t = props.timeSource.current?.() ?? 0;
  const x = t * PX_PER_SEC + LEFT_PAD;

  const cursor = cursorEl.value;
  if (cursor) {
    cursor.setAttribute("x1", String(x));
    cursor.setAttribute("x2", String(x));
  }

  const sc = scrollEl.value;
  if (sc && (x - sc.scrollLeft > sc.clientWidth - 140 || x < sc.scrollLeft)) {
    sc.scrollLeft = Math.max(0, x - sc.clientWidth / 3);
  }

  const svg = svgEl.value;
  if (svg) {
    svg.querySelectorAll<SVGRectElement>("rect.ev").forEach((rect) => {
      const s = Number(rect.dataset.start);
      const e = Number(rect.dataset.end);
      rect.classList.toggle("active", t >= s && t < e);
    });
    svg.querySelectorAll<SVGRectElement>("rect.evrow").forEach((rect) => {
      const s = Number(rect.dataset.start);
      const e = Number(rect.dataset.end);
      rect.classList.toggle("active", t >= s && t < e);
    });
  }

  raf = requestAnimationFrame(tick);
}

onMounted(() => {
  raf = requestAnimationFrame(tick);
});

onBeforeUnmount(() => cancelAnimationFrame(raf));

/** イベントの背景/行ハイライトの矩形 */
function evBox(ev: TabEvent) {
  const x = ev.start * PX_PER_SEC + LEFT_PAD;
  const w = Math.max(30, (Math.max(ev.end, ev.start + 0.15) - ev.start) * PX_PER_SEC);
  return { x: x - 8, w };
}
</script>

<template>
  <div ref="scrollEl" class="tab-scroll">
    <svg
      ref="svgEl"
      class="tab-svg"
      xmlns="http://www.w3.org/2000/svg"
      :width="width"
      :height="height"
    >
      <!-- イベント背景ハイライト -->
      <rect
        v-for="(ev, i) in events"
        :key="`bg${i}`"
        class="ev"
        :data-start="ev.start"
        :data-end="ev.end"
        :x="evBox(ev).x"
        :y="STAFF_TOP - 34"
        :width="evBox(ev).w"
        :height="5 * STAFF_GAP + 52"
        rx="5"
      />

      <!-- 譜線 -->
      <g v-for="(name, r) in STRING_NAMES" :key="`st${r}`">
        <line
          :x1="LEFT_PAD - 8"
          :y1="STAFF_TOP + r * STAFF_GAP"
          :x2="width"
          :y2="STAFF_TOP + r * STAFF_GAP"
          class="staff"
        />
        <text x="12" :y="STAFF_TOP + r * STAFF_GAP + 5" class="sname">{{ name }}</text>
      </g>

      <!-- 小節線 -->
      <line
        v-for="(b, i) in bars"
        :key="`bar${i}`"
        :x1="b * PX_PER_SEC + LEFT_PAD"
        :y1="STAFF_TOP"
        :x2="b * PX_PER_SEC + LEFT_PAD"
        :y2="STAFF_TOP + 5 * STAFF_GAP"
        class="bar"
      />

      <!-- 鳴っている弦の行ハイライト（ブリッジ側の映像と照合しやすく） -->
      <template v-for="(ev, i) in events" :key="`rows${i}`">
        <rect
          v-for="(c, j) in ev.cells"
          v-show="c.row >= 0 && c.row <= 5"
          :key="`row${i}_${j}`"
          class="evrow"
          :data-start="ev.start"
          :data-end="ev.end"
          :x="evBox(ev).x"
          :y="STAFF_TOP + c.row * STAFF_GAP - 7"
          :width="evBox(ev).w"
          height="14"
          rx="4"
        />
      </template>

      <!-- ノート / コード -->
      <g v-for="(ev, i) in events" :key="`ev${i}`">
        <text
          v-for="(c, j) in ev.cells"
          v-show="c.row >= 0 && c.row <= 5"
          :key="j"
          :x="ev.start * PX_PER_SEC + LEFT_PAD"
          :y="STAFF_TOP + c.row * STAFF_GAP + 5"
          class="fret"
          text-anchor="middle"
        >
          {{ c.text }}
        </text>
        <text
          v-if="ev.label"
          :x="ev.start * PX_PER_SEC + LEFT_PAD"
          :y="STAFF_TOP - 38"
          class="chlabel"
        >
          {{ ev.label }}
        </text>
      </g>

      <!-- 再生カーソル -->
      <line
        ref="cursorEl"
        :x1="LEFT_PAD"
        :y1="STAFF_TOP - 34"
        :x2="LEFT_PAD"
        :y2="STAFF_TOP + 5 * STAFF_GAP + 30"
        class="cursor"
      />
    </svg>
  </div>
</template>
