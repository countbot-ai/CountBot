<template>
  <Modal
    :model-value="modelValue"
    :title="title"
    size="large"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="config-help">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <LoaderIcon :size="32" class="spin" />
        <p>加载中...</p>
      </div>

      <!-- 帮助内容 -->
      <div v-else-if="helpContent" class="help-content">
        <div class="help-section">
          <h3>配置说明</h3>
          <p class="help-description">{{ helpContent.description }}</p>
          
          <div v-if="helpContent.help_text" class="help-text">
            <pre>{{ helpContent.help_text }}</pre>
          </div>
          
          <h3>字段说明</h3>
          <div class="fields-help">
            <div v-for="field in helpContent.fields" :key="field.key" class="field-help-item">
              <div class="field-header">
                <span class="field-label">{{ field.label }}</span>
                <span v-if="field.required" class="required-badge">必填</span>
                <span v-if="field.sensitive" class="sensitive-badge">敏感</span>
              </div>
              <p class="field-description">{{ field.description }}</p>
              <p v-if="field.help_text" class="field-help-text">💡 {{ field.help_text }}</p>
              <div v-if="field.default !== undefined" class="field-default">
                默认值: <code>{{ field.default }}</code>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 无帮助文档 -->
      <div v-else class="no-help">
        <InfoIcon :size="48" />
        <p>暂无配置帮助文档</p>
      </div>
    </div>

    <template #footer>
      <button class="btn-secondary" @click="$emit('update:modelValue', false)">
        关闭
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loader2 as LoaderIcon, Info as InfoIcon } from 'lucide-vue-next'
import Modal from '@/components/ui/Modal.vue'
import { skillsAPI } from '@/api/endpoints'

interface Props {
  modelValue: boolean
  skillName: string
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '配置帮助'
})

defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const loading = ref(false)
const helpContent = ref<any>(null)

const loadHelpDoc = async () => {
  if (!props.modelValue || !props.skillName) return
  
  loading.value = true
  try {
    // 直接从Schema获取帮助信息
    const response = await skillsAPI.getConfigSchema(props.skillName)
    if (response.has_schema && response.schema) {
      helpContent.value = response.schema
    } else {
      helpContent.value = null
    }
  } catch (error) {
    console.error('Failed to load help:', error)
    helpContent.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    loadHelpDoc()
  }
})
</script>

<style scoped>
.config-help {
  min-height: 400px;
}

.loading-state,
.no-help {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-3xl);
  color: var(--text-secondary);
}

.help-content {
  padding: var(--spacing-lg);
  max-height: 600px;
  overflow-y: auto;
}

.help-section h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: var(--spacing-lg) 0 var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 2px solid var(--border-color);
}

.help-section h3:first-child {
  margin-top: 0;
}

.help-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: var(--spacing-md);
}

.help-text {
  padding: var(--spacing-md);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-primary);
  margin-bottom: var(--spacing-lg);
}

.help-text pre {
  margin: 0;
  font-family: inherit;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.fields-help {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.field-help-item {
  padding: var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.field-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
}

.field-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.required-badge,
.sensitive-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.required-badge {
  background: var(--color-error-light, #fee2e2);
  color: var(--color-error, #ef4444);
  border: 1px solid var(--color-error, #ef4444);
}

.sensitive-badge {
  background: var(--color-warning-light, #fef3c7);
  color: var(--color-warning, #f59e0b);
  border: 1px solid var(--color-warning, #f59e0b);
}

.field-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0;
  line-height: 1.5;
}

.field-help-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  margin: var(--spacing-xs) 0;
  line-height: 1.5;
  font-style: italic;
}

.field-default {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin-top: var(--spacing-xs);
}

.field-default code {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.9em;
  color: var(--text-primary);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 深色模式 */
:root[data-theme="dark"] .help-text {
  background: #131b2c;
  border-color: rgba(0, 240, 255, 0.3);
}

:root[data-theme="dark"] .field-help-item {
  background: #0e1422;
  border-color: #152035;
}

:root[data-theme="dark"] .field-default code {
  background: #131b2c;
}

:root[data-theme="dark"] .required-badge {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
}

:root[data-theme="dark"] .sensitive-badge {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
}
</style>
