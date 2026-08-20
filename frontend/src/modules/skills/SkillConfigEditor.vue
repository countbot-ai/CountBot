<template>
  <div class="skill-config-editor">
    <div class="editor-header">
      <h3>{{ skillName }} - 配置编辑</h3>
      <div class="header-actions">
        <button
          v-if="schema"
          class="help-btn"
          @click="showHelp = true"
          title="查看配置帮助"
        >
          <HelpCircleIcon :size="20" />
        </button>
        <button class="close-btn" @click="handleClose">
          <XIcon :size="20" />
        </button>
      </div>
    </div>

    <div class="editor-body">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <LoaderIcon :size="32" class="spin" />
        <p>加载配置中...</p>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="error" class="error-state">
        <AlertCircleIcon :size="32" />
        <p>{{ error }}</p>
        <button class="retry-btn" @click="loadConfig">
          重试
        </button>
      </div>

      <!-- 无Schema -->
      <div v-else-if="!schema" class="no-schema-state">
        <InfoIcon :size="48" />
        <h4>不支持可视化编辑</h4>
        <p>该技能没有配置Schema定义，请手动编辑配置文件</p>
      </div>

      <!-- 未配置 -->
      <div v-else-if="configStatus === 'not_configured'" class="warning-state">
        <AlertTriangleIcon :size="48" />
        <h4>配置文件不存在</h4>
        <p>该技能的配置文件不存在，请检查技能目录</p>
      </div>

      <!-- 格式错误 -->
      <div v-else-if="configStatus === 'invalid_format'" class="error-state">
        <XCircleIcon :size="48" />
        <h4>配置文件格式错误</h4>
        <p>配置文件无法解析，请检查JSON格式</p>
      </div>

      <!-- 字段缺失 -->
      <div v-else-if="configStatus === 'missing_fields'" class="warning-state">
        <AlertTriangleIcon :size="48" />
        <h4>配置不完整</h4>
        <p>配置文件缺少必填字段：</p>
        <ul class="error-list">
          <li v-for="err in configErrors" :key="err">{{ err }}</li>
        </ul>
        <button class="fix-btn" @click="handleFix" :disabled="fixing">
          <LoaderIcon v-if="fixing" :size="16" class="spin" />
          自动修复
        </button>
      </div>

      <!-- 配置表单 -->
      <div v-else-if="configValues" class="config-form-container">
        <ConfigForm
          :fields="schema.fields"
          :values="configValues"
          @update="handleUpdate"
        />

        <!-- 安全提示 -->
        <div class="security-notice">
          <ShieldIcon :size="16" />
          <span>敏感信息将被安全存储，文件权限设置为仅所有者可读写</span>
        </div>
      </div>
    </div>

    <div v-if="configValues" class="editor-footer">
      <button class="cancel-btn" @click="handleClose">
        取消
      </button>
      <button 
        class="save-btn" 
        :disabled="!hasChanges || saving"
        @click="handleSave"
      >
        <LoaderIcon v-if="saving" :size="16" class="spin" />
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </div>

    <!-- 帮助模态框 -->
    <ConfigHelpModal
      v-model="showHelp"
      :skill-name="skillName"
      :title="`${skillName} 配置帮助`"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  X as XIcon,
  Loader2 as LoaderIcon,
  AlertCircle as AlertCircleIcon,
  AlertTriangle as AlertTriangleIcon,
  XCircle as XCircleIcon,
  Info as InfoIcon,
  HelpCircle as HelpCircleIcon,
  Shield as ShieldIcon
} from 'lucide-vue-next'
import ConfigForm from './components/ConfigForm.vue'
import ConfigHelpModal from './components/ConfigHelpModal.vue'
import { skillsAPI } from '@/api/endpoints'
import type { ConfigFieldSchema } from '@/api/endpoints'

interface Props {
  skillName: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const loading = ref(true)
const saving = ref(false)
const fixing = ref(false)
const error = ref('')
const showHelp = ref(false)

const schema = ref<{ fields: ConfigFieldSchema[] } | null>(null)
const configValues = ref<Record<string, any> | null>(null)
const originalValues = ref<Record<string, any> | null>(null)
const configStatus = ref('')
const configErrors = ref<string[]>([])

const hasChanges = computed(() => {
  return JSON.stringify(configValues.value) !== JSON.stringify(originalValues.value)
})

const loadConfig = async () => {
  loading.value = true
  error.value = ''
  
  try {
    // 加载Schema
    const schemaResponse = await skillsAPI.getConfigSchema(props.skillName)
    if (!schemaResponse.has_schema) {
      schema.value = null
      loading.value = false
      return
    }
    schema.value = schemaResponse.schema || null

    // 加载配置
    const configResponse = await skillsAPI.getConfig(props.skillName)
    configStatus.value = configResponse.status
    configErrors.value = configResponse.errors

    if (configResponse.has_config && configResponse.config) {
      configValues.value = { ...configResponse.config }
      originalValues.value = { ...configResponse.config }
    }
  } catch (err: any) {
    error.value = err.message || '加载配置失败'
  } finally {
    loading.value = false
  }
}

const handleUpdate = (key: string, value: any) => {
  if (configValues.value) {
    configValues.value[key] = value
  }
}

const handleSave = async () => {
  if (!hasChanges.value || saving.value || !configValues.value) return
  
  saving.value = true
  try {
    await skillsAPI.updateConfig(props.skillName, {
      config: configValues.value
    })
    
    originalValues.value = { ...configValues.value }
    
    // 显示成功提示
    alert('配置已保存')
    
    emit('saved')
  } catch (err: any) {
    alert(`保存失败: ${err.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

const handleFix = async () => {
  fixing.value = true
  try {
    await skillsAPI.fixConfig(props.skillName)
    alert('配置已自动修复')
    await loadConfig()
  } catch (err: any) {
    alert(`修复失败: ${err.message || '未知错误'}`)
  } finally {
    fixing.value = false
  }
}

const handleClose = () => {
  if (hasChanges.value) {
    if (confirm('有未保存的更改，确定要关闭吗？')) {
      emit('close')
    }
  } else {
    emit('close')
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.skill-config-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.editor-header h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.help-btn,
.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  cursor: pointer;
  transition: all var(--transition-base);
}

.help-btn {
  color: var(--color-primary);
}

.help-btn:hover {
  background: var(--color-primary-light, #eff6ff);
}

.close-btn {
  color: var(--text-secondary);
}

.close-btn:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.editor-body {
  flex: 1;
  padding: var(--spacing-xl);
  overflow-y: auto;
}

.loading-state,
.error-state,
.warning-state,
.no-schema-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-3xl);
  text-align: center;
}

.loading-state {
  color: var(--text-secondary);
}

.error-state {
  color: var(--color-error);
}

.warning-state {
  color: var(--color-warning);
}

.no-schema-state {
  color: var(--text-secondary);
}

.error-state h4,
.warning-state h4,
.no-schema-state h4 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  margin: 0;
}

.error-state p,
.warning-state p,
.no-schema-state p {
  font-size: var(--font-size-sm);
  margin: 0;
}

.error-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-md) 0;
  text-align: left;
}

.error-list li {
  padding: var(--spacing-xs);
  font-size: var(--font-size-sm);
}

.retry-btn,
.fix-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-base);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.retry-btn:hover,
.fix-btn:hover:not(:disabled) {
  background: var(--hover-bg);
}

.fix-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.config-form-container {
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
}

.security-notice {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  margin-top: var(--spacing-xl);
  border-radius: var(--radius-md);
  background: var(--color-primary-light, #eff6ff);
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  font-size: var(--font-size-xs);
}

.editor-footer {
  display: flex;
  gap: var(--spacing-sm);
  justify-content: flex-end;
  padding: var(--spacing-md) var(--spacing-xl);
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.cancel-btn,
.save-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.cancel-btn {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.cancel-btn:hover {
  background: var(--hover-bg);
}

.save-btn {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.save-btn:hover:not(:disabled) {
  background: var(--color-primary-dark, #2563eb);
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
:root[data-theme="dark"] .editor-header {
  background: var(--bg-primary, #0a0e1a);
  border-color: #152035;
}

:root[data-theme="dark"] .help-btn:hover {
  background: rgba(0, 240, 255, 0.1);
}

:root[data-theme="dark"] .security-notice {
  background: rgba(0, 240, 255, 0.08);
  border-color: rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}

:root[data-theme="dark"] .editor-footer {
  background: var(--bg-primary, #0a0e1a);
  border-color: #152035;
}
</style>
