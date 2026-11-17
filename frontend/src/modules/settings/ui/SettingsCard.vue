<template>
  <section class="co-card" :class="[{ 'co-card--plain': !title && !$slots.header }, variant === 'danger' && 'co-card--danger']">
    <header v-if="title || $slots.header" class="co-card-head">
      <div class="co-card-head-text">
        <slot name="header">
          <h2 class="co-card-title">{{ title }}</h2>
          <p v-if="description" class="co-card-desc">{{ description }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="co-card-actions">
        <slot name="actions" />
      </div>
    </header>

    <div class="co-card-body" :class="{ 'is-flush': flush }">
      <slot />
    </div>

    <footer v-if="$slots.footer" class="co-card-foot">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 分组标题；为空时渲染成无头分组（只作为行的容器） */
    title?: string
    description?: string
    /** 内容自带内边距（行式布局）时去掉 body 的 padding */
    flush?: boolean
    /** danger：危险操作专用分组，独立成块与外层隔离 */
    variant?: 'default' | 'danger'
  }>(),
  {
    variant: 'default',
  },
)
</script>
