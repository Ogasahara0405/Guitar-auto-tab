<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { AnalysisResult } from "~/shared/schema";
import type { TimeSource } from "~/composables/useTimeSource";
import { mediaUrl } from "~/utils/api";
import { createYTPlayer, extractYouTubeId, loadYouTubeAPI, type YTPlayer } from "~/utils/youtube";

const props = defineProps<{
  result: AnalysisResult;
  /** YouTube URL（空なら result のメディアファイルを再生） */
  sourceUrl: string;
  timeSource: TimeSource;
}>();

type Kind = "youtube" | "video" | "audio" | "none";

function isVideoFile(name: string): boolean {
  return /\.(mp4|webm|mkv|mov|avi|m4v)$/i.test(name);
}

const kind = computed<Kind>(() => {
  if (props.sourceUrl) return extractYouTubeId(props.sourceUrl) ? "youtube" : "none";
  const mf = props.result.meta.media_file;
  if (!mf) return "none";
  return isVideoFile(mf) ? "video" : "audio";
});

const src = computed(() => mediaUrl(props.result.id));

const ytHost = ref<HTMLElement | null>(null);
const mediaEl = ref<HTMLVideoElement | HTMLAudioElement | null>(null);
let player: YTPlayer | null = null;
let cancelled = false;

function teardown() {
  props.timeSource.current = () => 0;
  try {
    player?.destroy();
  } catch {
    /* プレイヤー未初期化 */
  }
  player = null;
  if (ytHost.value) ytHost.value.innerHTML = "";
}

function setup() {
  cancelled = false;
  teardown();
  if (kind.value === "none") return;

  if (kind.value === "youtube") {
    const videoId = extractYouTubeId(props.sourceUrl);
    if (!videoId) return;
    loadYouTubeAPI().then(() => {
      if (cancelled || !ytHost.value || !videoId) return;
      const host = ytHost.value;
      host.innerHTML = "";
      const mount = document.createElement("div");
      host.appendChild(mount);
      player = createYTPlayer(mount, videoId, () => {
        props.timeSource.current = () => {
          try {
            return player?.getCurrentTime() || 0;
          } catch {
            return 0;
          }
        };
      });
    });
    return;
  }

  // <video> / <audio> によるローカルメディア再生
  props.timeSource.current = () => mediaEl.value?.currentTime || 0;
}

// テンプレート ref はマウント後にしか存在しないので、初回は onMounted で開始する
watch(() => [kind.value, props.sourceUrl, props.result.id], setup);
onMounted(() => {
  setup();
});

onBeforeUnmount(() => {
  cancelled = true;
  teardown();
});
</script>

<template>
  <div v-if="kind !== 'none'" class="player-wrap">
    <div v-show="kind === 'youtube'" ref="ytHost" />
    <video v-if="kind === 'video'" ref="mediaEl" controls playsinline :src="src" />
    <audio v-if="kind === 'audio'" ref="mediaEl" controls :src="src" />
  </div>
</template>
