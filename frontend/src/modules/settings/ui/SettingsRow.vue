<template>
  <div class="co-row" :class="[`co-row--${layout}`, { 'co-row--wide-control': wideControl }]">
    <div class="co-row-label">
      <div class="co-row-title">
        <slot name="label">{{ label }}</slot>
        <span v-if="badge" class="co-row-badge">{{ badge }}</span>
      </div>
      <p v-if="description" class="co-row-desc">{{ description }}</p>
    </div>

    <div class="co-row-control" :class="{ 'co-row-control--error': Boolean(error) }">
      <div v-if="$slots.detail" class="co-row-detail">
        <slot name="detail" />
      </div>
      <slot />
    </div>

    <div v-if="$slots.below" class="co-row-below">
      <slot name="below" />
    </div>

    <p v-if="error" class="co-row-error">{{ error }}</p>
    <p v-else-if="hint" class="co-row-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    description?: string
    /** 标签右侧的弱化标注，例如「已启用」 */
    badge?: string
    /** inline：控件靠右单列；block：控件独占一整行（文本域、列表、多选） */
    layout?: 'inline' | 'block'
    /** 只对 inline 生效：控件列放宽到 280px，用于输入框加按钮这类组合 */
    wideControl?: boolean
    /** 行下方的补充说明，与 description 区分：description 讲「是什么」，hint 讲「注意什么」 */
    hint?: string
    /** 校验错误：非空时以危险色显示在行下方，并把同行控件描边标红 */
    error?: string
  }>(),
  {
    layout: 'inline',
    wideControl: false,
  },
)
</script>
