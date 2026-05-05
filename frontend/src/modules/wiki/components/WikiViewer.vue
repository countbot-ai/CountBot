<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <div class="modal-header">
          <h3>{{ entry?.title || '查看条目' }}</h3>
          <button class="close-btn" @click="$emit('close')">
            <XIcon :size="20" />
          </button>
        </div>
        <div class="modal-body" v-if="entry">
          <div class="entry-meta">
            <div class="tags" v-if="entry.tags?.length">
              <span v-for="tag in entry.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <span class="slug">{{ entry.slug }}</span>
          </div>
          <div class="entry-content" v-html="renderedContent"></div>

          <!-- 反向链接部分 -->
          <div v-if="backlinks !== null" class="backlinks-section">
            <h4 class="backlinks-title">
              <LinkIcon :size="16" />
              反向链接 ({{ backlinks.length }})
            </h4>
            <div v-if="backlinks.length > 0" class="backlinks-list">
              <div
                v-for="link in backlinks"
                :key="link.slug"
                class="backlink-item"
                @click="handleBacklinkClick(link.slug)"
              >
                <span class="backlink-title">{{ link.title }}</span>
                <span class="backlink-summary" v-if="link.summary">{{ link.summary }}</span>
              </div>
            </div>
            <p v-else class="no-backlinks">暂无其他条目链接到此条目</p>
          </div>
          <div v-else-if="loadingBacklinks" class="backlinks-loading">
            <LoaderIcon :size="16" class="spin" />
            加载反向链接...
          </div>
        </div>
        <div class="modal-footer">
          <button class="edit-btn" @click="$emit('edit', entry)">
            <EditIcon :size="16" />
            编辑
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { X as XIcon, Edit as EditIcon, Link as LinkIcon, Loader2 as LoaderIcon } from 'lucide-vue-next'
import { wikiApi } from '../services/wikiApi'

const props = defineProps<{
  modelValue: boolean
  entry: any
}>()

const emit = defineEmits(['update:modelValue', 'edit', 'close'])

const backlinks = ref<any[] | null>(null)
const loadingBacklinks = ref(false)

const renderedContent = computed(() => {
  if (!props.entry?.content) return ''
  // 简单的 Markdown 渲染
  return props.entry.content
    .replace(/# (.*)/g, '<h1>$1</h1>')
    .replace(/## (.*)/g, '<h2>$1</h2>')
    .replace(/### (.*)/g, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\[\[(.*?)\]\]/g, '<span class="wiki-link">$1</span>')
    .replace(/\n/g, '<br>')
})

// 加载反向链接
watch(() => props.entry, async (entry) => {
  if (entry && entry.slug) {
    backlinks.value = null
    loadingBacklinks.value = true
    try {
      const data = await wikiApi.getBacklinks(entry.slug)
      backlinks.value = data.backlinks
    } catch (err) {
      console.error('Failed to load backlinks:', err)
      backlinks.value = []
    } finally {
      loadingBacklinks.value = false
    }
  }
}, { immediate: true })

const handleBacklinkClick = (slug: string) => {
  // 可以在这里实现跳转到其他条目的逻辑
  console.log('Navigate to:', slug)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--spacing-lg);
}

.modal-container {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 800px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.close-btn {
  padding: var(--spacing-sm);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
}

.close-btn:hover {
  background: var(--bg-secondary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

.entry-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.tags {
  display: flex;
  gap: var(--spacing-xs);
}

.tag {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  font-size: var(--font-size-xs);
}

.slug {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.entry-content {
  line-height: 1.7;
  color: var(--text-primary);
}

.entry-content :deep(h1) {
  font-size: var(--font-size-xl);
  margin-bottom: var(--spacing-md);
}

.entry-content :deep(h2) {
  font-size: var(--font-size-lg);
  margin-top: var(--spacing-lg);
  margin-bottom: var(--spacing-sm);
}

.entry-content :deep(h3) {
  font-size: var(--font-size-base);
  margin-top: var(--spacing-md);
  margin-bottom: var(--spacing-sm);
}

.entry-content :deep(code) {
  padding: 2px 6px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-family: monospace;
}

.entry-content :deep(.wiki-link) {
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
  text-decoration: underline;
  cursor: pointer;
}

/* 反向链接样式 */
.backlinks-section {
  margin-top: var(--spacing-xl);
  padding-top: var(--spacing-lg);
  border-top: 2px solid var(--border-color);
}

.backlinks-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin: 0 0 var(--spacing-md) 0;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.backlinks-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.backlink-item {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.backlink-item:hover {
  border-color: var(--color-primary);
  background: var(--bg-primary);
  transform: translateX(4px);
}

.backlink-title {
  display: block;
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: 2px;
}

.backlink-summary {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.no-backlinks {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
  font-style: italic;
}

.backlinks-loading {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: var(--spacing-lg);
  border-top: 1px solid var(--border-color);
}

.edit-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: white;
  cursor: pointer;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 1s linear infinite;
}
</style>
