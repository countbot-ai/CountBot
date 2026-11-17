<template>
  <div class="persona-config">
    <!-- 基础信息 -->
    <SettingsCard :title="$t('settings.persona.basicInfo')">
      <SettingsRow
        :label="$t('settings.persona.aiName')"
        :description="$t('settings.persona.aiNameHint')"
        wide-control
      >
        <input
          v-model="localPersona.ai_name"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.aiNamePlaceholder')"
          maxlength="50"
        />
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.persona.userName')"
        :description="$t('settings.persona.userNameHint')"
        wide-control
      >
        <input
          v-model="localPersona.user_name"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.userNamePlaceholder')"
          maxlength="50"
        />
      </SettingsRow>

      <SettingsRow
        :description="$t('settings.persona.userAddressHint')"
        wide-control
      >
        <template #label>
          {{ $t('settings.persona.userAddress') }}
          <span class="optional-badge">{{ $t('common.optional') }}</span>
        </template>
        <input
          v-model="localPersona.user_address"
          type="text"
          class="co-input"
          :placeholder="$t('settings.persona.userAddressPlaceholder')"
          maxlength="200"
        />
      </SettingsRow>

      <SettingsRow
        :label="$t('settings.general.outputLanguage')"
        :description="$t('settings.general.outputLanguageDesc')"
        wide-control
      >
        <OutputLanguageSelect v-model="localPersona.output_language" />
      </SettingsRow>
    </SettingsCard>

    <!-- AI性格配置 -->
    <SettingsCard
      :title="$t('settings.persona.personalityTitle')"
      :description="$t('settings.persona.personalityHint')"
    >
      <div v-if="loadingPersonalities" class="loading-personalities">
        <div class="spinner"></div>
        <p>{{ $t('common.loading') }}</p>
      </div>
      <SettingsRow v-else layout="block">
        <div class="personality-grid">
          <div
            v-for="p in personalities"
            :key="p.id"
            class="personality-btn"
            :class="{ active: localPersona.personality === p.id }"
            role="button"
            tabindex="0"
            @click="selectPersonality(p.id)"
            @keydown.enter.prevent="selectPersonality(p.id)"
          >
            <component :is="p.icon" :size="20" class="personality-icon" />
            <div class="personality-content">
              <div class="personality-name">
                <span>{{ personalityLabel(p) }}</span>
                <span v-if="p.is_builtin" class="personality-badge">
                  {{ $t('settings.persona.builtin') }}
                </span>
              </div>
              <div class="personality-desc">{{ personalityDescription(p) }}</div>
            </div>
            <div class="personality-actions">
              <Tooltip :content="$t('settings.persona.copyTooltip')" :delay="120">
                <button
                  type="button"
                  class="card-action-btn"
                  :aria-label="$t('settings.persona.copyTooltip')"
                  @click.stop="duplicatePersonality(p)"
                >
                  <component :is="CopyIcon" :size="14" />
                </button>
              </Tooltip>
              <template v-if="!p.is_builtin || userStore.isAdmin">
                <Tooltip :content="$t('settings.persona.editTooltip')" :delay="120">
                  <button
                    type="button"
                    class="card-action-btn"
                    :aria-label="$t('settings.persona.editTooltip')"
                    @click.stop="openPersonalityEditor(p.id)"
                  >
                    <component :is="Edit3" :size="14" />
                  </button>
                </Tooltip>
                <Tooltip :content="$t('settings.persona.deleteTooltip')" :delay="120">
                  <button
                    type="button"
                    class="card-action-btn danger"
                    :aria-label="$t('settings.persona.deleteTooltip')"
                    @click.stop="deletePersonality(p)"
                  >
                    <component :is="Trash2" :size="14" />
                  </button>
                </Tooltip>
              </template>
            </div>
            <div v-if="localPersona.personality === p.id" class="check-icon">
              <component :is="CheckIcon" :size="16" />
            </div>
          </div>

          <button type="button" class="personality-add" @click="openCreatePersonality">
            <component :is="Plus" :size="20" class="personality-add-icon" />
            <div class="personality-content">
              <div class="personality-name">{{ $t('settings.persona.addPersonality') }}</div>
              <div class="personality-desc">{{ $t('settings.persona.addPersonalityHint') }}</div>
            </div>
          </button>
        </div>
      </SettingsRow>
    </SettingsCard>

    <!-- 主动问候设置：推送走全局渠道配置，普通用户改这里不会生效 -->
    <SettingsCard
      v-if="!personaSource.isUserScoped.value"
      :title="$t('settings.persona.heartbeat.title')"
      :description="$t('settings.persona.heartbeat.description')"
    >
      <!-- 启用开关 -->
      <SettingsRow
        :label="$t('settings.persona.heartbeat.enabled')"
        :description="$t('settings.persona.heartbeat.enabledHint')"
      >
        <SwitchToggle
          v-model="localPersona.heartbeat.enabled"
          :width="48"
          :height="28"
          :aria-label="$t('settings.persona.heartbeat.enabled')"
        />
      </SettingsRow>

      <!-- 启用后显示详细配置 -->
      <transition name="expand">
        <div v-if="localPersona.heartbeat.enabled" class="heartbeat-details">
          <!-- 渠道选择 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.channel')"
            wide-control
          >
            <select v-model="localPersona.heartbeat.channel" class="co-select">
              <option value="">{{ $t('settings.persona.heartbeat.channelPlaceholder') }}</option>
              <option value="feishu">{{ $t('settings.persona.heartbeat.channelNames.feishu') }}</option>
              <option value="telegram">{{ $t('settings.persona.heartbeat.channelNames.telegram') }}</option>
              <option value="dingtalk">{{ $t('settings.persona.heartbeat.channelNames.dingtalk') }}</option>
              <option value="wecom">{{ $t('settings.persona.heartbeat.channelNames.wecom') }}</option>
              <option value="wechat">{{ $t('settings.persona.heartbeat.channelNames.wechat') }}</option>
              <option value="qq">{{ $t('settings.persona.heartbeat.channelNames.qq') }}</option>
            </select>
          </SettingsRow>

          <SettingsRow
            v-if="showHeartbeatAccountId"
            :label="$t('settings.persona.heartbeat.accountId')"
            :description="$t('settings.persona.heartbeat.accountIdHint')"
            wide-control
          >
            <select v-model="localPersona.heartbeat.account_id" class="co-select">
              <option
                v-for="account in heartbeatAccountOptions"
                :key="account.accountId"
                :value="account.accountId"
              >
                {{ account.label }}
              </option>
            </select>
          </SettingsRow>

          <SettingsRow
            v-else-if="localPersona.heartbeat.channel"
            :label="$t('settings.persona.heartbeat.accountId')"
          >
            <div class="auto-account-notice">
              <span class="auto-account-value">default</span>
              <p class="hint">{{ $t('settings.persona.heartbeat.accountIdAutoHint') }}</p>
            </div>
          </SettingsRow>

          <SettingsRow
            :label="$t('settings.persona.heartbeat.chatId')"
            :description="$t('settings.persona.heartbeat.chatIdHint')"
            wide-control
          >
            <input
              v-model="localPersona.heartbeat.chat_id"
              type="text"
              class="co-input"
              :placeholder="$t('settings.persona.heartbeat.chatIdPlaceholder')"
            />
          </SettingsRow>

          <!-- 空闲阈值 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.idleThreshold')"
            :description="$t('settings.persona.heartbeat.idleThresholdHint')"
            wide-control
          >
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.idle_threshold_hours"
                type="number"
                class="co-input narrow-input"
                min="1"
                max="24"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.hours') }}</span>
            </div>
          </SettingsRow>

          <!-- 每日问候次数 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.maxGreetsPerDay')"
            :description="$t('settings.persona.heartbeat.maxGreetsPerDayHint')"
            wide-control
          >
            <div class="inline-field">
              <input
                v-model.number="localPersona.heartbeat.max_greets_per_day"
                type="number"
                class="co-input narrow-input"
                min="1"
                max="5"
              />
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.timesPerDay') }}</span>
            </div>
          </SettingsRow>

          <!-- 免打扰时段 -->
          <SettingsRow
            :label="$t('settings.persona.heartbeat.quietTime')"
            :description="$t('settings.persona.heartbeat.quietTimeHint')"
            wide-control
          >
            <div class="inline-field">
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietStart') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_start" class="co-select narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
              <span class="field-suffix">{{ $t('settings.persona.heartbeat.quietEnd') }}</span>
              <select v-model.number="localPersona.heartbeat.quiet_end" class="co-select narrow-input">
                <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
              </select>
            </div>
          </SettingsRow>

          <!-- 未配置渠道提示 -->
          <div v-if="!localPersona.heartbeat.channel || !localPersona.heartbeat.chat_id" class="warning-notice">
            <component :is="AlertCircleIcon" :size="16" />
            <span>{{ $t('settings.persona.heartbeat.notConfigured') }}</span>
          </div>
        </div>
      </transition>
    </SettingsCard>

    <PersonalityEditDialog
      v-if="editingPersonality"
      :personality="editingPersonality"
      :is-new="isCreating"
      :show-id="false"
      @save="savePersonality"
      @cancel="closePersonalityEditor"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import { SettingsCard, SettingsRow, OutputLanguageSelect } from './ui'
import { 
  MessageSquare as MessageSquareIcon,
  Check as CheckIcon,
  AlertCircle as AlertCircleIcon,
  Smile,
  Laugh,
  Snowflake,
  TrendingUp,
  Frown,
  Clock,
  Target,
  Gamepad2,
  BookOpen,
  Edit3,
  Copy as CopyIcon,
  Heart,
  CloudLightning,
  Plus,
  Trash2,
} from 'lucide-vue-next'
import Tooltip from '@/components/ui/Tooltip.vue'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { useUserStore } from '@/store/user'
import { personalitiesApi, type Personality } from '@/api/personalities'
import { usePersonaSource } from '@/composables/usePersonaSource'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import PersonalityEditDialog from './PersonalityEditDialog.vue'

const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()
const userStore = useUserStore()
// 人设读写按身份分流：管理员用全局配置，普通用户用 /api/me/persona
const personaSource = usePersonaSource()

interface HeartbeatConfig {
  enabled: boolean
  channel: string
  account_id: string
  chat_id: string
  schedule: string
  idle_threshold_hours: number
  quiet_start: number
  quiet_end: number
  max_greets_per_day?: number
}

interface PersonaConfig {
  ai_name: string
  user_name: string
  user_address: string
  output_language: string
  personality: string
  custom_personality: string
  max_history_messages: number
  enable_short_context_summary: boolean
  heartbeat: HeartbeatConfig
}

type PersonaConfigInput = Omit<Partial<PersonaConfig>, 'heartbeat'> & {
  heartbeat?: Partial<HeartbeatConfig>
}

const defaultHeartbeat = {
  enabled: false,
  channel: '',
  account_id: 'default',
  chat_id: '',
  schedule: '0 * * * *',
  idle_threshold_hours: 4,
  quiet_start: 21,
  quiet_end: 8,
  max_greets_per_day: 2,
}

const normalizeHistoryLimit = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0
  }
  return value <= 0 ? 0 : value
}

const createLocalPersonaState = (persona?: PersonaConfigInput): PersonaConfig => ({
  ai_name: persona?.ai_name ?? '',
  user_name: persona?.user_name ?? '',
  user_address: persona?.user_address || '',
  output_language: persona?.output_language || '中文',
  personality: persona?.personality ?? 'grumpy',
  custom_personality: persona?.custom_personality ?? '',
  max_history_messages: normalizeHistoryLimit(persona?.max_history_messages),
  enable_short_context_summary: persona?.enable_short_context_summary ?? false,
  heartbeat: {
    ...defaultHeartbeat,
    ...(persona?.heartbeat || {}),
  },
})

const localPersona = ref<PersonaConfig>(createLocalPersonaState(settingsStore.settings?.persona))

// 图标映射
const iconMap: Record<string, any> = {
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare: MessageSquareIcon,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
  Edit3,
}

type PersonalityCard = Personality & { icon: any }

const personalities = ref<PersonalityCard[]>([])
const loadingPersonalities = ref(false)
const personalityRecords = ref<Record<string, Personality>>({})
const editingPersonality = ref<Personality | null>(null)
const isCreating = ref(false)

/** 内置文案默认走 i18n；字段被修改后改用数据库内容 */
function isEditedBuiltin(p: Personality): boolean {
  if (!p.is_builtin) return false
  const created = Date.parse(p.created_at || '')
  const updated = Date.parse(p.updated_at || '')
  return Number.isFinite(created) && Number.isFinite(updated) && updated - created > 1000
}

function translateOr(key: string, fallback: string): string {
  const translated = t(key)
  return translated === key ? fallback : translated
}

function personalityLabel(p: Personality): string {
  if (p.is_builtin && !isEditedBuiltin(p)) {
    return translateOr(`settings.persona.personalities.${p.id}`, p.name)
  }
  return p.name
}

function personalityDescription(p: Personality): string {
  if (p.is_builtin && !isEditedBuiltin(p)) {
    return translateOr(`settings.persona.personalityDesc.${p.id}`, p.description)
  }
  return p.description
}

function generatePersonalityId(): string {
  const random = globalThis.crypto?.randomUUID?.() || Date.now().toString(36)
  return `persona-${random}`
}

function createEmptyPersonality(): Personality {
  return {
    id: generatePersonalityId(),
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
}

/** 当前选择不存在时回落到默认或首个可用项 */
function ensureValidSelection(items: PersonalityCard[]) {
  if (items.some(p => p.id === localPersona.value.personality)) {
    return
  }
  const fallback = items.find(p => p.id === 'default') || items[0]
  localPersona.value.personality = fallback?.id || ''
  localPersona.value.custom_personality = ''
}

// 加载性格列表
const loadPersonalities = async () => {
  loadingPersonalities.value = true
  try {
    const { personalities: data } = await personalitiesApi.list(true)
    const activeItems = data.filter(p => p.is_active)
    personalityRecords.value = Object.fromEntries(activeItems.map(p => [p.id, p]))
    personalities.value = activeItems.map(p => ({
      ...p,
      icon: iconMap[p.icon] || Smile,
    }))
    ensureValidSelection(personalities.value)
  } catch (error: any) {
    console.error('Failed to load personalities:', error)
    personalityRecords.value = {}
    personalities.value = []
    toast.error(error.message || t('settings.persona.loadFailed'))
  } finally {
    loadingPersonalities.value = false
  }
}

/** 添加性格 */
function openCreatePersonality() {
  editingPersonality.value = createEmptyPersonality()
  isCreating.value = true
}

/** 编辑性格 */
function openPersonalityEditor(id: string) {
  const personality = personalityRecords.value[id]
  if (!personality) {
    toast.error(t('settings.persona.loadFailed'))
    return
  }
  editingPersonality.value = { ...personality }
  isCreating.value = false
}

function closePersonalityEditor() {
  editingPersonality.value = null
  isCreating.value = false
}

/** 保存新增或编辑结果 */
async function savePersonality(personality: Personality) {
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
    closePersonalityEditor()
  } catch (error: any) {
    console.error('Failed to save personality:', error)
    toast.error(error.message || t('settings.persona.saveFailed'))
  }
}

/** 复制性格，基于内置或已有性格生成一份自定义副本 */
async function duplicatePersonality(personality: Personality) {
  try {
    const sourceName = personalityLabel(personality)
    await personalitiesApi.duplicate(personality.id, {
      id: generatePersonalityId(),
      name: t('settings.persona.copyName', { name: sourceName }),
    })
    toast.success(t('settings.persona.copySuccess'))
    await loadPersonalities()
  } catch (error: any) {
    console.error('Failed to duplicate personality:', error)
    toast.error(error.message || t('settings.persona.copyFailed'))
  }
}

/** 删除性格，内置与新增使用同一确认流程 */
async function deletePersonality(personality: Personality) {
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
        throw error
      }
    },
  })
}

onMounted(() => {
  loadPersonalities()
})

const hasConfiguredFields = (account: Record<string, any>) =>
  Object.entries(account || {}).some(([key, value]) => {
    if (['enabled', 'allow_from', 'account_id', 'draft_account_id', 'accounts'].includes(key)) {
      return false
    }
    if (Array.isArray(value)) {
      return value.length > 0
    }
    return Boolean(value)
  })

const getHeartbeatChannelAccountIds = (channelId: string) => {
  const normalizedChannelId = String(channelId || '').trim()
  if (!normalizedChannelId) {
    return []
  }

  const config = channelsStore.channels[normalizedChannelId]?.config || {}
  const statusInstances = channelsStore.status[normalizedChannelId]?.instances || {}
  const accountIds = new Set<string>()

  const addAccount = (accountId: string, account: Record<string, any> = {}, fromStatus = false) => {
    const normalizedAccountId = String(accountId || 'default').trim() || 'default'
    const configured = hasConfiguredFields(account)
    if (!configured && !account.enabled && !fromStatus) {
      return
    }
    accountIds.add(normalizedAccountId)
  }

  addAccount(String(config.account_id || 'default'), config)

  Object.entries(config.accounts || {}).forEach(([accountId, account]) => {
    addAccount(accountId, account as Record<string, any>)
  })

  Object.entries(statusInstances).forEach(([accountId, account]) => {
    addAccount(accountId, account as Record<string, any>, true)
  })

  return Array.from(accountIds).sort((left, right) => {
    if (left === 'default') return -1
    if (right === 'default') return 1
    return left.localeCompare(right)
  })
}

const heartbeatChannelAccountIds = computed(() =>
  getHeartbeatChannelAccountIds(localPersona.value.heartbeat.channel)
)

const showHeartbeatAccountId = computed(() => heartbeatChannelAccountIds.value.length > 1)

const heartbeatAccountOptions = computed(() => {
  const channelId = localPersona.value.heartbeat.channel
  const config = (channelsStore.channels[channelId]?.config || {}) as Record<string, any>
  const accounts = (config.accounts || {}) as Record<string, Record<string, any>>
  const primaryAccountId = String(config.account_id || 'default')

  return heartbeatChannelAccountIds.value.map((accountId) => {
    const account = accountId === primaryAccountId ? config : (accounts[accountId] || {})
    const displayName = String(account.display_name || '').trim()
    return {
      accountId,
      label: displayName ? `${displayName}（${accountId}）` : accountId,
    }
  })
})

watch(
  [() => localPersona.value.heartbeat.channel, showHeartbeatAccountId],
  () => {
    if (!showHeartbeatAccountId.value && localPersona.value.heartbeat.account_id !== 'default') {
      localPersona.value.heartbeat.account_id = 'default'
    }
  },
  { immediate: true }
)

onMounted(async () => {
  try {
    if (!Object.keys(channelsStore.channels).length) {
      await channelsStore.fetchChannels()
    }
    if (!Object.keys(channelsStore.status).length) {
      await channelsStore.fetchStatus()
    }
  } catch (error) {
    console.warn('Failed to load channel metadata for heartbeat settings:', error)
  }
})

// 选择性格
const selectPersonality = (id: string) => {
  localPersona.value.personality = id
}

// 普通用户自行拉取人设，管理员由 store watch 回填；用 watch 因身份异步到位
watch(
  () => personaSource.isUserScoped.value,
  async (scoped) => {
    if (!scoped) return
    try {
      localPersona.value = createLocalPersonaState(
        (await personaSource.load()) as PersonaConfigInput,
      )
    } catch (error) {
      console.error('Failed to load persona:', error)
    }
  },
  { immediate: true },
)

// 监听store变化（管理员路径：设置页统一提交后回填）
watch(
  () => settingsStore.settings?.persona,
  (newPersona) => {
    if (!personaSource.isUserScoped.value && newPersona) {
      localPersona.value = createLocalPersonaState(newPersona)
    }
  },
  { immediate: true, deep: true }
)

// 监听本地变化并更新store（使用immediate: false避免递归）
let isUpdating = false
watch(
  localPersona,
  (newValue) => {
    if (isUpdating) return
    const normalized = {
      ...newValue,
      max_history_messages: normalizeHistoryLimit(newValue.max_history_messages),
      output_language:
        newValue.output_language || settingsStore.settings?.persona?.output_language || '中文',
    }
    // 普通用户直接调用接口保存，不写入全局配置
    if (personaSource.isUserScoped.value) {
      return
    }
    if (settingsStore.settings) {
      isUpdating = true
      settingsStore.settings.persona = normalized
      setTimeout(() => {
        isUpdating = false
      }, 0)
    }
  },
  { deep: true }
)

/** 保存人设：管理员已在 store 更新，普通用户需在此落库 */
async function saveConfig(): Promise<boolean> {
  // 历史条数由通用配置页负责，避免两处草稿互相覆盖
  const payload = {
    ai_name: localPersona.value.ai_name,
    user_name: localPersona.value.user_name,
    user_address: localPersona.value.user_address,
    output_language: localPersona.value.output_language,
    personality: localPersona.value.personality,
    custom_personality: localPersona.value.custom_personality,
    heartbeat: localPersona.value.heartbeat,
  }
  await personaSource.save(payload)
  return true
}

defineExpose({ saveConfig })

</script>
<style scoped>
@import './styles/PersonaConfig.css';
</style>
