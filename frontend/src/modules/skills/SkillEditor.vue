<template>
  <div class="skill-editor">
    <!-- 编辑器头部 -->
    <div class="editor-header">
      <h3 class="editor-title">
        {{ isNewSkill ? $t('skills.createSkill') : $t('skills.editSkill') }}
      </h3>
      <button
        class="close-btn"
        @click="handleClose"
      >
        <component
          :is="XIcon"
          :size="20"
        />
      </button>
    </div>

    <!-- 编辑器主体 -->
    <div class="editor-body">
      <!-- 技能名称 -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('skills.skillName') }}
          <span class="required">*</span>
        </label>
        <Input
          v-model="formData.name"
          :placeholder="$t('skills.skillNamePlaceholder')"
          :disabled="!isNewSkill"
        />
        <span
          v-if="!isNewSkill"
          class="form-hint"
        >
          {{ $t('skills.skillNameHint') }}
        </span>
      </div>

      <!-- 技能描述 -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('skills.skillDescription') }}
        </label>
        <Input
          v-model="formData.description"
          :placeholder="$t('skills.skillDescriptionPlaceholder')"
        />
      </div>

      <!-- 编辑器选项卡 -->
      <div class="editor-tabs">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'edit' }"
          @click="activeTab = 'edit'"
        >
          <component
            :is="EditIcon"
            :size="16"
          />
          {{ $t('memory.editor') }}
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'preview' }"
          @click="activeTab = 'preview'"
        >
          <component
            :is="EyeIcon"
            :size="16"
          />
          {{ $t('memory.preview') }}
        </button>
      </div>

      <!-- 编辑器内容 -->
      <div class="editor-content">
        <!-- 编辑模式 -->
        <div
          v-show="activeTab === 'edit'"
          class="edit-panel"
        >
          <textarea
            v-model="formData.content"
            class="content-textarea"
            :placeholder="$t('skills.contentPlaceholder')"
          />
          <div class="editor-stats">
            <span>{{ contentStats.lines }} {{ $t('memory.lines') }}</span>
            <span>{{ contentStats.characters }} {{ $t('memory.characters') }}</span>
          </div>
        </div>

        <!-- 预览模式 -->
        <div
          v-show="activeTab === 'preview'"
          class="preview-panel"
        >
          <div
            v-if="formData.content"
            class="preview-content"
            v-html="renderedContent"
          />
          <div
            v-else
            class="preview-empty"
          >
            {{ $t('memory.emptyPreview') }}
          </div>
        </div>
      </div>

      <!-- 高级选项 -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('skills.advancedOptions') }}
        </label>
        <div class="checkbox-group">
          <label class="checkbox-label">
            <input
              v-model="formData.autoLoad"
              type="checkbox"
            >
            <span>{{ $t('skills.autoLoad') }}</span>
            <span class="checkbox-hint">{{ $t('skills.autoLoadHint') }}</span>
          </label>
        </div>
      </div>

      <!-- 依赖要求 -->
      <div class="form-group">
        <label class="form-label">
          {{ $t('skills.requirements') }}
        </label>
        <div class="requirements-input">
          <Input
            v-model="requirementInput"
            :placeholder="$t('skills.requirementsPlaceholder')"
            @keydown.enter="handleAddRequirement"
          />
          <button
            class="add-btn"
            @click="handleAddRequirement"
          >
            <component
              :is="PlusIcon"
              :size="16"
            />
            {{ $t('common.add') }}
          </button>
        </div>
        <div
          v-if="formData.requirements.length > 0"
          class="requirements-tags"
        >
          <span
            v-for="(req, index) in formData.requirements"
            :key="index"
            class="requirement-tag"
          >
            {{ req }}
            <button
              class="remove-btn"
              @click="handleRemoveRequirement(index)"
            >
              <component
                :is="XIcon"
                :size="12"
              />
            </button>
          </span>
        </div>
      </div>
    </div>

    <!-- 编辑器底部 -->
    <div class="editor-footer">
      <button
        class="cancel-btn"
        @click="handleClose"
      >
        {{ $t('common.cancel') }}
      </button>
      <button
        class="save-btn"
        :disabled="!canSave || saving"
        @click="handleSave"
      >
        <component
          :is="LoaderIcon"
          v-if="saving"
          :size="16"
          class="spin"
        />
        {{ saving ? $t('common.saving') : $t('common.save') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  X as XIcon,
  Edit as EditIcon,
  Eye as EyeIcon,
  Plus as PlusIcon,
  Loader2 as LoaderIcon
} from 'lucide-vue-next'
import { useMarkdown } from '@/composables/useMarkdown'
import Input from '@/components/ui/Input.vue'
import type { SkillDetail } from '@/store/skills'

interface Props {
  skill?: SkillDetail
}

interface Emits {
  (e: 'close'): void
  (e: 'save', data: SkillFormData): void
}

interface SkillFormData {
  name: string
  description: string
  content: string
  autoLoad: boolean
  requirements: string[]
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()
const { renderMarkdown } = useMarkdown()

// 状态
const activeTab = ref<'edit' | 'preview'>('edit')
const saving = ref(false)
const requirementInput = ref('')

const formData = ref<SkillFormData>({
  name: '',
  description: '',
  content: '',
  autoLoad: false,
  requirements: []
})

// 计算属性
const isNewSkill = computed(() => !props.skill)

const canSave = computed(() => formData.value.name.trim() !== '' && formData.value.content.trim() !== '')

const contentStats = computed(() => {
  const content = formData.value.content
  return {
    characters: content.length,
    lines: content.split('\n').length
  }
})

const renderedContent = computed(() => {
  if (!formData.value.content) return ''
  return renderMarkdown(formData.value.content)
})

// 监听 props 变化
watch(
  () => props.skill,
  (skill) => {
    if (skill) {
      formData.value = {
        name: skill.name,
        description: skill.description,
        content: skill.content,
        autoLoad: skill.autoLoad,
        requirements: [...skill.requirements]
      }
    }
  },
  { immediate: true }
)

// 方法
const handleAddRequirement = () => {
  const req = requirementInput.value.trim()
  if (req && !formData.value.requirements.includes(req)) {
    formData.value.requirements.push(req)
    requirementInput.value = ''
  }
}

const handleRemoveRequirement = (index: number) => {
  formData.value.requirements.splice(index, 1)
}

const handleClose = () => {
  if (hasUnsavedChanges()) {
    if (confirm(t('memory.unsavedChanges'))) {
      emit('close')
    }
  } else {
    emit('close')
  }
}

const handleSave = async () => {
  if (!canSave.value || saving.value) return

  saving.value = true
  try {
    emit('save', { ...formData.value })
  } finally {
    saving.value = false
  }
}

const hasUnsavedChanges = (): boolean => {
  if (!props.skill) {
    return formData.value.content.trim() !== '' || formData.value.name.trim() !== ''
  }
  
  return (
    formData.value.name !== props.skill.name ||
    formData.value.description !== props.skill.description ||
    formData.value.content !== props.skill.content ||
    formData.value.autoLoad !== props.skill.autoLoad ||
    JSON.stringify(formData.value.requirements) !== JSON.stringify(props.skill.requirements)
  )
}
</script>

<style scoped>
.skill-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

/* 头部 */
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-xl);
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.editor-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.close-btn:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

/* 主体 */
.editor-body {
  flex: 1;
  padding: var(--spacing-xl);
  overflow-y: auto;
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.required {
  color: var(--color-error);
}

.form-hint {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-xs);
}

/* 选项卡 */
.editor-tabs {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-color);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-base);
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

/* 编辑器内容 */
.editor-content {
  min-height: 400px;
  margin-bottom: var(--spacing-lg);
}

.edit-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.content-textarea {
  width: 100%;
  min-height: 400px;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  resize: vertical;
  transition: all var(--transition-base);
}

.content-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.editor-stats {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.preview-panel {
  min-height: 400px;
  padding: var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
}

.preview-content {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-primary);
}

.preview-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

/* 复选框 */
.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  margin-top: 2px;
  cursor: pointer;
}

.checkbox-hint {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin-left: var(--spacing-lg);
}

/* 依赖要求 */
.requirements-input {
  display: flex;
  gap: var(--spacing-sm);
}

.add-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
  cursor: pointer;
  transition: all var(--transition-base);
}

.add-btn:hover {
  background: var(--hover-bg);
  border-color: var(--color-primary);
}

.requirements-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
}

.requirement-tag {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color var(--transition-base);
}

.remove-btn:hover {
  color: var(--color-error);
}

/* 底部 */
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
  background: var(--color-primary-dark);
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 动画 */
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
</style>
