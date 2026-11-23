<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import {
  buildTabLayout,
  beamGroups,
  flagCount,
  SLOT_W,
  STAFF_GAP,
  STAFF_LEFT,
  TOP_PAD,
  type LayoutEvent,
} from "~/shared/tabLayout";
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

/** 段ごとのビーム単位（連続する同音価をつなぐ） */
const beamsBySystem = computed(() =>
  layout.value.systems.map((sys) => beamGroups(sys.events, layout.value.slotsPerBeat)),
);

/** ビームで結ばれるイベント index（ビームがある音符にフラグは付けない＝標準記譜） */
const beamedIndex = computed(() => {
  const s = new Set<number>();
  for (const groups of beamsBySystem.value) {
    for (const g of groups) for (const ev of g) s.add(ev.index);
  }
  return s;
});

/* ===== ハイライト（変化時のみDOM操作 → カクつき防止） ===== */
// ノード参照はレイアウト確定時に一度だけキャッシュし、毎フレームの走査を行わない
interface EvNodes {
  hl: Element[];
  text: SVGTextElement[];
}
const evNodes = new Map<number, EvNodes>();
const cursorNodes = new Map<number, SVGLineElement>();

function clearActiveClasses() {
  for (const e of evNodes.values()) {
    for (const el of e.hl) el.classList.remove("active");
    for (const el of e.text) el.classList.remove("active");
  }
}

function rebuildCache() {
  clearActiveClasses(); // 安全網: 古いノードの残りハイライトを消す
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

/** フレット/背景のハイライト切替のみ担当（カーソルは tick が管理する） */
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

  if (nextSystem >= 0 && nextSystem !== activeSystem.value) {
    activeSystem.value = nextSystem;
    // 段が変わったらその段を表示域に（コンテナ内のみ・ページは動かさない）
    const sc = scrollEl.value;
    const el = sc?.querySelector<HTMLElement>(`[data-system="${nextSystem}"]`);
    if (sc && el) {
      const r = el.getBoundingClientRect();
      const sr = sc.getBoundingClientRect();
      if (r.top < sr.top + 8) sc.scrollTop += r.top - sr.top - 8;
      else if (r.bottom > sr.bottom - 8) sc.scrollTop += r.bottom - sr.bottom + 8;
    }
  }
}
const activeSystem = ref(-1);

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

  // カーソル表示/位置は timeToX 基準で毎フレーム更新（休符中も維持）
  const loc = layout.value.timeToX(t);
  if (loc) {
    for (const [si, line] of cursorNodes) {
      const show = si === loc.system;
      if ((line.style.display === "none") === show) {
        line.style.display = show ? "" : "none";
      }
    }
    const line = cursorNodes.get(loc.system);
    if (line) {
      line.setAttribute("x1", String(loc.x));
      line.setAttribute("x2", String(loc.x));
    }
    // 段内横方向の追従（カーソルが見えたらしくならないように）
    const sc = scrollEl.value;
    if (sc && loc.x - sc.scrollLeft > sc.clientWidth - 60) {
      sc.scrollLeft = Math.max(0, loc.x - sc.clientWidth / 3);
    } else if (sc && loc.x < sc.scrollLeft) {
      sc.scrollLeft = Math.max(0, loc.x - 40);
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
    clearActiveClasses(); // リセット時の残りハイライトを防ぐ
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

          <!-- 拍子記号（先頭の段のみ・弦名と重ならないよう譜線の左に配置） -->
          <g v-if="si === 0" :transform="`translate(15, ${TOP_PAD - 8})`" class="timesig">
            <text x="0" y="14" class="timesig-num">4</text>
            <text x="0" y="38" class="timesig-num">4</text>
          </g>

          <!-- 譜線6本（1弦=上） -->
          <line
            v-for="r in 6"
            :key="'st' + r"
            :x1="STAFF_LEFT"
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

          <!-- 音価ステム（whole 以外） -->
          <line
            v-for="ev in sys.events.filter((e) => stemVisible(e))"
            :key="'stem' + ev.index"
            :x1="ev.x + 8"
            :y1="STAFF_BOTTOM + 4"
            :x2="ev.x + 8"
            :y2="STAFF_BOTTOM + 4 + STEM_LEN"
            class="stem"
          />
          <!-- フラグ: ビームに属さない音符のみ（標準記譜ではビーム時はフラグなし） -->
          <template v-for="ev in sys.events" :key="'flags' + ev.index">
            <line
              v-for="f in beamedIndex.has(ev.index) ? [] : flagCount(ev.rhythm)"
              :key="'fl' + ev.index + '_' + f"
              :x1="ev.x + 8"
              :y1="STAFF_BOTTOM + 4 + STEM_LEN - (f - 1) * 6"
              :x2="ev.x + 15"
              :y2="STAFF_BOTTOM + 8 + STEM_LEN - (f - 1) * 6"
              class="flag"
            />
          </template>
          <!-- ビーム: 音価に応じた本数の平行ビーム -->
          <template v-for="(group, gi) in beamsBySystem[si]" :key="'beamgrp' + gi">
            <line
              v-for="b in flagCount(group[0].rhythm)"
              :key="'beam' + gi + '_' + b"
              :x1="group[0].x + 8"
              :y1="STAFF_BOTTOM + 4 + STEM_LEN - (b - 1) * 5"
              :x2="group[group.length - 1].x + 8"
              :y2="STAFF_BOTTOM + 4 + STEM_LEN - (b - 1) * 5"
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

          <!-- 再生カーソル（tick が表示段と位置を更新） -->
          <line
            class="cursor"
            :data-cursor="si"
            :x1="STAFF_LEFT"
            :y1="TOP_PAD - 34"
            :x2="STAFF_LEFT"
            :y2="STAFF_BOTTOM + 42"
            style="display: none"
          />
        </svg>
      </div>
    </div>
  </div>
</template>
