<template>
  <div class="mcp-panel">
    <!-- Header -->
    <div class="mcp-header">
      <div class="header-left">
        <h3 class="panel-title">{{ $t('settings.mcp.title') }}</h3>
        <span class="panel-desc">{{ $t('settings.mcp.description') }}</span>
      </div>
      <div class="header-right">
        <label class="switch-label">
          <span class="switch-text">{{ enabled ? $t('settings.mcp.enabled') : $t('settings.mcp.disabled') }}</span>
          <button
            class="switch-btn"
            :class="{ active: enabled }"
            @click="handleToggle"
            :title="enabled ? $t('settings.mcp.disableMcp') : $t('settings.mcp.enableMcp')"
          >
            <span class="switch-dot" />
          </button>
        </label>
      </div>
    </div>

    <!-- Disabled State -->
    <div v-if="!enabled" class="mcp-disabled-hint">
      <p>{{ $t('settings.mcp.disabledHint') }}</p>
    </div>

    <!-- Enabled State -->
    <template v-else>
      <!-- Stats -->
      <div class="mcp-stats">
        <div class="stat-card">
          <span class="stat-value">{{ summary.total_servers }}</span>
          <span class="stat-label">{{ $t('settings.mcp.totalServers') }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ summary.enabled_servers }}</span>
          <span class="stat-label">{{ $t('settings.mcp.enabledServers') }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ summary.connected_servers }}</span>
          <span class="stat-label">{{ $t('settings.mcp.connectedServers') }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ summary.mcp_tool_count }}</span>
          <span class="stat-label">{{ $t('settings.mcp.toolCount') }}</span>
        </div>
      </div>

      <!-- Toolbar -->
      <div class="mcp-toolbar">
        <div class="toolbar-group">
          <button class="mcp-btn mcp-btn-primary" @click="handleAdd">
            <span class="mcp-btn-icon">+</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.addServer') }}</span>
          </button>
          <button class="mcp-btn" @click="handleRefresh" :disabled="loading">
            <span class="mcp-btn-icon">↻</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.refresh') }}</span>
          </button>
          <button class="mcp-btn" @click="handleReconnectAll">
            <span class="mcp-btn-icon">↺</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.reconnectAll') }}</span>
          </button>
          <button class="mcp-btn" @click="handleImport">
            <span class="mcp-btn-icon">↓</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.importConfig') }}</span>
          </button>
          <button class="mcp-btn" @click="handleExport">
            <span class="mcp-btn-icon">↑</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.exportConfig') }}</span>
          </button>
        </div>
      </div>

      <!-- Server List -->
      <div class="mcp-list">
        <div v-if="registry.servers.length === 0 && !editingServerId" class="empty-hint">
          {{ $t('settings.mcp.noServers') }}
        </div>

        <!-- Existing Servers -->
        <div
          v-for="(server, index) in registry.servers"
          :key="server.id"
          class="server-card"
          :class="{ 'is-expanded': editingServerId === server.id }"
        >
          <!-- Server Header (always visible, click to toggle) -->
          <div class="server-header" @click="handleToggleExpand(server)">
            <div class="server-header-left">
              <span class="expand-arrow" :class="{ expanded: editingServerId === server.id }">▶</span>
              <div class="server-info">
                <span class="server-name">{{ server.name || '(unnamed)' }}</span>
                <div class="server-meta">
                  <span class="mcp-badge" :class="'mcp-badge--' + getTransport(server)">
                    {{ getTransportLabel(server) }}
                  </span>
                  <span v-if="getStatus(server.id)" class="mcp-badge" :class="getStatus(server.id)?.running ? 'mcp-badge--success' : 'mcp-badge--error'">
                    {{ getStatus(server.id)?.running ? $t('settings.mcp.statusConnected') : $t('settings.mcp.statusDisconnected') }}
                  </span>
                  <span
                    v-if="getStatus(server.id)?.tool_count != null"
                    class="meta-tools"
                    @click.stop="showToolsPopup(server)"
                    :title="$t('settings.mcp.viewTools')"
                  >
                    {{ getStatus(server.id)?.tool_count }} tools
                  </span>
                </div>
              </div>
            </div>
            <div class="server-header-right" @click.stop>
              <button
                v-if="getStatus(server.id)?.running"
                class="mcp-btn mcp-btn-sm"
                @click="handleStopServer(server)"
              >{{ $t('settings.mcp.stopServer') }}</button>
              <button
                v-else
                class="mcp-btn mcp-btn-sm mcp-btn-success"
                @click="handleStartServer(server)"
              >{{ $t('settings.mcp.startServer') }}</button>
              <button class="mcp-btn mcp-btn-sm" @click="handleServerStatus(server)">{{ $t('settings.mcp.serverStatus') }}</button>
              <button class="mcp-btn mcp-btn-sm mcp-btn-danger" @click="handleDelete(index)">{{ $t('settings.mcp.deleteServer') }}</button>
            </div>
          </div>

          <!-- Server Editor (expandable) -->
          <div v-if="editingServerId === server.id" class="server-body">
            <McpServerEditor
              :server="editingDraft"
              :saving="saving"
              :testing="testingServerId === server.id"
              :test-result="testResults[server.id || '']"
              :show-actions="true"
              @test="handleTestServer"
              @save="handleSaveEdit"
              @cancel="handleCancelEdit"
            />
          </div>
        </div>

        <!-- New Server Editor -->
        <div v-if="isNewServer && editingServerId" class="server-card is-new">
          <McpServerEditor
            :server="editingDraft"
            :saving="saving"
            :testing="testingServerId === editingServerId"
            :test-result="testResults[editingServerId || '']"
            :show-actions="true"
            @test="handleTestServer"
            @save="handleSaveEdit"
            @cancel="handleCancelEdit"
          />
        </div>
      </div>
    </template>

    <!-- Tools Modal -->
    <div v-if="showToolsModal" class="mcp-modal-overlay" @click.self="closeToolsModal">
      <div class="mcp-modal">
        <div class="mcp-modal-header">
          <h4 class="mcp-modal-title">
            {{ toolsModalServer?.name || toolsModalServer?.id }} — {{ $t('settings.mcp.toolsList') }}
          </h4>
          <button class="mcp-modal-close" @click="closeToolsModal">×</button>
        </div>
        <div class="mcp-modal-body">
          <div v-if="toolsModalList.length === 0" class="empty-hint">
            {{ $t('settings.mcp.noTools') }}
          </div>
          <div v-else class="mcp-tools-list">
            <div v-for="tool in toolsModalList" :key="tool" class="mcp-tool-item">
              {{ tool }}
            </div>
          </div>
        </div>
        <div class="mcp-modal-footer">
          <button class="mcp-btn" @click="closeToolsModal">{{ $t('common.close') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMcp } from '@/modules/mcp/composables/useMcp'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import McpServerEditor from '@/modules/mcp/components/McpServerEditor.vue'
import type { McpServerConfig } from '@/modules/mcp/types'
import { TRANSPORT_LABELS, inferTransport } from '@/modules/mcp/types'

const { t } = useI18n()
const toast = useToast()
const {
  loading,
  saving,
  enabled,
  overview,
  registry,
  testResults,
  summary,
  serverStatusMap,
  editingServerId,
  editingDraft,
  isNewServer,
  refreshAll,
  toggleMcp,
  saveRegistry,
  testServer,
  addServer,
  startEdit,
  cancelEdit,
  commitEditLocally,
  removeServer,
  importConfig,
  exportConfig,
  reconnect,
  startServer,
  stopServer,
  getServerStatus,
} = useMcp()

const testingServerId = ref<string | null>(null)

function getTransport(server: McpServerConfig): string {
  return inferTransport(server) || '—'
}

function getTransportLabel(server: McpServerConfig): string {
  const tr = inferTransport(server)
  return TRANSPORT_LABELS[tr] || tr || '—'
}

function getStatus(serverId: string) {
  return serverStatusMap.value[serverId] || null
}

async function handleToggle() {
  const targetEnabled = !enabled.value
  await toggleMcp(targetEnabled)
  if (targetEnabled) {
    await refreshAll()
  } else {
    overview.value = null
    registry.value = { version: 1, servers: [] }
    testResults.value = {}
  }
}

async function handleRefresh() {
  await refreshAll()
  toast.success(t('settings.mcp.refreshSuccess'))
}

function handleAdd() {
  addServer()
}

function handleToggleExpand(server: McpServerConfig) {
  if (editingServerId.value === server.id) {
    cancelEdit()
  } else {
    startEdit(server)
  }
}

function handleEdit(server: McpServerConfig) {
  startEdit(server)
}

async function handleSaveEdit(server: McpServerConfig) {
  commitEditLocally()
  try {
    await saveRegistry(registry.value)
    await refreshAll()
    toast.success(t('settings.mcp.saveSuccess'))
  } catch {
    toast.error(t('settings.mcp.saveError'))
  }
}

function handleCancelEdit() {
  cancelEdit()
}

function handleDelete(index: number) {
  if (!confirm(t('settings.mcp.deleteConfirm'))) return
  const s = registry.value.servers[index]
  if (editingServerId.value === s.id) {
    cancelEdit()
  }
  registry.value.servers.splice(index, 1)
  saveRegistry(registry.value).then(() => refreshAll()).catch(() => toast.error(t('settings.mcp.saveError')))
}

async function handleTestServer(server: McpServerConfig) {
  testingServerId.value = server.id || server.name || null
  await testServer(server)
  testingServerId.value = null
}

async function handleImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const text = await file.text()
    const result = await importConfig(text, true)
    if (result.success) {
      toast.success(t('settings.mcp.importSuccess', { count: result.imported }))
    } else {
      toast.error(result.message || t('settings.mcp.importError'))
    }
  }
  input.click()
}

async function handleExport() {
  const json = await exportConfig()
  if (!json) {
    toast.error(t('settings.mcp.exportError'))
    return
  }
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'mcp-servers.json'
  a.click()
  URL.revokeObjectURL(url)
  toast.success(t('settings.mcp.exportSuccess'))
}

async function handleReconnectAll() {
  const result = await reconnect()
  if (result.success) {
    await refreshAll()
    toast.success(t('settings.mcp.reconnectSuccess'))
  } else {
    toast.error(t('settings.mcp.reconnectError'))
  }
}

async function handleStartServer(server: McpServerConfig) {
  const id = server.id || server.name || ''
  if (!id) return
  const result = await startServer(id)
  if (result.success) {
    await refreshAll()
    toast.success(t('settings.mcp.startSuccess'))
  } else {
    toast.error(result.message || t('settings.mcp.startError'))
  }
}

async function handleStopServer(server: McpServerConfig) {
  const id = server.id || server.name || ''
  if (!id) return
  const result = await stopServer(id)
  if (result.success) {
    await refreshAll()
    toast.success(t('settings.mcp.stopSuccess'))
  } else {
    toast.error(result.message || t('settings.mcp.stopError'))
  }
}

async function handleServerStatus(server: McpServerConfig) {
  const id = server.id || server.name || ''
  if (!id) return
  const result = await getServerStatus(id)
  if (result.success) {
    toolsModalServer.value = server
    toolsModalList.value = result.tools || []
    showToolsModal.value = true
  } else {
    toast.error(result.message || t('settings.mcp.statusError'))
  }
}

const showToolsModal = ref(false)
const toolsModalServer = ref<McpServerConfig | null>(null)
const toolsModalList = ref<string[]>([])

function showToolsPopup(server: McpServerConfig) {
  const status = getStatus(server.id)
  if (!status || !status.tools || status.tools.length === 0) {
    toast.info(t('settings.mcp.noToolsAvailable'))
    return
  }
  toolsModalServer.value = server
  toolsModalList.value = status.tools
  showToolsModal.value = true
}

function closeToolsModal() {
  showToolsModal.value = false
  toolsModalServer.value = null
  toolsModalList.value = []
}

onMounted(() => {
  refreshAll()
})
</script>

<style>
@import './styles/mcp.css';

.mcp-tools-trigger {
  cursor: pointer;
  text-decoration: underline;
  text-decoration-style: dashed;
  text-underline-offset: 2px;
}

.mcp-tools-trigger:hover {
  color: var(--mcp-primary);
}

.mcp-btn-success {
  background: var(--mcp-success-bg);
  color: var(--mcp-success);
  border-color: rgba(34, 197, 94, 0.2);
}

.mcp-btn-success:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.15);
  border-color: var(--mcp-success);
}
</style>
