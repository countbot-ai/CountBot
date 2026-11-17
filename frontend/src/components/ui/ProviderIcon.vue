<template>
  <span class="provider-icon" :style="style">
    <span
      v-if="visual.glyph"
      class="provider-icon-glyph"
      v-html="visual.glyph"
    />
    <component v-else-if="visual.icon" :is="visual.icon" :size="size" />
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { resolveProviderVisual } from '@/utils/providerIcons'

interface Props {
  providerId: string
  /** 图标边长（字形与容器同尺寸） */
  size?: number
}

const props = withDefaults(defineProps<Props>(), {
  size: 22,
})

const visual = computed(() => resolveProviderVisual(props.providerId))

const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${props.size}px`,
  color: visual.value.color,
}))
</script>

<style scoped>
/**
 * 供应商图标：不加底座、描边、圆角，直接放品牌字形。
 * public 字形是内联 SVG，靠 currentColor 着色，需要 :deep 才能命中注入节点。
 */
.provider-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.provider-icon-glyph {
  display: flex;
  line-height: 1;
}

.provider-icon-glyph :deep(svg) {
  display: block;
  width: 1em;
  height: 1em;
}
</style>
