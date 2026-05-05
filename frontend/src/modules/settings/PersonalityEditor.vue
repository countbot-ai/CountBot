<template>
  <div class="personality-editor">
    <div class="editor-header">
      <h3>{{ $t('settings.persona.personalityEditor') }}</h3>
      <Button
        variant="primary"
        size="md"
        :icon="PlusIcon"
        class="header-create-button"
        @click="showCreateDialog"
      >
        {{ $t('settings.persona.createPersonality') }}
      </Button>
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
              <Button
                variant="primary"
                size="sm"
                :icon="EditIcon"
                class="personality-action-button"
                @click="editPersonality(p)"
              >
                {{ $t('common.edit') }}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                :icon="p.is_active ? EyeOffIcon : EyeIcon"
                class="personality-action-button"
                @click="toggleActive(p)"
              >
                {{ p.is_active ? $t('common.disable') : $t('common.enable') }}
              </Button>
              <Button
                variant="outline"
                size="sm"
                :icon="CopyIcon"
                class="personality-action-button"
                @click="duplicatePersonality(p)"
              >
                {{ $t('settings.persona.duplicate') }}
              </Button>
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
              <Button
                variant="primary"
                size="sm"
                :icon="EditIcon"
                class="personality-action-button"
                @click="editPersonality(p)"
              >
                {{ $t('common.edit') }}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                :icon="p.is_active ? EyeOffIcon : EyeIcon"
                class="personality-action-button"
                @click="toggleActive(p)"
              >
                {{ p.is_active ? $t('common.disable') : $t('common.enable') }}
              </Button>
              <Button
                variant="danger"
                size="sm"
                :icon="TrashIcon"
                class="personality-action-button"
                @click="deletePersonality(p)"
              >
                {{ $t('common.delete') }}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="customPersonalities.length === 0" class="empty-state">
        <div class="empty-state-icon">
          <component :is="SparklesIcon" :size="30" />
        </div>
        <p>{{ $t('settings.persona.noCustomPersonalities') }}</p>
        <Button
          variant="primary"
          size="lg"
          :icon="PlusIcon"
          class="empty-state-create-button"
          @click="showCreateDialog"
        >
          {{ $t('settings.persona.createFirstPersonality') }}
        </Button>
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
import Button from '@/components/ui/Button.vue'
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
@import './styles/PersonalityEditor.css';
</style>
