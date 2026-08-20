<template>
  <div class="memory-panel">
    <MemoryViewer
      v-if="mode === 'view'"
      :tab="tab"
      @edit="handleEdit"
      @change-tab="handleChangeTab"
    />

    <MemoryEditor
      v-else
      :target="editTarget"
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
type MemoryTab = 'long-term'

const mode = ref<Mode>('view')
const tab = ref<MemoryTab>('long-term')
const editTarget = ref<MemoryTab>('long-term')

const handleEdit = (target: MemoryTab) => {
  editTarget.value = target
  mode.value = 'edit'
}

const handleChangeTab = (target: MemoryTab) => {
  tab.value = target
}

const handleCloseEditor = () => {
  mode.value = 'view'
}

const handleSaved = () => {
  tab.value = editTarget.value
  mode.value = 'view'
}

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

:root[data-theme="dark"] .memory-panel {
  background: var(--bg-secondary, #111827);
}
</style>
