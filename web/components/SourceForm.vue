<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  url: string;
  busy: boolean;
}>();

const emit = defineEmits<{
  (e: "update:url", v: string): void;
  (e: "analyze", file: File | null): void;
}>();

const file = ref<File | null>(null);

function onUrlInput(e: Event) {
  emit("update:url", (e.target as HTMLInputElement).value);
}

function onFileChange(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null;
}
</script>

<template>
  <div class="row">
    <div class="group grow">
      <label for="url">YouTube URL</label>
      <input
        id="url"
        type="text"
        placeholder="https://www.youtube.com/watch?v=..."
        :value="url"
        @input="onUrlInput"
      />
    </div>
    <div class="group">
      <label for="file">または ファイル</label>
      <input id="file" type="file" accept="audio/*,video/*" @change="onFileChange" />
    </div>
    <button class="primary" :disabled="busy" @click="emit('analyze', file)">解析開始</button>
  </div>
</template>
