<template>
  <div class="memory-panel">
    <!-- 查看模式 -->
    <MemoryViewer
      v-if="mode === 'view'"
      @edit="handleEdit"
    />

    <!-- 编辑模式 -->
    <MemoryEditor
      v-else-if="mode === 'edit'"
      @close="handleCloseEditor"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import MemoryViewer from './MemoryViewer.vue'
import MemoryEditor from './MemoryEditor.vue'

type Mode = 'view' | 'edit'

// 状态
const mode = ref<Mode>('view')

// 方法
const handleEdit = () => {
    mode.value = 'edit'
}

const handleCloseEditor = () => {
    mode.value = 'view'
}

const handleSaved = () => {
    mode.value = 'view'
}

// 暴露方法供父组件调用
defineExpose({
    switchToView: () => {
        mode.value = 'view'
    },
})
</script>

<style scoped>
.memory-panel {
    height: 100%;
    overflow: hidden;
    background: var(--bg-secondary, #f9fafb);
}

/* 深色模式 */
:root[data-theme="dark"] .memory-panel {
    background: var(--bg-secondary, #111827);
}
</style>
