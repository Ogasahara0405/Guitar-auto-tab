<script setup lang="ts">
import type { ChordStyle, Mode } from "~/shared/schema";

defineProps<{
  mode: Mode;
  chordStyle: ChordStyle;
}>();

const emit = defineEmits<{
  (e: "update:mode", v: Mode): void;
  (e: "update:chordStyle", v: ChordStyle): void;
}>();
</script>

<template>
  <div class="row">
    <div class="group">
      <label>出力したいパート</label>
      <div class="radios">
        <label>
          <input
            type="radio"
            name="mode"
            :checked="mode === 'melody'"
            @change="emit('update:mode', 'melody')"
          />
          メロディ（単音・リード）
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            :checked="mode === 'chords'"
            @change="emit('update:mode', 'chords')"
          />
          コード（バッキング）
        </label>
      </div>
    </div>

    <div v-if="mode === 'chords'" class="group">
      <label>バッキングの出力形式</label>
      <div class="radios">
        <label>
          <input
            type="radio"
            name="chord_style"
            :checked="chordStyle === 'chord'"
            @change="emit('update:chordStyle', 'chord')"
          />
          コード
        </label>
        <label>
          <input
            type="radio"
            name="chord_style"
            :checked="chordStyle === 'power'"
            @change="emit('update:chordStyle', 'power')"
          />
          パワーコード
        </label>
      </div>
    </div>
  </div>
</template>
