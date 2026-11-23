<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import { buildTabLayout, beamGroups, flagCount, SLOT_W, STAFF_GAP, TOP_PAD, type LayoutEvent } from "~/shared/tabLayout";
import type { TimeSource } from "~/composables/useTimeSource";

const props = defineProps<{
  result: AnalysisResult;
  timeSource: TimeSource;
}>();

const STAFF_BOTTOM = TOP_PAD + 5 * STAFF_GAP;
const STEM_LEN = 24;

/* ===== レイアウト（Guitar Pro 風: 小節単位で折り返した段＋音価ステム） ===== */
const scrollEl = ref<HTMLElement | null>(null);
const containerWidth = ref(1100);
let resizeObs: ResizeObserver | null = null;

const layout = computed(() =>
  buildTabLayout(props.result, { containerWidth: containerWidth.value }),
);
const slotsPerBeat = computed(() => {
  const m = layout.value.score.measures[0];
  const beatDur = 60 / (props.result.meta.tempo || 120);
  return Math.max(1, Math.round(m.slots / Math.max((m.end - m.start) / beatDur, 1e-6)));
});

/** 段ごとのビーム単位（連続する同音価をつなぐ） */
const beamsBySystem = computed(() =>
  layout.value.systems.map((sys) => beamGroups(sys.events, slotsPerBeat.value)),
);

/* ===== カーソル・ハイライト（変化時のみDOM操作 → カクつき防止） ===== */
// ノード参照はレイアウト確定時に一度だけキャッシュし、毎フレームの走査を行わない
interface EvNodes {
  hl: Element[];
  text: SVGTextElement[];
}
const evNodes = new Map<number, EvNodes>();
const cursorNodes = new Map<number, SVGLineElement>();

function rebuildCache() {
  evNodes.clear();
  cursorNodes.clear();
  const root = scrollEl.value;
  if (!root) return;
  for (const el of root.querySelectorAll("[data-ev]")) {
    const idx = Number(el.getAttribute("data-ev"));
    const entry = evNodes.get(idx) ?? { hl: [], text: [] };
    if (el.tagName === "text") entry.text.push(el as SVGTextElement);
    else entry.hl.push(el);
    evNodes.set(idx, entry);
  }
  for (const el of root.querySelectorAll("[data-cursor]")) {
    cursorNodes.set(Number(el.getAttribute("data-cursor")), el as SVGLineElement);
  }
}

const activeIndex = ref(-1);
const activeSystem = ref(-1);

function setActive(next: number, nextSystem: number) {
  const prev = activeIndex.value;
  if (prev === next) return;
  const apply = (idx: number, on: boolean) => {
    const e = evNodes.get(idx);
    if (!e) return;
    for (const el of e.hl) el.classList.toggle("active", on);
    for (const el of e.text) el.classList.toggle("active", on);
  };
  if (prev >= 0) apply(prev, false);
  if (next >= 0) apply(next, true);
  activeIndex.value = next;

  // カーソルはアクティブな段にのみ表示
  for (const [si, line] of cursorNodes) {
    line.style.display = si === nextSystem ? "" : "none";
  }
  if (nextSystem !== activeSystem.value) {
    activeSystem.value = nextSystem;
    // 段が変わったらその段を表示域に（毎フレームではなく段の変わり目だけ）
    if (nextSystem >= 0) {
      const el = scrollEl.value?.querySelector<HTMLElement>(`[data-system="${nextSystem}"]`);
      el?.scrollIntoView({ block: "nearest", behavior: "auto" });
    }
  }
}

let raf = 0;
function tick() {
  const t = props.timeSource.current?.() ?? 0;
  const evs = layout.value.events;

  // アクティブイベント: 時刻が最後に始まったもの
  let idx = -1;
  for (let i = 0; i < evs.length; i++) {
    if (evs[i].time <= t + 0.02) idx = i;
    else break;
  }
  setActive(idx, idx >= 0 ? evs[idx].system : activeSystem.value);

  // カーソル位置（段内 x を時間補間で算出）
  const loc = layout.value.timeToX(t);
  if (loc) {
    const line = cursorNodes.get(loc.system);
    if (line) {
      line.setAttribute("x1", String(loc.x));
      line.setAttribute("x2", String(loc.x));
    }
  }
  raf = requestAnimationFrame(tick);
}

onMounted(() => {
  const el = scrollEl.value;
  if (el) {
    containerWidth.value = el.clientWidth || 1100;
    resizeObs = new ResizeObserver(() => {
      if (el.clientWidth > 200) containerWidth.value = el.clientWidth;
    });
    resizeObs.observe(el);
  }
  void nextTick(rebuildCache);
  raf = requestAnimationFrame(tick);
});

onBeforeUnmount(() => {
  cancelAnimationFrame(raf);
  resizeObs?.disconnect();
  evNodes.clear();
  cursorNodes.clear();
});

watch(
  () => [props.result.id, containerWidth.value],
  () => {
    activeIndex.value = -1;
    activeSystem.value = -1;
    if (scrollEl.value) scrollEl.value.scrollTop = 0;
    void nextTick(rebuildCache);
  },
);

/** ステム/フラグ/ビームの描画（音価 = スロット長） */
function stemVisible(ev: LayoutEvent): boolean {
  return ev.rhythm !== "whole";
}
</script>

<template>
  <div ref="scrollEl" class="tab-scroll">
    <div class="tab-systems">
      <div
        v-for="(sys, si) in layout.systems"
        :key="si"
        class="tab-system"
        :data-system="si"
      >
        <svg
          class="tab-svg"
          xmlns="http://www.w3.org/2000/svg"
          :width="sys.width"
          :height="layout.systemHeight"
        >
          <!-- 小節番号（各小節の頭に小さく） -->
          <text
            v-for="m in sys.measures"
            :key="'num' + m.index"
            :x="m.x + 2"
            :y="TOP_PAD - 26"
            class="barnum"
          >
            {{ m.index + 1 }}
          </text>

          <!-- 拍子記号（先頭の段のみ・標準的な 4/4 表記） -->
          <g v-if="si === 0" :transform="`translate(2, ${TOP_PAD - 8})`" class="timesig">
            <text x="0" y="14" class="timesig-num">4</text>
            <text x="0" y="38" class="timesig-num">4</text>
          </g>

          <!-- 譜線6本（1弦=上） -->
          <line
            v-for="r in 6"
            :key="'st' + r"
            :x1="12"
            :y1="TOP_PAD + (r - 1) * STAFF_GAP"
            :x2="sys.width - 12"
            :y2="TOP_PAD + (r - 1) * STAFF_GAP"
            class="staff"
          />
          <!-- 弦名 -->
          <text
            v-for="(name, r) in ['e', 'B', 'G', 'D', 'A', 'E']"
            :key="'sn' + r"
            x="2"
            :y="TOP_PAD + r * STAFF_GAP + 4"
            class="sname"
          >
            {{ name }}
          </text>

          <!-- 小節線 -->
          <line
            v-for="m in sys.measures"
            :key="'bar' + m.index"
            :x1="m.x"
            :y1="TOP_PAD"
            :x2="m.x"
            :y2="STAFF_BOTTOM"
            class="bar"
          />
          <!-- 段末の締め -->
          <line
            :x1="sys.width - 12"
            :y1="TOP_PAD"
            :x2="sys.width - 12"
            :y2="STAFF_BOTTOM"
            class="bar"
          />

          <!-- イベント背景（アクティブ時のハイライト） -->
          <rect
            v-for="ev in sys.events"
            :key="'bg' + ev.index"
            class="ev"
            :data-ev="ev.index"
            :x="ev.x - 9"
            :y="TOP_PAD - 16"
            :width="Math.max(18, ev.slotsLen * SLOT_W)"
            :height="5 * STAFF_GAP + 32"
            rx="4"
          />

          <!-- コード名 -->
          <text
            v-for="ev in sys.events.filter((e) => e.label)"
            :key="'lb' + ev.index"
            :x="ev.x"
            :y="TOP_PAD - 34"
            class="chlabel"
            text-anchor="middle"
          >
            {{ ev.label }}
          </text>

          <!-- 音価ステム/フラグ（ビームは下端でつなぐ） -->
          <template v-for="ev in sys.events" :key="'stem' + ev.index">
            <line
              v-if="stemVisible(ev)"
              :x1="ev.x + 8"
              :y1="STAFF_BOTTOM + 4"
              :x2="ev.x + 8"
              :y2="STAFF_BOTTOM + 4 + STEM_LEN"
              class="stem"
            />
            <line
              v-for="f in flagCount(ev.rhythm)"
              :key="'fl' + ev.index + '_' + f"
              :x1="ev.x + 8"
              :y1="STAFF_BOTTOM + 4 + STEM_LEN - (f - 1) * 6"
              :x2="ev.x + 15"
              :y2="STAFF_BOTTOM + 8 + STEM_LEN - (f - 1) * 6"
              class="flag"
            />
          </template>
          <template v-for="(group, gi) in beamsBySystem[si]" :key="'bg' + gi">
            <line
              :x1="group[0].x + 8"
              :y1="STAFF_BOTTOM + 4 + STEM_LEN"
              :x2="group[group.length - 1].x + 8"
              :y2="STAFF_BOTTOM + 4 + STEM_LEN"
              class="beam"
            />
          </template>

          <!-- フレット数字と弦行ハイライト -->
          <template v-for="ev in sys.events" :key="'ev' + ev.index">
            <rect
              v-for="(cell, ci) in ev.rows"
              :key="'row' + ev.index + '_' + ci"
              class="evrow"
              :data-ev="ev.index"
              :x="ev.x - 9"
              :y="TOP_PAD + cell.row * STAFF_GAP - 8"
              :width="Math.max(18, ev.slotsLen * SLOT_W)"
              height="16"
              rx="3"
            />
            <text
              v-for="(cell, ci) in ev.rows"
              :key="'tx' + ev.index + '_' + ci"
              class="fret"
              :data-ev="ev.index"
              :x="ev.x"
              :y="TOP_PAD + cell.row * STAFF_GAP + 5"
              text-anchor="middle"
            >
              {{ cell.text }}
            </text>
          </template>

          <!-- 再生カーソル（アクティブな段のみ表示） -->
          <line
            class="cursor"
            :data-cursor="si"
            :x1="12"
            :y1="TOP_PAD - 34"
            :x2="12"
            :y2="STAFF_BOTTOM + 42"
            style="display: none"
          />
        </svg>
      </div>
    </div>
  </div>
</template>
