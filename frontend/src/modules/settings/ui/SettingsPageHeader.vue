<template>
  <header class="co-page-head">
    <div class="co-page-head-text">
      <h1 class="co-page-title">{{ title }}</h1>
      <p v-if="description" class="co-page-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="co-page-head-extra">
      <slot />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>
