<template>
  <div class="config-import-export">
    <div class="section-header">
      <h3 class="section-title">{{ $t('settings.importExport.title') }}</h3>
      <p class="section-desc">{{ $t('settings.importExport.description') }}</p>
    </div>

    <div class="overview-card">
      <div class="overview-item">
        <component :is="DatabaseIcon" :size="18" class="overview-icon" />
        <div class="overview-text">
          <strong>{{ availableSections.length }}</strong>
          <span>可选配置块</span>
        </div>
      </div>
      <div class="overview-item">
        <component :is="RefreshCwIcon" :size="18" class="overview-icon" />
        <div class="overview-text">
          <strong>2</strong>
          <span>导入模式</span>
        </div>
      </div>
      <div class="overview-item">
        <component :is="NetworkIcon" :size="18" class="overview-icon" />
        <div class="overview-text">
          <strong>JSON</strong>
          <span>统一迁移格式</span>
        </div>
      </div>
    </div>

    <div class="config-cards">
      <article class="config-card export-card">
        <div class="card-header">
          <div class="header-icon export">
            <DownloadIcon :size="20" />
          </div>
          <div class="header-text">
            <h4 class="card-title">{{ $t('settings.importExport.export') }}</h4>
            <p class="card-desc">{{ $t('settings.importExport.exportDesc') }}</p>
          </div>
        </div>

        <div class="card-body">
          <ul class="feature-list">
            <li>
              <CheckCircle2Icon :size="16" />
              <span>按配置块精确导出，避免把无关设置一起带走</span>
            </li>
            <li>
              <CheckCircle2Icon :size="16" />
              <span>默认不包含敏感密钥，适合发给同事或迁移环境</span>
            </li>
            <li>
              <CheckCircle2Icon :size="16" />
              <span>额外支持 Coding Plan 与智能体团队导出</span>
            </li>
          </ul>

          <div class="card-footer">
            <button @click="showExportDialog = true" class="action-btn primary" :disabled="isExporting">
              <DownloadIcon :size="16" />
              <span>{{ $t('settings.importExport.exportButton') }}</span>
            </button>
            <p class="footer-hint">支持全局设置、本地扩展配置和多智能体团队</p>
          </div>
        </div>
      </article>

      <article class="config-card import-card">
        <div class="card-header">
          <div class="header-icon import">
            <UploadIcon :size="20" />
          </div>
          <div class="header-text">
            <h4 class="card-title">{{ $t('settings.importExport.import') }}</h4>
            <p class="card-desc">{{ $t('settings.importExport.importDesc') }}</p>
          </div>
        </div>

        <div class="card-body">
          <ul class="feature-list">
            <li>
              <CheckCircle2Icon :size="16" />
              <span>支持覆盖和合并两种导入策略</span>
            </li>
            <li>
              <CheckCircle2Icon :size="16" />
              <span>导入后立即应用全局设置，并刷新渠道配置</span>
            </li>
            <li>
              <CheckCircle2Icon :size="16" />
              <span>智能体团队按团队名称更新，支持整批恢复</span>
            </li>
          </ul>

          <div class="card-footer">
            <button @click="triggerImport" class="action-btn secondary" :disabled="isImporting">
              <UploadIcon :size="16" />
              <span>{{ $t('settings.importExport.importButton') }}</span>
            </button>
            <p class="footer-hint">支持带团队配置的导出文件直接回填</p>
            <input
              ref="fileInput"
              type="file"
              accept=".json"
              class="hidden-input"
              @change="handleFileSelect"
            />
          </div>
        </div>
      </article>
    </div>

    <teleport to="body">
      <div v-if="showExportDialog" class="modal-overlay" @click="showExportDialog = false">
        <div class="modal-dialog" @click.stop>
          <div class="modal-header">
            <div>
              <h3 class="modal-title">{{ $t('settings.importExport.exportOptions') }}</h3>
              <p class="modal-subtitle">选择要打包的配置块，并决定是否附带敏感信息</p>
            </div>
            <button class="modal-close" @click="showExportDialog = false">
              <XIcon :size="20" />
            </button>
          </div>

          <div class="modal-body">
            <section class="panel-card warning-panel">
              <div class="panel-header">
                <div class="panel-icon">
                  <KeyIcon :size="16" />
                </div>
                <div>
                  <h4>敏感信息</h4>
                  <p>默认关闭，导出文件更适合跨机器迁移或共享给他人</p>
                </div>
              </div>

              <label class="toggle-card" :class="{ active: exportOptions.includeApiKeys }">
                <input type="checkbox" v-model="exportOptions.includeApiKeys" />
                <div class="toggle-card-main">
                  <span class="toggle-card-title">
                    <AlertTriangleIcon :size="16" class="warning-icon" />
                    {{ $t('settings.importExport.includeApiKeys') }}
                  </span>
                  <span class="toggle-card-desc">{{ $t('settings.importExport.apiKeysWarning') }}</span>
                </div>
              </label>
            </section>

            <section class="panel-card">
              <div class="panel-header">
                <div class="panel-icon">
                  <DatabaseIcon :size="16" />
                </div>
                <div>
                  <h4>{{ $t('settings.importExport.selectSections') }}</h4>
                  <p>后端配置、本地 Coding Plan 和智能体团队可以一起导出</p>
                </div>
              </div>

              <div class="section-grid">
                <label
                  v-for="section in availableSections"
                  :key="section.key"
                  class="section-option"
                  :class="{ selected: exportOptions.sections.includes(section.key) }"
                >
                  <input
                    type="checkbox"
                    :value="section.key"
                    v-model="exportOptions.sections"
                  />
                  <span class="section-icon">
                    <component :is="section.icon" :size="16" />
                  </span>
                  <span class="section-copy">
                    <strong>{{ getSectionLabel(section.key) }}</strong>
                    <small>{{ section.scope === 'server' ? '系统配置' : '本地扩展' }}</small>
                  </span>
                </label>
              </div>
            </section>

            <section class="summary-panel">
              <div class="summary-top">
                <span>导出摘要</span>
                <strong>已选择 {{ exportOptions.sections.length }} 个配置块</strong>
              </div>
              <div v-if="selectedSectionLabels.length" class="summary-tags">
                <span
                  v-for="label in selectedSectionLabels"
                  :key="label"
                  class="summary-tag"
                >
                  {{ label }}
                </span>
              </div>
              <p class="summary-note">
                {{ exportOptions.includeApiKeys ? '将包含敏感密钥，请谨慎存放导出文件。' : '不会导出敏感密钥，适合常规备份和迁移。' }}
              </p>
            </section>
          </div>

          <div class="modal-footer">
            <button @click="showExportDialog = false" class="btn btn-secondary">
              {{ $t('common.cancel') }}
            </button>
            <button
              @click="handleExport"
              class="btn btn-primary"
              :disabled="exportOptions.sections.length === 0 || isExporting"
            >
              <DownloadIcon :size="16" />
              <span>{{ isExporting ? '导出中...' : $t('settings.importExport.exportNow') }}</span>
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <teleport to="body">
      <div v-if="showImportDialog" class="modal-overlay" @click="showImportDialog = false">
        <div class="modal-dialog" @click.stop>
          <div class="modal-header">
            <div>
              <h3 class="modal-title">{{ $t('settings.importExport.confirmImport') }}</h3>
              <p class="modal-subtitle">先确认文件内容，再决定采用合并还是覆盖策略</p>
            </div>
            <button class="modal-close" @click="showImportDialog = false">
              <XIcon :size="20" />
            </button>
          </div>

          <div class="modal-body">
            <section class="summary-panel import-summary">
              <div class="summary-grid">
                <div class="summary-item">
                  <span class="summary-item-label">{{ $t('settings.importExport.fileVersion') }}</span>
                  <strong>{{ importData?.version || '-' }}</strong>
                </div>
                <div class="summary-item">
                  <span class="summary-item-label">{{ $t('settings.importExport.exportedAt') }}</span>
                  <strong>{{ formatDate(importData?.exported_at) }}</strong>
                </div>
              </div>

              <div class="summary-section-block">
                <span class="summary-item-label">{{ $t('settings.importExport.sections') }}</span>
                <div v-if="importedSectionLabels.length" class="summary-tags">
                  <span
                    v-for="label in importedSectionLabels"
                    :key="label"
                    class="summary-tag"
                  >
                    {{ label }}
                  </span>
                </div>
                <p v-else class="summary-note">未识别到可导入的配置节</p>
              </div>

              <p v-if="importedTeamCount > 0" class="summary-note">
                当前文件包含 {{ importedTeamCount }} 个智能体团队。
              </p>
            </section>

            <div class="alert alert-warning">
              <AlertTriangleIcon :size="20" />
              <p>{{ $t('settings.importExport.importWarning') }}</p>
            </div>

            <section class="panel-card">
              <div class="panel-header">
                <div class="panel-icon">
                  <RefreshCwIcon :size="16" />
                </div>
                <div>
                  <h4>导入策略</h4>
                  <p>合并模式保留未导入内容，覆盖模式按文件内容替换当前配置</p>
                </div>
              </div>

              <label class="toggle-card" :class="{ active: importOptions.merge }">
                <input type="checkbox" v-model="importOptions.merge" />
                <div class="toggle-card-main">
                  <span class="toggle-card-title">{{ $t('settings.importExport.mergeConfig') }}</span>
                  <span class="toggle-card-desc">{{ $t('settings.importExport.mergeHint') }}</span>
                </div>
              </label>

              <p v-if="hasImportedTeams" class="team-hint">
                {{ importOptions.merge
                  ? '智能体团队会按名称执行新增或更新，未出现在文件中的团队会保留。'
                  : '智能体团队会按名称执行替换，文件中不存在的现有团队会被删除。' }}
              </p>
            </section>
          </div>

          <div class="modal-footer">
            <button @click="showImportDialog = false" class="btn btn-secondary">
              {{ $t('common.cancel') }}
            </button>
            <button @click="handleImport" class="btn btn-danger" :disabled="isImporting">
              <UploadIcon :size="16" />
              <span>{{ isImporting ? '导入中...' : $t('settings.importExport.importNow') }}</span>
            </button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle as AlertTriangleIcon,
  CheckCircle2 as CheckCircle2Icon,
  Cpu as CpuIcon,
  Database as DatabaseIcon,
  Download as DownloadIcon,
  Folder as FolderIcon,
  Key as KeyIcon,
  MessageSquare as MessageSquareIcon,
  Network as NetworkIcon,
  RefreshCw as RefreshCwIcon,
  Settings as SettingsIcon,
  Shield as ShieldIcon,
  Upload as UploadIcon,
  User as UserIcon,
  X as XIcon,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { configAPI, type ImportConfigResponse } from '@/api/endpoints'
import {
  agentTeamsApi,
  type AgentDefinition,
  type AgentTeam,
  type TeamModelConfig,
  type TeamModelConfigResponse,
} from '@/api/agentTeams'
import { useSettingsStore } from '@/store/settings'
import { useChannelsStore } from '@/store/channels'
import { useAgentTeamsStore } from '@/store/agentTeams'

type ExportSectionKey =
  | 'providers'
  | 'model'
  | 'persona'
  | 'security'
  | 'channels'
  | 'workspace'
  | 'codingplan'
  | 'multiagent'

interface ConfigExportPayload {
  version: string
  exported_at: string
  app_version: string
  config: Record<string, any>
}

interface ExportableAgentTeam {
  id?: string
  name: string
  description?: string
  mode: 'pipeline' | 'graph' | 'council'
  agents: AgentDefinition[]
  is_active?: boolean
  cross_review?: boolean
  enable_skills?: boolean
  use_custom_model?: boolean
  model_config?: TeamModelConfig | null
}

interface AgentTeamsExportBlock {
  teams: ExportableAgentTeam[]
}

const BACKEND_SECTION_KEYS: ExportSectionKey[] = [
  'providers',
  'model',
  'persona',
  'security',
  'channels',
  'workspace',
]

const CLIENT_ONLY_SECTION_KEYS = new Set<ExportSectionKey>(['codingplan', 'multiagent'])

const toast = useToast()
const settingsStore = useSettingsStore()
const channelsStore = useChannelsStore()
const agentTeamsStore = useAgentTeamsStore()
const { t } = useI18n()

const fileInput = ref<HTMLInputElement>()
const showExportDialog = ref(false)
const showImportDialog = ref(false)
const isExporting = ref(false)
const isImporting = ref(false)

const exportOptions = ref<{ includeApiKeys: boolean; sections: ExportSectionKey[] }>({
  includeApiKeys: false,
  sections: ['providers', 'model', 'persona', 'security'],
})

const importOptions = ref({
  merge: false,
})

const importData = ref<ConfigExportPayload | null>(null)

const availableSections = [
  { key: 'providers' as const, icon: SettingsIcon, scope: 'server' as const },
  { key: 'model' as const, icon: CpuIcon, scope: 'server' as const },
  { key: 'persona' as const, icon: UserIcon, scope: 'server' as const },
  { key: 'security' as const, icon: ShieldIcon, scope: 'server' as const },
  { key: 'channels' as const, icon: MessageSquareIcon, scope: 'server' as const },
  { key: 'workspace' as const, icon: FolderIcon, scope: 'server' as const },
  { key: 'codingplan' as const, icon: CpuIcon, scope: 'local' as const },
  { key: 'multiagent' as const, icon: NetworkIcon, scope: 'local' as const },
]

const selectedSectionLabels = computed(() => getAppliedSectionLabels(exportOptions.value.sections))
const importedSectionKeys = computed(() => Object.keys(importData.value?.config || {}) as ExportSectionKey[])
const importedSectionLabels = computed(() => getAppliedSectionLabels(importedSectionKeys.value))
const importedTeamCount = computed(() => {
  try {
    return extractImportedTeams(importData.value?.config?.multiagent).length
  } catch {
    return 0
  }
})
const hasImportedTeams = computed(() => importedTeamCount.value > 0)

function getSectionLabel(sectionKey: string): string {
  const label = t(`settings.section.${sectionKey}`)
  return label === `settings.section.${sectionKey}` ? sectionKey : label
}

function getAppliedSectionLabels(sectionKeys: string[]): string[] {
  const orderedKeys = availableSections
    .map(section => section.key)
    .filter(key => sectionKeys.includes(key))

  const knownLabels = orderedKeys.map(key => getSectionLabel(key))
  const unknownLabels = sectionKeys
    .filter(key => !orderedKeys.includes(key as ExportSectionKey))
    .map(key => getSectionLabel(key))

  return [...knownLabels, ...unknownLabels]
}

function createEmptyExportPayload(): ConfigExportPayload {
  return {
    version: '1.0.0',
    exported_at: new Date().toISOString(),
    app_version: '0.5.0',
    config: {},
  }
}

function getBackendSectionKeys(sectionKeys: ExportSectionKey[]): ExportSectionKey[] {
  return sectionKeys.filter(section => BACKEND_SECTION_KEYS.includes(section))
}

function getCodingPlanExport(includeApiKeys: boolean): Record<string, any> {
  try {
    const codingPlanConfigs = localStorage.getItem('codingPlanConfigs')
    if (!codingPlanConfigs) {
      return {}
    }

    const parsed = JSON.parse(codingPlanConfigs)
    if (!parsed || typeof parsed !== 'object') {
      return {}
    }

    if (!includeApiKeys) {
      Object.values(parsed).forEach((item: any) => {
        if (item && typeof item === 'object' && 'apiKey' in item) {
          item.apiKey = ''
        }
      })
    }

    return parsed
  } catch (error) {
    console.error('Failed to export coding plan configs:', error)
    return {}
  }
}

function extractCustomTeamModelConfig(config: TeamModelConfigResponse): TeamModelConfig | null {
  const customConfig: TeamModelConfig = {}
  const keys: (keyof TeamModelConfig)[] = ['provider', 'model', 'api_mode', 'temperature', 'max_tokens', 'api_key', 'api_base']

  keys.forEach(key => {
    const value = config.model_settings?.[key]
    const defaultValue = (config.global_defaults as Record<string, any> | undefined)?.[key]

    if (value === undefined || value === null || value === '') {
      return
    }

    if (value !== defaultValue || key === 'api_key' || key === 'api_base') {
      switch (key) {
        case 'temperature':
        case 'max_tokens':
          customConfig[key] = Number(value)
          break
        case 'provider':
        case 'model':
        case 'api_key':
        case 'api_base':
          customConfig[key] = String(value)
          break
        case 'api_mode':
          customConfig[key] = 'chat_completions'
          break
      }
    }
  })

  return Object.keys(customConfig).length > 0 ? customConfig : null
}

async function getAgentTeamsExport(includeApiKeys: boolean): Promise<AgentTeamsExportBlock> {
  const teams = await agentTeamsApi.list()

  const exportedTeams = await Promise.all(
    teams.map(async (team) => {
      let modelConfig: TeamModelConfig | null = null

      if (team.use_custom_model) {
        const config = await agentTeamsApi.getConfig(team.id)
        modelConfig = extractCustomTeamModelConfig(config)

        if (modelConfig && !includeApiKeys && modelConfig.api_key) {
          modelConfig = {
            ...modelConfig,
            api_key: '',
          }
        }
      }

      return {
        id: team.id,
        name: team.name,
        description: team.description,
        mode: team.mode,
        agents: team.agents,
        is_active: team.is_active,
        cross_review: team.cross_review,
        enable_skills: team.enable_skills,
        use_custom_model: team.use_custom_model,
        model_config: modelConfig,
      } satisfies ExportableAgentTeam
    }),
  )

  return { teams: exportedTeams }
}

function downloadJsonFile(data: ConfigExportPayload) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `countbot_config_${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

async function handleExport() {
  isExporting.value = true

  try {
    const selectedSections = [...exportOptions.value.sections]
    const backendSections = getBackendSectionKeys(selectedSections)

    const data = backendSections.length > 0
      ? await configAPI.export({
          include_api_keys: exportOptions.value.includeApiKeys,
          sections: backendSections.join(','),
        })
      : createEmptyExportPayload()

    if (selectedSections.includes('codingplan')) {
      data.config.codingplan = getCodingPlanExport(exportOptions.value.includeApiKeys)
    }

    if (selectedSections.includes('multiagent')) {
      data.config.multiagent = await getAgentTeamsExport(exportOptions.value.includeApiKeys)
    }

    downloadJsonFile(data)

    toast.success(
      selectedSectionLabels.value.length > 0
        ? `已导出：${selectedSectionLabels.value.join('、')}`
        : '配置导出成功',
    )
    showExportDialog.value = false
  } catch (error) {
    console.error('导出失败:', error)
    toast.error('配置导出失败')
  } finally {
    isExporting.value = false
  }
}

function triggerImport() {
  fileInput.value?.click()
}

async function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return

  try {
    const text = await file.text()
    const data = JSON.parse(text)

    if (!data?.version || !data?.config || typeof data.config !== 'object') {
      toast.error('无效的配置文件格式')
      return
    }

    importData.value = data
    showImportDialog.value = true
  } catch (error) {
    console.error('读取文件失败:', error)
    toast.error('读取配置文件失败')
  } finally {
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  }
}

function getBackendImportConfig(config: Record<string, any>): Record<string, any> {
  return Object.fromEntries(
    Object.entries(config).filter(([key]) => !CLIENT_ONLY_SECTION_KEYS.has(key as ExportSectionKey)),
  )
}

function applyCodingPlanImport(config: Record<string, any>, merge: boolean) {
  try {
    const importedConfigs = config || {}
    if (merge) {
      const existing = localStorage.getItem('codingPlanConfigs')
      const existingConfigs = existing ? JSON.parse(existing) : {}
      localStorage.setItem('codingPlanConfigs', JSON.stringify({ ...existingConfigs, ...importedConfigs }))
      return
    }

    localStorage.setItem('codingPlanConfigs', JSON.stringify(importedConfigs))
  } catch (error) {
    console.error('Failed to import coding plan configs:', error)
    throw new Error('Coding Plan 配置导入失败')
  }
}

function extractImportedTeams(rawBlock: unknown): ExportableAgentTeam[] {
  if (!rawBlock) {
    return []
  }

  if (Array.isArray(rawBlock)) {
    return rawBlock as ExportableAgentTeam[]
  }

  if (typeof rawBlock === 'object' && rawBlock !== null && Array.isArray((rawBlock as AgentTeamsExportBlock).teams)) {
    return (rawBlock as AgentTeamsExportBlock).teams
  }

  throw new Error('智能体团队配置格式无效')
}

function normalizeImportedTeam(team: ExportableAgentTeam): ExportableAgentTeam {
  const name = String(team.name || '').trim()
  if (!name) {
    throw new Error('智能体团队配置缺少团队名称')
  }

  if (!['pipeline', 'graph', 'council'].includes(team.mode)) {
    throw new Error(`智能体团队 "${name}" 的协作模式无效`)
  }

  if (!Array.isArray(team.agents)) {
    throw new Error(`智能体团队 "${name}" 的成员配置无效`)
  }

  return {
    name,
    description: team.description || '',
    mode: team.mode,
    agents: team.agents,
    is_active: team.is_active ?? true,
    cross_review: team.cross_review ?? true,
    enable_skills: team.enable_skills ?? false,
    use_custom_model: Boolean(team.use_custom_model),
    model_config: team.model_config ?? null,
  }
}

function validateDuplicateTeamNames(teams: ExportableAgentTeam[]) {
  const nameSet = new Set<string>()

  teams.forEach(team => {
    if (nameSet.has(team.name)) {
      throw new Error(`导入文件中存在重复的团队名称：${team.name}`)
    }
    nameSet.add(team.name)
  })
}

async function applyImportedTeamModelConfig(
  teamId: string,
  team: ExportableAgentTeam,
  existingTeam?: AgentTeam,
) {
  if (team.use_custom_model) {
    await agentTeamsApi.updateConfig(teamId, team.model_config ?? {})
    return
  }

  if (existingTeam?.use_custom_model) {
    await agentTeamsApi.resetConfig(teamId)
  }
}

async function applyImportedTeams(rawBlock: unknown, merge: boolean) {
  const importedTeams = extractImportedTeams(rawBlock).map(normalizeImportedTeam)
  validateDuplicateTeamNames(importedTeams)

  const existingTeams = await agentTeamsApi.list()
  const existingByName = new Map(existingTeams.map(team => [team.name, team]))
  const importedNames = new Set(importedTeams.map(team => team.name))

  for (const importedTeam of importedTeams) {
    const existing = existingByName.get(importedTeam.name)
    const payload = {
      name: importedTeam.name,
      description: importedTeam.description,
      mode: importedTeam.mode,
      agents: importedTeam.agents,
      is_active: importedTeam.is_active,
      cross_review: importedTeam.cross_review,
      enable_skills: importedTeam.enable_skills,
    }

    const savedTeam = existing
      ? await agentTeamsApi.update(existing.id, payload)
      : await agentTeamsApi.create(payload)

    await applyImportedTeamModelConfig(savedTeam.id, importedTeam, existing)
  }

  if (!merge) {
    for (const existingTeam of existingTeams) {
      if (!importedNames.has(existingTeam.name)) {
        await agentTeamsApi.delete(existingTeam.id)
      }
    }
  }

  await agentTeamsStore.loadTeams()
}

async function handleImport() {
  if (!importData.value) return

  isImporting.value = true

  try {
    const rawConfig = JSON.parse(JSON.stringify(importData.value.config || {}))
    const rawImportedSections = Object.keys(rawConfig)
    const backendConfig = getBackendImportConfig(rawConfig)

    let response: ImportConfigResponse | null = null

    if (Object.keys(backendConfig).length > 0) {
      response = await configAPI.import({
        version: importData.value.version,
        config: backendConfig,
        merge: importOptions.value.merge,
      })

      settingsStore.settings = response.settings

      if ('channels' in backendConfig) {
        channelsStore.clearPendingChanges()
        await channelsStore.fetchChannels()
        await channelsStore.fetchStatus()
      }
    }

    if ('codingplan' in rawConfig) {
      applyCodingPlanImport(rawConfig.codingplan, importOptions.value.merge)
    }

    if ('multiagent' in rawConfig) {
      await applyImportedTeams(rawConfig.multiagent, importOptions.value.merge)
    }

    const appliedSectionLabels = getAppliedSectionLabels(rawImportedSections)
    const appliedMessage = appliedSectionLabels.length > 0
      ? `已应用：${appliedSectionLabels.join('、')}`
      : '已立即应用到当前运行中'

    toast.success(appliedMessage, '配置导入成功')
    showImportDialog.value = false
    importData.value = null
  } catch (error: any) {
    console.error('导入失败:', error)
    const message = error?.response?.data?.detail || error?.message || '配置导入失败'
    toast.error(message)
  } finally {
    isImporting.value = false
  }
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString()
  } catch {
    return dateStr
  }
}
</script>
<style scoped>
@import './styles/ConfigImportExport.css';
</style>
