<template>
  <div class="personality-editor">
    <div class="editor-header">
      <h3>{{ $t('settings.persona.personalityEditor') }}</h3>
      <div class="header-actions">
        <Button
          variant="primary"
          size="md"
          :icon="PlusIcon"
          class="header-create-button"
          @click="showCreateDialog"
        >
          {{ $t('settings.persona.addPersonality') }}
        </Button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>{{ $t('common.loading') }}</p>
    </div>

    <!-- 性格列表：内置与自建统一展示，末尾固定添加入口 -->
    <div v-else class="personality-list">
      <div class="personality-grid">
        <div
          v-for="p in personalities"
          :key="p.id"
          class="personality-card"
          :class="{ inactive: !p.is_active }"
        >
          <div class="card-header">
            <component :is="getIcon(p.icon)" :size="20" class="personality-icon" />
            <h5>{{ p.name }}</h5>
            <span v-if="p.is_builtin" class="builtin-badge">
              {{ $t('settings.persona.builtin') }}
            </span>
          </div>
          <p class="personality-desc">{{ p.description }}</p>
          <div class="personality-traits">
            <span v-for="trait in p.traits" :key="trait" class="trait-tag">{{ trait }}</span>
          </div>
          <div v-if="canManage(p)" class="card-actions">
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

        <button type="button" class="personality-add" @click="showCreateDialog">
          <component :is="PlusIcon" :size="20" class="personality-add-icon" />
          <span class="personality-add-title">{{ $t('settings.persona.addPersonality') }}</span>
          <span class="personality-add-desc">{{ $t('settings.persona.addPersonalityHint') }}</span>
        </button>
      </div>
    </div>

    <!-- 编辑/创建对话框 -->
    <PersonalityEditDialog
      v-if="editingPersonality"
      :personality="editingPersonality"
      :is-new="isCreating"
      :show-id="false"
      @save="savePersonality"
      @cancel="closeDialog"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Plus as PlusIcon,
  Edit as EditIcon,
  Trash as TrashIcon,
  Eye as EyeIcon,
  EyeOff as EyeOffIcon,
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
import { useConfirm } from '@/composables/useConfirm'
import { useUserStore } from '@/store/user'
import Button from '@/components/ui/Button.vue'
import PersonalityEditDialog from './PersonalityEditDialog.vue'

const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const userStore = useUserStore()

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
const canManage = (personality: Personality) =>
  !personality.is_builtin || userStore.isAdmin

function createPersonalityId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `persona-${crypto.randomUUID()}`
  }
  return `persona-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

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
    id: createPersonalityId(),
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
  await confirm({
    title: t('common.confirmDelete'),
    message: t('settings.persona.confirmDelete', { name: personality.name }),
    type: 'danger',
    confirmText: t('common.delete'),
    confirmVariant: 'danger',
    onConfirm: async () => {
      try {
        await personalitiesApi.delete(personality.id)
        toast.success(t('settings.persona.deleteSuccess'))
        await loadPersonalities()
      } catch (error: any) {
        console.error('Failed to delete personality:', error)
        toast.error(error.message || t('settings.persona.deleteFailed'))
      }
    }
  })
}

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
