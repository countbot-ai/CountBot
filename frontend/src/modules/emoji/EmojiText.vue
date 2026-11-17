<template>
  <span class="emoji-text">
    <template v-for="(segment, index) in segments" :key="index">
      <span
        v-if="segment.type === 'emoji'"
        class="wx-emoji"
        role="img"
        :aria-label="segment.code"
        :title="segment.code"
      >{{ segment.value }}</span>
      <template v-else>{{ segment.value }}</template>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { parseWechatEmojiText } from './wechatEmoji'

interface Props {
  text: string
}

const props = defineProps<Props>()

const segments = computed(() => parseWechatEmojiText(props.text || ''))
</script>
