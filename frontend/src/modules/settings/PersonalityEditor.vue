<template>
  <div class="personality-editor">
    <div class="editor-header">
      <h3>{{ $t('settings.persona.personalityEditor') }}</h3>
      <button class="create-btn" @click="showCreateDialog">
        <component :is="PlusIcon" :size="16" />
        {{ $t('settings.persona.createPersonality') }}
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- 性格列表 -->
    <div v-else class="personality-list">
      <!-- 内置性格 -->
      <div v-if="builtinPersonalities.length > 0" class="personality-section">
        <h4 class="section-title">{{ $t('settings.persona.builtinPersonalities') }}</h4>
        <div class="personality-grid">
          <div
            v-for="p in builtinPersonalities"
            :key="p.id"
            class="personality-card"
            :class="{ inactive: !p.is_active }"
          >
            <div class="card-header">
              <component :is="getIcon(p.icon)" :size="20" class="personality-icon" />
              <h5>{{ p.name }}</h5>
              <span class="builtin-badge">{{ $t('settings.persona.builtin') }}</span>
            </div>
            <p class="personality-desc">{{ p.description }}</p>
            <div class="personality-traits">
              <span v-for="trait in p.traits" :key="trait" class="trait-tag">{{ trait }}</span>
            </div>
            <div class="card-actions">
              <button @click="editPersonality(p)" class="action-btn primary">
                <component :is="EditIcon" :size="14" />
                {{ $t('common.edit') }}
              </button>
              <button @click="toggleActive(p)" class="action-btn">
                <component :is="p.is_active ? EyeOffIcon : EyeIcon" :size="14" />
                {{ p.is_active ? $t('common.disable') : $t('common.enable') }}
              </button>
              <button @click="duplicatePersonality(p)" class="action-btn">
                <component :is="CopyIcon" :size="14" />
                {{ $t('settings.persona.duplicate') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 自定义性格 -->
      <div v-if="customPersonalities.length > 0" class="personality-section">
        <h4 class="section-title">{{ $t('settings.persona.customPersonalities') }}</h4>
        <div class="personality-grid">
          <div
            v-for="p in customPersonalities"
            :key="p.id"
            class="personality-card"
            :class="{ inactive: !p.is_active }"
          >
            <div class="card-header">
              <component :is="getIcon(p.icon)" :size="20" class="personality-icon" />
              <h5>{{ p.name }}</h5>
            </div>
            <p class="personality-desc">{{ p.description }}</p>
            <div class="personality-traits">
              <span v-for="trait in p.traits" :key="trait" class="trait-tag">{{ trait }}</span>
            </div>
            <div class="card-actions">
              <button @click="editPersonality(p)" class="action-btn primary">
                <component :is="EditIcon" :size="14" />
                {{ $t('common.edit') }}
              </button>
              <button @click="toggleActive(p)" class="action-btn">
                <component :is="p.is_active ? EyeOffIcon : EyeIcon" :size="14" />
                {{ p.is_active ? $t('common.disable') : $t('common.enable') }}
              </button>
              <button @click="deletePersonality(p)" class="action-btn danger">
                <component :is="TrashIcon" :size="14" />
                {{ $t('common.delete') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="customPersonalities.length === 0" class="empty-state">
        <component :is="SparklesIcon" :size="48" />
        <p>{{ $t('settings.persona.noCustomPersonalities') }}</p>
        <button class="create-btn-large" @click="showCreateDialog">
          <component :is="PlusIcon" :size="20" />
          {{ $t('settings.persona.createFirstPersonality') }}
        </button>
      </div>
    </div>

    <!-- 编辑/创建对话框 -->
    <PersonalityEditDialog
      v-if="editingPersonality"
      :personality="editingPersonality"
      :is-new="isCreating"
      @save="savePersonality"
      @cancel="closeDialog"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Plus as PlusIcon,
  Edit as EditIcon,
  Copy as CopyIcon,
  Trash as TrashIcon,
  Eye as EyeIcon,
  EyeOff as EyeOffIcon,
  Sparkles as SparklesIcon,
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
} from 'lucide-vue-next'
import { personalitiesApi, type Personality } from '@/api/personalities'
import { useToast } from '@/composables/useToast'
import PersonalityEditDialog from './PersonalityEditDialog.vue'

const { t } = useI18n()
const toast = useToast()

const personalities = ref<Personality[]>([])
const loading = ref(false)
const editingPersonality = ref<Personality | null>(null)
const isCreating = ref(false)

// 图标映射
const iconMap: Record<string, any> = {
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
}

const getIcon = (iconName: string) => {
  return iconMap[iconName] || Smile
}

// 分类性格
const builtinPersonalities = computed(() =>
  personalities.value.filter(p => p.is_builtin)
)

const customPersonalities = computed(() =>
  personalities.value.filter(p => !p.is_builtin)
)

// 加载性格列表
const loadPersonalities = async () => {
  loading.value = true
  try {
    const { personalities: data } = await personalitiesApi.list(false)
    personalities.value = data
  } catch (error) {
    console.error('Failed to load personalities:', error)
    toast.error(t('settings.persona.loadFailed'))
  } finally {
    loading.value = false
  }
}

// 显示创建对话框
const showCreateDialog = () => {
  editingPersonality.value = {
    id: '',
    name: '',
    description: '',
    traits: [],
    speaking_style: '',
    icon: 'Smile',
    is_builtin: false,
    is_active: true,
    created_at: '',
    updated_at: '',
  }
  isCreating.value = true
}

// 编辑性格（内置和自定义都可以编辑）
const editPersonality = (personality: Personality) => {
  editingPersonality.value = { ...personality }
  isCreating.value = false
}

// 复制性格
const duplicatePersonality = async (personality: Personality) => {
  const newId = prompt(t('settings.persona.enterNewId'), `${personality.id}_copy`)
  if (!newId) return

  try {
    await personalitiesApi.duplicate(personality.id, newId, `${personality.name} (副本)`)
    toast.success(t('settings.persona.duplicateSuccess'))
    await loadPersonalities()
  } catch (error: any) {
    console.error('Failed to duplicate personality:', error)
    toast.error(error.message || t('settings.persona.duplicateFailed'))
  }
}

// 切换启用状态
const toggleActive = async (personality: Personality) => {
  try {
    await personalitiesApi.update(personality.id, {
      is_active: !personality.is_active,
    })
    toast.success(t('settings.persona.updateSuccess'))
    await loadPersonalities()
  } catch (error: any) {
    console.error('Failed to toggle personality:', error)
    toast.error(error.message || t('settings.persona.updateFailed'))
  }
}

// 删除性格
const deletePersonality = async (personality: Personality) => {
  if (!confirm(t('settings.persona.confirmDelete', { name: personality.name }))) {
    return
  }

  try {
    await personalitiesApi.delete(personality.id)
    toast.success(t('settings.persona.deleteSuccess'))
    await loadPersonalities()
  } catch (error: any) {
    console.error('Failed to delete personality:', error)
    toast.error(error.message || t('settings.persona.deleteFailed'))
  }
}

// 保存性格
const savePersonality = async (personality: Personality) => {
  try {
    if (isCreating.value) {
      await personalitiesApi.create({
        id: personality.id,
        name: personality.name,
        description: personality.description,
        traits: personality.traits,
        speaking_style: personality.speaking_style,
        icon: personality.icon,
      })
      toast.success(t('settings.persona.createSuccess'))
    } else {
      await personalitiesApi.update(personality.id, {
        name: personality.name,
        description: personality.description,
        traits: personality.traits,
        speaking_style: personality.speaking_style,
        icon: personality.icon,
      })
      toast.success(t('settings.persona.updateSuccess'))
    }
    await loadPersonalities()
    closeDialog()
  } catch (error: any) {
    console.error('Failed to save personality:', error)
    toast.error(error.message || t('settings.persona.saveFailed'))
  }
}

// 关闭对话框
const closeDialog = () => {
  editingPersonality.value = null
  isCreating.value = false
}

onMounted(() => {
  loadPersonalities()
})
</script>

<style scoped>
.personality-editor {
  width: 100%;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.editor-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: var(--primary-color);
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.create-btn:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.personality-section {
  margin-bottom: 32px;
}

.section-title {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.personality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.personality-card {
  padding: 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  transition: all 0.2s;
}

.personality-card:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.personality-card.inactive {
  opacity: 0.6;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.personality-icon {
  color: var(--primary-color);
}

.card-header h5 {
  flex: 1;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.builtin-badge {
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.personality-desc {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.personality-traits {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}

.trait-tag {
  padding: 4px 8px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: var(--primary-color);
}

.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 14px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  opacity: 1;
}

.action-btn:hover {
  border-color: var(--primary-color);
  background: var(--bg-hover);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.action-btn.primary {
  background: #9598a0ff !important;
  color: #ffffff !important;
  border-color: #8994a4ff !important;
  font-weight: 600;
}

.action-btn.primary:hover {
  background: #44516dff !important;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}

.action-btn.danger {
  color: #ef4444;
  border-color: #ef4444;
}

.action-btn.danger:hover {
  background: rgba(239, 68, 68, 0.1);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.empty-state p {
  margin: 16px 0 24px 0;
  font-size: 14px;
}

.create-btn-large {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  background: var(--primary-color);
  color: white;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.create-btn-large:hover {
  background: var(--primary-hover);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

@media (max-width: 768px) {
  .personality-grid {
    grid-template-columns: 1fr;
  }
}
</style>
