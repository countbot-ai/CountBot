<template>
  <div class="preset-selector">
    <div class="preset-header">
      <div class="preset-select-group">
        <label class="preset-label">{{ $t('settings.presets.selectPreset') }}</label>
        <div class="preset-select-wrapper">
          <select
            v-model="selectedPresetId"
            class="preset-select"
            @change="handlePresetChange"
          >
            <option value="">{{ $t('settings.presets.noPresetSelected') }}</option>
            <option
              v-for="option in presetOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
          <ChevronDownIcon class="preset-select-icon" :size="16" />
        </div>
      </div>
      
      <div class="preset-actions">
        <button
          v-if="currentSelectedPreset"
          class="preset-action-btn preset-clear-btn"
          @click="handleClearSelection"
          :title="$t('settings.presets.clearSelection')"
        >
          <XIcon :size="16" />
        </button>

        <button
          v-if="currentSelectedPreset"
          class="preset-action-btn delete-btn"
          @click="handleDeletePreset"
          :title="$t('settings.presets.deletePreset')"
        >
          <Trash2Icon :size="16" />
        </button>
        
        <input
          ref="fileInputRef"
          type="file"
          accept=".json"
          style="display: none"
          @change="handleFileImport"
        />
        <button
          class="preset-action-btn import-btn"
          @click="fileInputRef?.click()"
          :title="$t('settings.presets.importPresets')"
        >
          <UploadIcon :size="16" />
        </button>
        
        <button
          v-if="presets.length > 0"
          class="preset-action-btn export-btn"
          @click="handleExport"
          :title="$t('settings.presets.exportPresets')"
        >
          <DownloadIcon :size="16" />
        </button>
      </div>
    </div>

    <!-- 预设详情 -->
    <div v-if="currentSelectedPreset" class="preset-details">
      <div class="preset-info">
        <div class="preset-tags">
          <span class="preset-provider">{{ currentSelectedPreset.provider }}</span>
          <span class="preset-model">{{ currentSelectedPreset.model }}</span>
        </div>
        <p v-if="currentSelectedPreset.description" class="preset-description">
          {{ currentSelectedPreset.description }}
        </p>
      </div>
      <div class="preset-meta">
        <span class="preset-date">
          {{ $t('settings.presets.updatedAt') }}: {{ formatDate(currentSelectedPreset.updatedAt) }}
        </span>
      </div>
    </div>

    <!-- 导入结果提示 -->
    <div v-if="importResult" class="import-result" :class="importResult.success ? 'success' : 'error'">
      {{ importResult.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronDown as ChevronDownIcon,
  X as XIcon,
  Upload as UploadIcon,
  Download as DownloadIcon,
  Trash2 as Trash2Icon
} from 'lucide-vue-next'
import { usePresets } from '@/composables/usePresets'

interface Props {
  modelValue?: string
}

interface Emits {
  (e: 'update:modelValue', value: string | undefined): void
  (e: 'presetSelected', preset: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t } = useI18n()

const {
  presets,
  presetOptions,
  selectPreset,
  clearSelection,
  deletePreset,
  exportPresets,
  importPresets
} = usePresets()

// 本地状态
const fileInputRef = ref<HTMLInputElement>()
const importResult = ref<{ success: boolean; message: string } | null>(null)

// 计算属性
const selectedPresetId = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const currentSelectedPreset = computed(() =>
  presets.value.find(preset => preset.id === selectedPresetId.value)
)

// 方法
function handlePresetChange() {
  if (selectedPresetId.value) {
    selectPreset(selectedPresetId.value)
    emit('presetSelected', currentSelectedPreset.value)
  } else {
    handleClearSelection()
  }
}

function handleClearSelection() {
  clearSelection()
  emit('update:modelValue', undefined)
  emit('presetSelected', null)
}

function handleDeletePreset() {
  if (!currentSelectedPreset.value) {
    return
  }

  const presetToDelete = currentSelectedPreset.value
  const confirmed = window.confirm(
    t('settings.presets.deletePresetConfirm', { name: presetToDelete.name })
  )
  if (!confirmed) {
    return
  }

  deletePreset(presetToDelete.id)
  emit('update:modelValue', undefined)
  emit('presetSelected', null)
}

function handleExport() {
  const data = exportPresets()
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `provider-presets-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  
  // 显示导出成功提示
  alert('预设导出成功！')
}

function handleFileImport(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const content = e.target?.result as string
      const result = importPresets(content)
      importResult.value = result
      
      // 显示结果提示
      if (result.success) {
        alert(result.message)
      } else {
        alert('导入失败：' + result.message)
      }
      
      // 3秒后清除提示
      setTimeout(() => {
        importResult.value = null
      }, 3000)
    } catch (err) {
      const errorMsg = '文件读取失败：' + (err as Error).message
      importResult.value = { success: false, message: errorMsg }
      alert(errorMsg)
    }
  }
  
  reader.readAsText(file)
  
  // 清空文件输入，允许重复选择同一文件
  target.value = ''
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString()
}
</script>
<style scoped>
@import './styles/PresetSelector.css';
</style>
