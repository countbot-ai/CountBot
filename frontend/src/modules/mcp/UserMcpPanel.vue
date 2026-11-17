<template>
  <div class="mcp-panel">
    <div class="mcp-header">
      <div class="header-left">
        <h3 class="panel-title">{{ $t('settings.mcp.user.title') }}</h3>
        <span class="panel-desc">
          {{ $t('settings.mcp.user.description') }}
        </span>
      </div>
      <div class="header-right">
        <span class="user-mcp-limit">{{ $t('settings.mcp.user.limit', { n: state.max_servers }) }}</span>
      </div>
    </div>

    <div v-if="!state.enabled" class="mcp-disabled-hint">
      <p>{{ $t('settings.mcp.user.disabledHint') }}</p>
    </div>

    <template v-else>
      <div class="mcp-stats">
        <div class="stat-card">
          <span class="stat-value">{{ servers.length }}</span>
          <span class="stat-label">{{ $t('settings.mcp.user.configured') }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ runningCount }}</span>
          <span class="stat-label">{{ $t('settings.mcp.user.running') }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ state.tool_count }}</span>
          <span class="stat-label">{{ $t('settings.mcp.user.toolCount') }}</span>
        </div>
      </div>

      <div class="mcp-toolbar">
        <div class="toolbar-group">
          <button
            class="mcp-btn mcp-btn-primary"
            :disabled="servers.length >= state.max_servers || loading"
            @click="handleAdd"
          >
            <span class="mcp-btn-icon">+</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.user.addServer') }}</span>
          </button>
          <button class="mcp-btn" :disabled="loading" @click="refresh">
            <span class="mcp-btn-icon">↻</span>
            <span class="mcp-btn-label">{{ $t('settings.mcp.user.refresh') }}</span>
          </button>
        </div>
        <span v-if="state.stdio_allowlist.length === 0" class="user-mcp-hint">
          {{ $t('settings.mcp.user.stdioClosed') }}
        </span>
      </div>

      <div class="mcp-list">
        <div v-if="servers.length === 0 && !editingId" class="empty-hint">
          {{ $t('settings.mcp.user.empty') }}
        </div>

        <div
          v-for="(server, index) in servers"
          :key="server.id"
          class="server-card"
          :class="{ 'is-expanded': editingId === server.id }"
        >
          <div class="server-header" @click="toggleExpand(server)">
            <div class="server-header-left">
              <span class="expand-arrow" :class="{ expanded: editingId === server.id }">▶</span>
              <div class="server-info">
                <span class="server-name">{{ server.name || '(unnamed)' }}</span>
                <div class="server-meta">
                  <span class="mcp-badge" :class="'mcp-badge--' + transportOf(server)">
                    {{ transportLabel(server) }}
                  </span>
                  <span
                    class="mcp-badge"
                    :class="server.running ? 'mcp-badge--success' : 'mcp-badge--error'"
                  >
                    {{ server.running ? $t('settings.mcp.user.connected') : $t('settings.mcp.user.disconnected') }}
                  </span>
                  <span class="meta-tools">{{ server.tool_count || 0 }} tools</span>
                </div>
              </div>
            </div>
            <div class="server-header-right" @click.stop>
              <label class="mcp-checkbox">
                <input
                  type="checkbox"
                  :checked="server.enabled"
                  @change="toggleEnabled(index, ($event.target as HTMLInputElement).checked)"
                />
                <span>{{ $t('settings.mcp.user.enableLabel') }}</span>
              </label>
              <button class="mcp-btn mcp-btn-sm mcp-btn-danger" @click="handleDelete(index)">
                {{ $t('common.delete') }}
              </button>
            </div>
          </div>

          <div v-if="editingId === server.id" class="server-body">
            <McpServerEditor
              :server="draft"
              :saving="saving"
              :testing="testingId === (server.id || server.name)"
              :test-result="testResults[server.id || server.name] || null"
              :show-actions="true"
              @test="handleTest"
              @save="handleSaveEdit"
              @cancel="cancelEdit"
            />
          </div>
        </div>

        <div v-if="isNew && editingId" class="server-card is-new">
          <McpServerEditor
            :server="draft"
            :saving="saving"
            :testing="testingId === (draft?.id || draft?.name || 'draft')"
            :test-result="testResults[draft?.id || draft?.name || 'draft'] || null"
            :show-actions="true"
            @test="handleTest"
            @save="handleSaveEdit"
            @cancel="cancelEdit"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { meAPI, type MeMcpServer } from '@/api/endpoints'
import McpServerEditor from '@/modules/mcp/components/McpServerEditor.vue'
import {
  TRANSPORT_LABELS,
  cloneServer,
  createEmptyServer,
  inferTransport,
  type McpServerConfig,
  type McpServerTestResult,
} from '@/modules/mcp/types'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'

interface UserMcpServer extends McpServerConfig {
  running?: boolean
  tool_count?: number
}

const toast = useToast()
const { confirm } = useConfirm()

const loading = ref(false)
const saving = ref(false)
const state = ref({
  enabled: true,
  max_servers: 5,
  stdio_allowlist: [] as string[],
  connected: false,
  tool_count: 0,
})
const servers = ref<UserMcpServer[]>([])
const editingId = ref<string | null>(null)
const isNew = ref(false)
const draft = ref<UserMcpServer | null>(null)
const testingId = ref<string | null>(null)
const testResults = ref<Record<string, McpServerTestResult>>({})

const runningCount = computed(() => servers.value.filter((s) => s.running).length)

function normalizeServer(raw: MeMcpServer): UserMcpServer {
  const base = createEmptyServer()
  const merged = {
    ...base,
    ...raw,
    include_tools: raw.include_tools?.length ? [...raw.include_tools] : ['*'],
    exclude_tools: [...(raw.exclude_tools || [])],
    args: [...(raw.args || [])],
    env: { ...(raw.env || {}) },
    headers: { ...(raw.headers || {}) },
  } as UserMcpServer
  if (!merged.transport) {
    merged.transport = merged.command ? 'stdio' : 'streamable_http'
  }
  return merged
}

async function refresh() {
  loading.value = true
  try {
    const data = await meAPI.getMcp()
    state.value = {
      enabled: data.enabled,
      max_servers: data.max_servers,
      stdio_allowlist: data.stdio_allowlist || [],
      connected: data.connected,
      tool_count: data.tool_count,
    }
    servers.value = (data.servers || []).map(normalizeServer)
  } catch (err: any) {
    toast.error(err?.message || '加载 MCP 配置失败')
  } finally {
    loading.value = false
  }
}

function transportOf(server: McpServerConfig): string {
  return inferTransport(server) || '—'
}

function transportLabel(server: McpServerConfig): string {
  const tr = inferTransport(server)
  return TRANSPORT_LABELS[tr] || tr || '—'
}

function handleAdd() {
  if (servers.value.length >= state.value.max_servers) return
  const server = createEmptyServer()
  server.transport = state.value.stdio_allowlist.length > 0 ? 'stdio' : 'streamable_http'
  isNew.value = true
  editingId.value = '__new__'
  draft.value = server
}

function toggleExpand(server: McpServerConfig) {
  if (editingId.value === server.id) {
    cancelEdit()
    return
  }
  isNew.value = false
  editingId.value = server.id
  draft.value = cloneServer(server)
}

function cancelEdit() {
  editingId.value = null
  isNew.value = false
  draft.value = null
}

async function persist(next: McpServerConfig[]) {
  saving.value = true
  try {
    const data = await meAPI.updateMcp(next as unknown as MeMcpServer[])
    state.value = {
      enabled: data.enabled,
      max_servers: data.max_servers,
      stdio_allowlist: data.stdio_allowlist || [],
      connected: data.connected,
      tool_count: data.tool_count,
    }
    servers.value = (data.servers || []).map(normalizeServer)
    return true
  } catch (err: any) {
    toast.error(err?.message || '保存失败')
    return false
  } finally {
    saving.value = false
  }
}

async function handleSaveEdit(server: McpServerConfig) {
  if (!server.name.trim()) {
    toast.error('请填写服务器名称')
    return
  }
  if (!server.id) {
    server.id = server.name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').slice(0, 40)
  }

  const next = [...servers.value]
  const index = next.findIndex((item) => item.id === server.id)
  const normalized = normalizeServer(server as unknown as MeMcpServer)
  if (index >= 0) {
    next[index] = normalized
  } else {
    next.push(normalized)
  }

  const ok = await persist(next)
  if (ok) {
    toast.success('已保存')
    cancelEdit()
  }
}

async function toggleEnabled(index: number, enabled: boolean) {
  const next = [...servers.value]
  next[index] = { ...next[index], enabled }
  const ok = await persist(next)
  if (ok) toast.success(enabled ? '已启用' : '已停用')
}

async function handleDelete(index: number) {
  const server = servers.value[index]
  await confirm({
    title: '删除服务器',
    message: `确定删除「${server.name || server.id}」吗？`,
    type: 'danger',
    confirmText: '删除',
    confirmVariant: 'danger',
    onConfirm: async () => {
      const next = servers.value.filter((_, i) => i !== index)
      if (editingId.value === server.id) cancelEdit()
      const ok = await persist(next)
      if (ok) toast.success('已删除')
    },
  })
}

async function handleTest(server: McpServerConfig) {
  const key = server.id || server.name || 'draft'
  testingId.value = key
  try {
    const result = await meAPI.testMcpServer(server as unknown as MeMcpServer)
    testResults.value = { ...testResults.value, [key]: result }
  } catch (err: any) {
    testResults.value = {
      ...testResults.value,
      [key]: { success: false, message: err?.message || '测试失败' },
    }
  } finally {
    testingId.value = null
  }
}

onMounted(refresh)
</script>

<style>
@import './styles/mcp.css';

.user-mcp-limit,
.user-mcp-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
