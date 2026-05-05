<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('cancel')">
      <div class="modal-container">
        <div class="modal-header">
          <h3>{{ entry ? '编辑条目' : '新建条目' }}</h3>
          <button class="close-btn" @click="$emit('cancel')">
            <XIcon :size="20" />
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>标题</label>
            <input v-model="form.title" type="text" placeholder="输入标题">
          </div>
          <div class="form-group">
            <label>标签（用逗号分隔）</label>
            <input v-model="form.tags" type="text" placeholder="例如: Python, 教程, 后端">
          </div>
          <div class="form-group">
            <label>内容</label>
            <textarea v-model="form.content" rows="15" placeholder="支持 Markdown 格式"></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="cancel-btn" @click="$emit('cancel')">取消</button>
          <button class="save-btn" :disabled="!form.title || !form.content" @click="handleSave">
            {{ entry ? '更新' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { X as XIcon } from 'lucide-vue-next'

const props = defineProps<{
  modelValue: boolean
  entry: any
}>()

const emit = defineEmits(['update:modelValue', 'save', 'cancel'])

const form = ref({
  title: '',
  tags: '',
  content: ''
})

watch(() => props.entry, (entry) => {
  if (entry) {
    form.value = {
      title: entry.title || '',
      tags: entry.tags?.join(', ') || '',
      content: entry.content || ''
    }
  } else {
    form.value = { title: '', tags: '', content: '' }
  }
}, { immediate: true })

const handleSave = () => {
  const tags = form.value.tags
    .split(',')
    .map((t: string) => t.trim())
    .filter(Boolean)
  
  emit('save', {
    title: form.value.title,
    content: form.value.content,
    tags
  })
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
  max-width: 700px;
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

.form-group {
  margin-bottom: var(--spacing-md);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-xs);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-secondary);
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--font-size-base);
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-group textarea {
  resize: vertical;
  font-family: monospace;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-lg);
  border-top: 1px solid var(--border-color);
}

.cancel-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
}

.save-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: white;
  cursor: pointer;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
