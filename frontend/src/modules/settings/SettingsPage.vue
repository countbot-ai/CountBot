<template>
  <div class="co-settings">
    <!-- 左侧导航：分组 + 返回 -->
    <aside class="co-nav">
      <div class="co-nav-head">
        <button class="co-nav-back" :title="$t('settings.backToChat')" @click="goBack">
          <component :is="ArrowLeftIcon" :size="16" class="co-nav-back-icon" />
          <span class="co-nav-back-label">{{ $t('settings.backToChat') }}</span>
        </button>
      </div>

      <div class="co-nav-scroll">
        <div v-for="group in navGroups" :key="group.id" class="co-nav-group">
          <p class="co-nav-group-label">{{ $t(group.labelKey) }}</p>
          <button
            v-for="tab in group.tabs"
            :key="tab.id"
            class="co-nav-item"
            :class="{ 'is-active': activeTab === tab.id }"
            :title="$t(tab.labelKey)"
            :aria-current="activeTab === tab.id ? 'page' : undefined"
            @click="goToTab(tab.id)"
          >
            <component :is="tab.icon" :size="16" class="co-nav-item-icon" />
            <span class="co-nav-item-label">{{ $t(navLabel(tab)) }}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <section class="co-panel">
      <header class="co-panel-head">
        <nav class="co-breadcrumb">
          <span>{{ $t('settings.title') }}</span>
          <span class="co-breadcrumb-sep">/</span>
          <span class="co-breadcrumb-current">{{ $t(currentTab.labelKey) }}</span>
        </nav>

        <div class="co-panel-actions">
          <span class="co-save-state" :class="{ 'is-dirty': isDirty }">
            <span class="co-save-state-dot" />
            {{ saveStateText }}
          </span>
          <template v-if="!isInstantTab">
            <!-- 「保存全部」提交的是全局配置，用户级入口没有该语义 -->
            <button
              v-if="userStore.isAdmin"
              class="co-btn co-btn--secondary"
              :disabled="saving"
              @click="handleSaveAll"
            >
              {{ $t('settings.saveAll') }}
            </button>
            <button class="co-btn co-btn--primary" :disabled="saving" @click="handleSave">
              {{ saving ? $t('common.saving') : $t('common.save') }}
            </button>
          </template>
        </div>
      </header>

      <div class="co-panel-body">
        <div
          class="co-panel-inner"
          :class="{ 'is-full': currentTab.fullHeight, 'is-bare': isBareTab }"
        >
          <SettingsPageHeader
            v-if="!isBareTab"
            :title="$t(currentTab.labelKey)"
            :description="$t(currentTab.descKey)"
          />

          <p v-if="loadFailed" class="co-empty">
            {{ $t('settings.loadError') }}
            <button class="co-btn co-btn--secondary load-retry" @click="loadSettings">
              {{ $t('common.retry') }}
            </button>
          </p>

          <p v-else-if="!tabReady" class="co-empty">{{ $t('common.loading') }}</p>

          <component :is="currentComponent" v-else :key="paneKey" ref="tabComponentRef" v-bind="componentProps" />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft as ArrowLeftIcon,
  Brain as BrainIcon,
  Cpu as CpuIcon,
  Download as DownloadIcon,
  Filter as FilterIcon,
  FolderOpen as FolderIcon,
  Server as ServerIcon,
  Settings as SettingsIcon,
  Shield as ShieldIcon,
  Sliders as SlidersIcon,
  TerminalSquare as TerminalSquareIcon,
  Users as UsersIcon,
} from 'lucide-vue-next'
import { SettingsPageHeader } from './ui'
import GeneralConfig from './GeneralConfig.vue'
import ProviderConfig from './ProviderConfig.vue'
import ModelConfig from './ModelConfig.vue'
import WorkspaceConfig from './WorkspaceConfig.vue'
import SecurityConfig from './SecurityConfig.vue'
import InjectionPanel from './InjectionPanel.vue'
import McpPanel from '@/modules/mcp/McpPanel.vue'
import UserMcpPanel from '@/modules/mcp/UserMcpPanel.vue'
import SharedSkillsPanel from '@/modules/skills/SharedSkillsPanel.vue'
import ExternalCodingToolsConfig from './ExternalCodingToolsConfig.vue'
import ConfigImportExport from './ConfigImportExport.vue'
import MemoryPanel from '@/modules/memory/MemoryPanel.vue'
import UserManagement from '@/modules/admin/UserManagement.vue'
import { useUserStore } from '@/store/user'
import { useSettingsStore } from '@/store/settings'
import { useExternalCodingToolsStore } from '@/store/externalCodingTools'
import { useToast } from '@/composables/useToast'
import type { SettingsTab } from '@/types/settings'

interface TabMeta {
  id: SettingsTab
  icon: Component
  labelKey: string
  descKey: string
  /** 保存由页面自己完成时置为 true，页头不再提供保存按钮 */
  instant?: boolean
  /** 需要完整高度（记忆面板是自绘两栏） */
  fullHeight?: boolean
  /** 自绘全屏工作区：不渲染页内标题，也不留外边距 */
  bare?: boolean
}

const PERSONAL_GROUP = { id: 'personal', labelKey: 'settings.navGroups.personal' }
const MODEL_GROUP = { id: 'model', labelKey: 'settings.navGroups.model' }
const CONNECT_GROUP = { id: 'connect', labelKey: 'settings.navGroups.connect' }
const SYSTEM_GROUP = { id: 'system', labelKey: 'settings.navGroups.system' }

const TABS: TabMeta[] = [
  { id: 'general', icon: SettingsIcon, labelKey: 'settings.tabs.general', descKey: 'settings.tabDesc.general' },
  { id: 'memory', icon: BrainIcon, labelKey: 'settings.tabs.memory', descKey: 'settings.tabDesc.memory', instant: true },

  { id: 'provider', icon: ServerIcon, labelKey: 'settings.tabs.provider', descKey: 'settings.tabDesc.provider', fullHeight: true, bare: true },
  { id: 'model', icon: SlidersIcon, labelKey: 'settings.tabs.model', descKey: 'settings.tabDesc.model' },
  { id: 'injection', icon: FilterIcon, labelKey: 'settings.tabs.injection', descKey: 'settings.tabDesc.injection' },

  { id: 'mcp', icon: CpuIcon, labelKey: 'settings.tabs.mcp', descKey: 'settings.tabDesc.mcp', instant: true },
  { id: 'externaltools', icon: TerminalSquareIcon, labelKey: 'settings.tabs.externaltools', descKey: 'settings.tabDesc.externaltools' },

  { id: 'workspace', icon: FolderIcon, labelKey: 'settings.tabs.workspace', descKey: 'settings.tabDesc.workspace' },
  { id: 'security', icon: ShieldIcon, labelKey: 'settings.tabs.security', descKey: 'settings.tabDesc.security' },
  { id: 'sharedskills', icon: UsersIcon, labelKey: 'settings.tabs.sharedskills', descKey: 'settings.tabDesc.sharedskills', instant: true },
  { id: 'importexport', icon: DownloadIcon, labelKey: 'settings.tabs.importexport', descKey: 'settings.tabDesc.importexport', instant: true },
  { id: 'users', icon: UsersIcon, labelKey: 'settings.tabs.users', descKey: 'settings.tabDesc.users', instant: true },
]

const GROUP_OF: Record<SettingsTab, { id: string; labelKey: string }> = {
  general: PERSONAL_GROUP,
  persona: PERSONAL_GROUP,
  memory: PERSONAL_GROUP,
  provider: MODEL_GROUP,
  model: MODEL_GROUP,
  multiagent: MODEL_GROUP,
  injection: MODEL_GROUP,
  channels: CONNECT_GROUP,
  mcp: CONNECT_GROUP,
  externaltools: CONNECT_GROUP,
  notifications: CONNECT_GROUP,
  workspace: SYSTEM_GROUP,
  security: SYSTEM_GROUP,
  sharedskills: SYSTEM_GROUP,
  importexport: SYSTEM_GROUP,
  users: SYSTEM_GROUP,
}

/** 管理员专属入口；普通用户直接看不到，越权路由回落到 general */
const ADMIN_ONLY_TABS = new Set<SettingsTab>([
  'provider', 'security', 'workspace',
  'injection', 'externaltools', 'importexport', 'users',
])

/** 渲染前需拿到 settings 的入口；仅对管理员成立，普通用户由 /api/me/* 自行取数 */
const NEEDS_SETTINGS = new Set<SettingsTab>([
  'general', 'persona', 'provider', 'model', 'workspace',
  'security', 'injection', 'multiagent',
])

/** 普通用户可见、但需要全局配置的入口：没有管理员身份就不该等全局 settings */
const USER_TABS_WITHOUT_GLOBAL_SETTINGS = new Set<SettingsTab>([
  'general', 'persona', 'model', 'mcp', 'multiagent',
])

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
const settingsStore = useSettingsStore()
const externalCodingToolsStore = useExternalCodingToolsStore()
const toast = useToast()

const emit = defineEmits<{ saved: [] }>()

const loadFailed = ref(false)
const settingsLoaded = ref(false)
const tabComponentRef = ref<
  { validateBeforeSave?: () => string | null; saveConfig?: () => Promise<boolean> } | null
>(null)

const saving = computed(() => settingsStore.saving)

const visibleTabs = computed(() =>
  TABS.filter((tab) => {
    if (ADMIN_ONLY_TABS.has(tab.id) && !userStore.isAdmin) return false
    return true
  }),
)

const navGroups = computed(() =>
  [PERSONAL_GROUP, MODEL_GROUP, CONNECT_GROUP, SYSTEM_GROUP]
    .map((group) => ({
      ...group,
      tabs: visibleTabs.value.filter((tab) => GROUP_OF[tab.id].id === group.id),
    }))
    .filter((group) => group.tabs.length > 0),
)

const readRouteTab = (): SettingsTab => {
  const raw = String(route.params.tab ?? '')
  return TABS.some((tab) => tab.id === raw) ? (raw as SettingsTab) : 'general'
}

const activeTab = ref<SettingsTab>(readRouteTab())

const currentTab = computed(() => TABS.find((tab) => tab.id === activeTab.value) ?? TABS[0])

/** 身份未就绪时放行，避免直链进入管理员页时闪烁；越权判定交给 loaded 后的 visibleTabs */
const tabAuthorized = computed(
  () => !userStore.loaded || visibleTabs.value.some((tab) => tab.id === activeTab.value),
)

/** model / mcp 按身份切换实现，其余一对一 */
const currentComponent = computed<Component | undefined>(() => {
  switch (activeTab.value) {
    case 'model':
      // 管理员保持「默认模型与生成参数」；普通用户渲染与 provider tab 同一个
      // 供应商配置组件，仅数据源换成 /api/me/providers
      return userStore.isAdmin ? ModelConfig : ProviderConfig
    case 'mcp':
      return userStore.isAdmin ? McpPanel : UserMcpPanel
    case 'general':
      return GeneralConfig
    case 'provider':
      return ProviderConfig
    case 'memory':
      return MemoryPanel
    case 'injection':
      return InjectionPanel
    case 'externaltools':
      return ExternalCodingToolsConfig
    case 'workspace':
      return WorkspaceConfig
    case 'security':
      return SecurityConfig
    case 'sharedskills':
      return SharedSkillsPanel
    case 'importexport':
      return ConfigImportExport
    case 'users':
      return UserManagement
    default:
      return undefined
  }
})

const paneKey = computed(() => activeTab.value)

/** 普通用户的 model tab 渲染同一套供应商配置组件，数据源走用户端点 */
const componentProps = computed<Record<string, unknown>>(() =>
  activeTab.value === 'model' && !userStore.isAdmin ? { scope: 'user' } : {},
)

/** 普通用户的 model tab 与管理员 provider tab 是同一能力，标签复用「模型配置」 */
const navLabel = (tab: TabMeta): string =>
  tab.id === 'model' && !userStore.isAdmin ? 'settings.tabs.provider' : tab.labelKey

/** 自绘全屏工作区：不渲染页内标题，也不留页面级内边距 */
const isBareTab = computed(
  () =>
    Boolean(currentTab.value.bare) ||
    (activeTab.value === 'model' && !userStore.isAdmin),
)

/** 用户级页面自带保存入口，页面级不再重复给按钮 */
const isInstantTab = computed(
  () =>
    Boolean(currentTab.value.instant) ||
    (activeTab.value === 'model' && !userStore.isAdmin),
)

const tabReady = computed(() => {
  if (!tabAuthorized.value) return false
  if (!NEEDS_SETTINGS.has(activeTab.value)) return true
  // 普通用户读不到全局配置，由用户级实现取数；身份未就绪时不作此判断
  if (
    userStore.loaded &&
    !userStore.isAdmin &&
    USER_TABS_WITHOUT_GLOBAL_SETTINGS.has(activeTab.value)
  ) {
    return true
  }
  return settingsLoaded.value && Boolean(settingsStore.settings)
})

const isDirty = computed(() => {
  const current = settingsStore.settings
  const persisted = settingsStore.persistedSettings
  if (!current || !persisted) return false
  return JSON.stringify(current) !== JSON.stringify(persisted)
})

const saveStateText = computed(() => {
  if (saving.value) return t('settings.saveState.saving')
  if (isInstantTab.value) return t('settings.saveState.instant')
  if (isDirty.value) return t('settings.saveState.dirty')
  return t('settings.saveState.saved')
})

const goToTab = (tab: SettingsTab) => {
  if (tab === activeTab.value) return
  activeTab.value = tab
  void router.replace({ name: 'settings', params: { tab } })
}

/** 固定回聊天首页：浏览器历史可能指向登录页或其它设置页，不能作为返回目标 */
const goBack = () => {
  void router.replace({ name: 'home' })
}

const loadSettings = async () => {
  loadFailed.value = false
  try {
    await settingsStore.loadSettings()
    settingsLoaded.value = true
  } catch (error) {
    console.error('Failed to load settings:', error)
    loadFailed.value = true
  }
}

watch(
  () => route.params.tab,
  () => {
    activeTab.value = readRouteTab()
  },
)

// 身份异步到位后可见分组会变，落在被隐藏的入口上要退回 general
watch([visibleTabs, () => userStore.loaded], ([tabs, loaded]) => {
  if (!loaded) return
  if (!tabs.some((tab) => tab.id === activeTab.value)) goToTab('general')
})

/** 供应商一个模型都没有时，保存后补一条提示：它在对话窗口里选不到 */
const warnProviderWithoutModels = () => {
  const warning = tabComponentRef.value?.validateBeforeSave?.()
  if (warning) toast.warning(warning)
}

/** 交由子页自行保存；子页暴露 saveConfig()，成功与失败提示在此统一处理 */
const saveViaTabComponent = async (errorMessage: string) => {
  const saveConfig = tabComponentRef.value?.saveConfig
  // 子页可能是即时保存型（没有 saveConfig），此时不能谎报保存成功
  if (!saveConfig) return
  try {
    await saveConfig()
    toast.success(t('settings.saveSuccess'), t('common.success'))
    emit('saved')
  } catch (error) {
    console.error('Failed to save via tab component:', error)
    toast.error(errorMessage, t('common.error'))
  }
}

const handleSave = async () => {
  const currentSettings = settingsStore.settings

  // 用户级通用设置不经全局配置：普通用户的 store 为空，需在判空之前分流
  if (!userStore.isAdmin && activeTab.value === 'general') {
    await saveViaTabComponent(t('settings.saveError'))
    return
  }

  if (!currentSettings) {
    toast.error(t('settings.loadError'), t('common.error'))
    return
  }

  let savePayload: Record<string, unknown> = {}

  switch (activeTab.value) {
    case 'provider':
    case 'model':
      // 提供商与模型参数共用一组草稿
      savePayload = { providers: currentSettings.providers, model: currentSettings.model }
      break
    case 'workspace':
      savePayload = { workspace: currentSettings.workspace }
      break
    case 'security':
      savePayload = { security: currentSettings.security }
      break
    case 'externaltools':
      try {
        await tabComponentRef.value?.saveConfig?.()
        toast.success(t('settings.saveSuccess'), t('common.success'))
        emit('saved')
      } catch (error) {
        console.error('Failed to save external coding tools:', error)
        toast.error(t('settings.saveError'), t('common.error'))
      }
      return
    default:
      savePayload = { ...currentSettings }
  }

  try {
    await settingsStore.saveSettings(savePayload)
    toast.success(t('settings.saveSuccess'), t('common.success'))
    warnProviderWithoutModels()
    emit('saved')
  } catch (error) {
    console.error('Failed to save settings:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  }
}

const handleSaveAll = async () => {
  const currentSettings = settingsStore.settings
  if (!currentSettings) {
    toast.error(t('settings.loadError'), t('common.error'))
    return
  }

  try {
    await settingsStore.saveSettings({ ...currentSettings }, { includeChannels: true })
    if (externalCodingToolsStore.config) {
      await externalCodingToolsStore.saveConfig()
    }
    toast.success(t('settings.saveAllSuccess'), t('common.success'))
    warnProviderWithoutModels()
    emit('saved')
  } catch (error) {
    console.error('Failed to save all settings:', error)
    toast.error(t('settings.saveError'), t('common.error'))
  }
}

onMounted(async () => {
  await userStore.loadProfile()
  // 全局配置仅管理员可读：普通用户调用会 403，其数据由用户级实现自取
  if (userStore.isAdmin) {
    await loadSettings()
  }
})
</script>
