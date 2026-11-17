<template>
  <div class="user-management">
    <div class="um-tabs co-segmented" role="tablist" aria-label="用户管理分区">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        class="co-segmented-item"
        :class="{ 'is-active': activeTab === tab.key }"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 注册与准入 -->
    <template v-if="activeTab === 'access'">
    <SettingsCard
      title="注册与准入"
      description="控制谁能注册、新账号如何生效，改动后立即保存"
      flush
    >
      <template v-if="settings">
        <SettingsRow label="启用多用户" description="关闭后仅管理员账号可用">
          <SwitchToggle
            v-model="settings.enabled"
            :width="40"
            :height="22"
            aria-label="启用多用户"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow label="开放注册" description="关闭后新账号只能由管理员手动创建；开放后任何能访问本服务的人都能注册并使用服务器资源">
          <SwitchToggle
            v-model="settings.registration_open"
            :width="40"
            :height="22"
            :disabled="!settings.enabled"
            aria-label="开放注册"
            @change="handleRegistrationChange"
          />
        </SettingsRow>
        <SettingsRow label="注册审批" description="新注册账号的准入方式">
          <select v-model="settings.approval" class="co-select form-control" @change="saveSettings">
            <option value="manual">管理员审批</option>
            <option value="auto">自动通过</option>
          </select>
        </SettingsRow>
        <p v-if="settings.registration_open" class="note is-warn">
          开放注册意味着把服务器权限共享给所有用户：任何能访问本服务的人都能注册并使用服务器上的模型、算力、文件与命令工具。
        </p>
      </template>
      <p v-else class="empty-note">正在读取策略…</p>
    </SettingsCard>

    <p v-if="settings && !settings.allow_local_admin_bypass" class="note is-warn">
      本机免登录已被部署级开关关闭。
    </p>
    </template>

    <!-- 资源共享 -->
    <template v-if="activeTab === 'resources'">
    <SettingsCard
      title="资源共享与权限"
      description="普通用户可复用的管理员资源，以及自建能力的边界"
      flush
    >
      <template v-if="settings">
        <SettingsRow label="全局模式" description="共享模式复用管理员配置，隔离模式由各用户自行维护">
          <select v-model="settings.mode" class="co-select form-control" @change="saveSettings">
            <option value="shared">共享（复用管理员资源）</option>
            <option value="isolated">隔离（用户自建）</option>
          </select>
        </SettingsRow>
        <SettingsRow label="共享 LLM 供应商" description="普通用户可使用管理员配置的模型供应商">
          <SwitchToggle
            v-model="settings.shared_providers"
            :width="40"
            :height="22"
            aria-label="共享 LLM 供应商"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow label="共享技能 / 知识库 / MCP" description="普通用户可复用管理员的技能、知识库与 MCP 配置">
          <SwitchToggle
            v-model="settings.shared_skills_wiki_mcp"
            :width="40"
            :height="22"
            aria-label="共享技能、知识库与 MCP"
            @change="saveSettings"
          />
        </SettingsRow>
        <p v-if="settings.shared_skills_wiki_mcp" class="note is-warn">
          共享 MCP 工具会以管理员配置的凭据与权限执行，请只共享可信服务。
        </p>
        <SettingsRow label="允许用户自建 MCP" description="开启后普通用户可在自己的设置里添加 MCP 服务">
          <SwitchToggle
            v-model="settings.allow_user_mcp"
            :width="40"
            :height="22"
            aria-label="允许用户自建 MCP"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow label="stdio 命令白名单" layout="block">
          <input
            v-model="stdioAllowlistText"
            class="co-input"
            placeholder="npx, uvx"
            @change="saveSettings"
          >
          <p class="note">多个命令用英文逗号分隔；留空表示禁止普通用户使用 stdio。</p>
        </SettingsRow>
      </template>
      <p v-else class="co-empty co-empty--inline">正在读取策略…</p>
    </SettingsCard>
    </template>

    <!-- 共享模型总览 -->
    <template v-if="activeTab === 'models'">
    <SettingsCard
      title="共享模型"
      description="普通用户在「设置 → 模型」里能选到的模型；在模型编辑弹窗里勾选「共享」即在此出现"
      flush
    >
      <template #actions>
        <button class="co-btn co-btn--secondary btn-compact" @click="loadSharedModels">刷新</button>
      </template>

      <p v-if="sharedModels && !sharedModels.enabled" class="notice-inline">
        当前为 {{ sharedModels.mode === 'shared' ? '共享模式但未开启共享供应商' : '隔离模式' }}，普通用户看不到这些共享模型。
      </p>

      <div v-if="sharedModels && sharedModels.items.length" class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>用户可见别名</th>
              <th>供应商 / 模型</th>
              <th>每日上限</th>
              <th>今日调用</th>
              <th>累计调用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sharedModels.items" :key="item.ref">
              <td>
                <div class="username">{{ item.alias }}</div>
                <div class="sub" v-if="item.note">{{ item.note }}</div>
              </td>
              <td class="sub">{{ item.provider_name }} / {{ item.model }}</td>
              <td>{{ item.daily_limit ? item.daily_limit + ' 次' : '不限' }}</td>
              <td>{{ usageFor(item).todayCalls }}</td>
              <td>{{ usageFor(item).totalCalls }}</td>
              <td class="ops">
                <button
                  class="btn-link is-danger"
                  :disabled="removingSharedRef === item.ref"
                  @click="removeSharedModel(item)"
                >
                  {{ removingSharedRef === item.ref ? '删除中…' : '删除' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="sharedModels" class="empty-note">还没有共享任何模型。</p>
      <p v-else class="empty-note">正在读取共享模型…</p>

      <template v-if="sharedModels && sharedModels.usage.length">
        <h4 class="usage-title">各用户用量（今日 / 累计）</h4>
        <div class="table-scroll">
          <table class="table">
            <thead>
              <tr>
                <th>用户</th>
                <th>模型</th>
                <th>今日调用</th>
                <th>累计调用</th>
                <th>今日 Token</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in sharedModels.usage" :key="`${row.owner_id}-${row.provider}-${row.model}`">
                <td>{{ row.username }}</td>
                <td class="sub">{{ row.provider }} / {{ row.model }}</td>
                <td>{{ row.today_calls }}</td>
                <td>{{ row.total_calls }}</td>
                <td>{{ row.today_tokens.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </SettingsCard>
    </template>

    <!-- 用户列表 -->
    <template v-if="activeTab === 'users'">
    <SettingsCard title="用户" :description="`共 ${total} 个账号`" flush>
      <div class="toolbar">
        <input
          v-model="query"
          class="co-input search-input"
          placeholder="搜索用户名"
          @keyup.enter="handleFilter"
        >
        <select v-model="statusFilter" class="co-select filter-select" @change="handleFilter">
          <option value="">全部状态</option>
          <option value="pending">待审批</option>
          <option value="active">正常</option>
          <option value="disabled">已禁用</option>
        </select>
        <button class="co-btn co-btn--secondary btn-compact" @click="loadUsers">刷新</button>
        <button class="co-btn co-btn--primary btn-compact" @click="showCreate = !showCreate">
          {{ showCreate ? '取消' : '新建用户' }}
        </button>
      </div>

      <div v-if="showCreate" class="create-box">
        <input v-model="createForm.username" class="co-input" placeholder="用户名（3-32 位）">
        <input v-model="createForm.password" class="co-input" type="password" placeholder="初始密码">
        <input v-model="createForm.display_name" class="co-input" placeholder="显示名称（可选）">
        <select v-model="createForm.role" class="co-select">
          <option value="user">普通用户</option>
          <option value="admin">管理员</option>
        </select>
        <select v-model="createForm.chat_mode_policy" class="co-select" :disabled="createForm.role === 'admin'">
          <option value="all">可用全部模式</option>
          <option value="chat">仅对话模式</option>
          <option value="agent">仅 Agent 模式</option>
        </select>
        <button class="co-btn co-btn--primary" :disabled="creating" @click="createUser">
          {{ creating ? '创建中…' : '创建' }}
        </button>
      </div>

      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>角色</th>
              <th>状态</th>
              <th>可用模式</th>
              <th>最后登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>
                <div class="username">{{ user.username }}</div>
                <div class="sub" v-if="user.display_name">{{ user.display_name }}</div>
              </td>
              <td>{{ user.role === 'admin' ? '管理员' : '普通用户' }}</td>
              <td>
                <div class="status-cell">
                  <span class="badge" :class="user.status">{{ statusText(user.status) }}</span>
                  <span
                    v-if="user.login_locked"
                    class="badge locked"
                    :title="`连续登录失败过多，剩余 ${formatLockRemaining(user.login_locked)}`"
                  >
                    登录锁定
                  </span>
                </div>
              </td>
              <td>
                <select
                  v-if="user.role !== 'admin'"
                  class="co-select"
                  :value="user.chat_mode_policy"
                  @change="setChatModePolicy(user, ($event.target as HTMLSelectElement).value as ChatModePolicy)"
                >
                  <option value="all">全部</option>
                  <option value="chat">仅对话</option>
                  <option value="agent">仅 Agent</option>
                </select>
                <span v-else class="sub">全部</span>
              </td>
              <td class="sub">{{ formatTime(user.last_login_at) }}</td>
              <td class="ops">
                <button v-if="user.status === 'pending'" class="btn-link" @click="setStatus(user, 'active')">
                  通过
                </button>
                <button v-if="user.status === 'pending'" class="btn-link is-danger" @click="setStatus(user, 'disabled')">
                  拒绝
                </button>
                <button v-if="user.status === 'active'" class="btn-link" @click="setStatus(user, 'disabled')">
                  禁用
                </button>
                <button v-if="user.status === 'disabled'" class="btn-link" @click="setStatus(user, 'active')">
                  启用
                </button>
                <button v-if="user.login_locked" class="btn-link" @click="unlockUser(user)">
                  解锁
                </button>
                <button class="btn-link" @click="openEditUser(user)">编辑</button>
                <button class="btn-link" @click="resetPassword(user)">重置密码</button>
                <button class="btn-link is-danger" @click="removeUser(user)">删除</button>
              </td>
            </tr>
            <tr v-if="!users.length">
              <td colspan="6" class="empty">暂无用户</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager">
        <span class="pager-info">共 {{ total }} 个用户</span>
        <div class="pager-actions">
          <button
            class="co-btn co-btn--secondary btn-compact"
            :disabled="page <= 1"
            @click="changePage(page - 1)"
          >
            上一页
          </button>
          <span class="pager-current">{{ page }} / {{ totalPages }}</span>
          <button
            class="co-btn co-btn--secondary btn-compact"
            :disabled="page >= totalPages"
            @click="changePage(page + 1)"
          >
            下一页
          </button>
        </div>
      </div>
    </SettingsCard>
    </template>

    <p v-if="message" class="toast" :class="{ error: messageIsError }">{{ message }}</p>

    <Modal
      v-model="showEdit"
      title="编辑用户"
      size="medium"
      show-footer
      confirm-text="保存"
      :confirm-loading="editing"
      @confirm="saveEditUser"
    >
      <div class="edit-form">
        <div class="edit-field">
          <label class="edit-label">用户名</label>
          <input :value="editForm.username" class="co-input" disabled>
        </div>
        <div class="edit-field">
          <label class="edit-label">显示名称</label>
          <input v-model="editForm.display_name" class="co-input" placeholder="显示名称（可选）">
        </div>
        <div class="edit-field">
          <label class="edit-label">角色</label>
          <select v-model="editForm.role" class="co-select">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
        </div>
        <div class="edit-field">
          <label class="edit-label">状态</label>
          <select v-model="editForm.status" class="co-select">
            <option value="pending">待审批</option>
            <option value="active">正常</option>
            <option value="disabled">已禁用</option>
          </select>
        </div>
        <div class="edit-field">
          <label class="edit-label">可用模式</label>
          <select
            v-model="editForm.chat_mode_policy"
            class="co-select"
            :disabled="editForm.role === 'admin'"
          >
            <option value="all">可用全部模式</option>
            <option value="chat">仅对话模式</option>
            <option value="agent">仅 Agent 模式</option>
          </select>
          <p class="edit-hint">只允许一种模式时，用户输入框不再显示模式切换。</p>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import SwitchToggle from '@/components/ui/SwitchToggle.vue'
import Modal from '@/components/ui/Modal.vue'
import { useConfirm } from '@/composables/useConfirm'
import { SettingsCard, SettingsRow } from '@/modules/settings/ui'
import {
  adminAPI,
  settingsAPI,
  type AdminUserItem,
  type ChatModePolicy,
  type SharedModelItem,
  type SharedModelsResponse,
} from '@/api/endpoints'

interface MultiuserSettings {
  enabled: boolean
  registration_open: boolean
  approval: string
  mode: string
  shared_providers: boolean
  shared_skills_wiki_mcp: boolean
  allow_user_mcp: boolean
  user_mcp_stdio_allowlist: string[]
  allow_local_admin_bypass: boolean
  max_users: number
}

const users = ref<AdminUserItem[]>([])
const total = ref(0)
const query = ref('')
const statusFilter = ref('')
const showCreate = ref(false)
const creating = ref(false)

/** 用户列表分页：与后端 page/page_size 对齐，避免一次拉全量 */
const PAGE_SIZE = 20
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

type TabKey = 'users' | 'access' | 'resources' | 'models'

/** 页面分区：策略类配置与用户列表拆开，避免长页面上下滚动 */
const TABS: { key: TabKey; label: string }[] = [
  { key: 'users', label: '用户' },
  { key: 'access', label: '注册与准入' },
  { key: 'resources', label: '资源共享' },
  { key: 'models', label: '共享模型' },
]
const activeTab = ref<TabKey>('users')
const settings = ref<MultiuserSettings | null>(null)
const sharedModels = ref<SharedModelsResponse | null>(null)
/** 正在移除共享的模型 ref，用于禁用该行按钮 */
const removingSharedRef = ref('')
const stdioAllowlistText = ref('')
const message = ref('')
const messageIsError = ref(false)
const { confirm } = useConfirm()
const showEdit = ref(false)
const editing = ref(false)

const editForm = reactive({
  id: '',
  username: '',
  display_name: '',
  role: 'user',
  status: 'active',
  chat_mode_policy: 'all' as ChatModePolicy,
})

const createForm = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'user',
  chat_mode_policy: 'all' as ChatModePolicy,
})

function notify(text: string, isError = false) {
  message.value = text
  messageIsError.value = isError
  window.setTimeout(() => (message.value = ''), 3000)
}

function statusText(status: string) {
  return { pending: '待审批', active: '正常', disabled: '已禁用' }[status] || status
}

function formatTime(value?: string) {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

async function loadUsers() {
  try {
    const data = await adminAPI.listUsers({
      q: query.value || undefined,
      status: statusFilter.value || undefined,
      page: page.value,
      page_size: PAGE_SIZE,
    })
    // 删除最后一页的最后一条后回退一页，避免停在空页
    const maxPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE))
    if (page.value > maxPage) {
      page.value = maxPage
      return loadUsers()
    }
    users.value = data.items
    total.value = data.total
  } catch (err: any) {
    notify(err?.message || '加载用户失败', true)
  }
}

/** 搜索 / 筛选 / 手动刷新都从第一页开始 */
function handleFilter() {
  page.value = 1
  void loadUsers()
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value || next === page.value) return
  page.value = next
  void loadUsers()
}

async function loadSettings() {
  try {
    const data = await adminAPI.getMultiuserSettings()
    settings.value = { ...data }
    stdioAllowlistText.value = (data.user_mcp_stdio_allowlist || []).join(', ')
  } catch (err: any) {
    notify(err?.message || '加载策略失败', true)
  }
}

async function saveSettings() {
  if (!settings.value) return
  try {
    await adminAPI.updateMultiuserSettings({
      enabled: settings.value.enabled,
      registration_open: settings.value.registration_open,
      approval: settings.value.approval,
      mode: settings.value.mode,
      shared_providers: settings.value.shared_providers,
      shared_skills_wiki_mcp: settings.value.shared_skills_wiki_mcp,
      allow_user_mcp: settings.value.allow_user_mcp,
      user_mcp_stdio_allowlist: stdioAllowlistText.value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    })
    notify('策略已保存')
  } catch (err: any) {
    notify(err?.message || '保存失败', true)
    await loadSettings()
  }
}

async function handleRegistrationChange(value: boolean) {
  if (!settings.value) return
  if (!value) {
    await saveSettings()
    return
  }

  const confirmed = await confirm({
    title: '开放注册风险确认',
    message:
      '开放注册意味着把服务器权限共享给所有用户，这会带来严重的隐私与安全风险：任何能访问本服务的人都可以创建账号，使用服务器上的模型、算力、文件与命令工具。请确认服务已限制在可信网络，或已配置访问控制。',
    type: 'warning',
    confirmText: '确认开放',
    cancelText: '取消',
    confirmVariant: 'warning',
  })
  if (!confirmed) {
    settings.value.registration_open = false
    return
  }
  await saveSettings()
}

async function createUser() {
  creating.value = true
  try {
    await adminAPI.createUser({
      username: createForm.username.trim(),
      password: createForm.password,
      display_name: createForm.display_name || undefined,
      role: createForm.role,
      status: 'active',
      chat_mode_policy: createForm.chat_mode_policy,
    })
    notify('用户已创建')
    showCreate.value = false
    createForm.username = ''
    createForm.password = ''
    createForm.display_name = ''
    createForm.role = 'user'
    createForm.chat_mode_policy = 'all'
    // 新用户按创建时间倒序排在第一页
    page.value = 1
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || '创建失败', true)
  } finally {
    creating.value = false
  }
}

async function setStatus(user: AdminUserItem, status: string) {
  try {
    await adminAPI.updateUser(user.id, { status })
    notify('状态已更新')
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || '更新失败', true)
  }
}

async function setChatModePolicy(user: AdminUserItem, policy: ChatModePolicy) {
  try {
    const updated = await adminAPI.updateUser(user.id, { chat_mode_policy: policy })
    user.chat_mode_policy = updated.chat_mode_policy
    notify('可用模式已更新')
  } catch (err: any) {
    notify(err?.message || '更新可用模式失败', true)
    await loadUsers()
  }
}

function openEditUser(user: AdminUserItem) {
  editForm.id = user.id
  editForm.username = user.username
  editForm.display_name = user.display_name || ''
  editForm.role = user.role
  editForm.status = user.status
  editForm.chat_mode_policy = user.chat_mode_policy
  showEdit.value = true
}

async function saveEditUser() {
  if (!editForm.id) return
  editing.value = true
  try {
    await adminAPI.updateUser(editForm.id, {
      display_name: editForm.display_name.trim() || undefined,
      role: editForm.role,
      status: editForm.status,
      chat_mode_policy: editForm.role === 'admin' ? 'all' : editForm.chat_mode_policy,
    })
    showEdit.value = false
    notify('用户信息已更新')
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || '保存失败', true)
  } finally {
    editing.value = false
  }
}

function formatLockRemaining(seconds: number) {
  if (!seconds || seconds <= 0) return ''
  const minutes = Math.ceil(seconds / 60)
  return minutes <= 1 ? '不到 1 分钟' : `${minutes} 分钟`
}

async function unlockUser(user: AdminUserItem) {
  try {
    const result = await adminAPI.unlockUser(user.id)
    notify(result.message || '已解除登录锁定')
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || '解锁失败', true)
  }
}

async function resetPassword(user: AdminUserItem) {
  const next = window.prompt(`为 ${user.username} 设置新密码（至少 8 位，含大小写与数字）`)
  if (!next) return
  try {
    await adminAPI.resetPassword(user.id, next)
    notify('密码已重置，该用户需重新登录')
  } catch (err: any) {
    notify(err?.message || '重置失败', true)
  }
}

async function removeUser(user: AdminUserItem) {
  if (!window.confirm(`确认删除用户 ${user.username}？该操作不可撤销。`)) return
  try {
    await adminAPI.deleteUser(user.id)
    notify('用户已删除')
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || '删除失败', true)
  }
}

/** 某个共享模型在全站的今日/累计调用合计（用量按「用户 + 模型」返回，这里做一次汇总） */
function usageFor(item: SharedModelItem): { todayCalls: number; totalCalls: number } {
  const rows = (sharedModels.value?.usage || []).filter(
    row => row.provider === item.provider && row.model === item.model,
  )
  return {
    todayCalls: rows.reduce((sum, row) => sum + row.today_calls, 0),
    totalCalls: rows.reduce((sum, row) => sum + row.total_calls, 0),
  }
}

async function loadSharedModels() {
  try {
    sharedModels.value = await adminAPI.getSharedModels()
  } catch (err: any) {
    notify(err?.message || '加载共享模型失败', true)
  }
}

/**
 * 从共享清单移除：只把模型的 shared 关掉，供应商里的模型本身保留，
 * 避免为了清理共享而误删管理员已配置的模型。
 */
async function removeSharedModel(item: SharedModelItem) {
  const confirmed = await confirm({
    title: '删除共享模型',
    message: `确认将「${item.alias}」从共享清单移除？供应商中的模型不会被删除，之后仍可重新勾选共享。`,
    type: 'warning',
    confirmText: '删除',
    confirmVariant: 'danger',
  })
  if (!confirmed) return

  removingSharedRef.value = item.ref
  try {
    await settingsAPI.updateProviderModel(item.provider, item.model, { shared: false })
    notify('已从共享清单移除')
  } catch (err: any) {
    notify(err?.message || '删除共享模型失败', true)
  } finally {
    removingSharedRef.value = ''
    // 模型可能已随供应商删除：无论成功失败都以服务端清单为准
    await loadSharedModels()
  }
}

/** 切到共享模型页或窗口重新获得焦点时刷新，避免看到供应商删除前的旧清单 */
watch(activeTab, tab => {
  if (tab === 'models') void loadSharedModels()
})

function handleWindowFocus() {
  if (activeTab.value === 'models') void loadSharedModels()
}

onMounted(async () => {
  window.addEventListener('focus', handleWindowFocus)
  await Promise.all([loadUsers(), loadSettings(), loadSharedModels()])
})

onBeforeUnmount(() => {
  window.removeEventListener('focus', handleWindowFocus)
})
</script>

<style scoped>
.user-management {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 分区标签：宽度跟随内容，不随纵向 flex 容器撑满 */
.um-tabs {
  align-self: flex-start;
  max-width: 100%;
  overflow-x: auto;
}

/* ---------- 分页 ---------- */

.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  padding: 10px var(--co-row-gutter);
  border-top: 1px solid var(--color-border-primary);
}

.pager-info {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.pager-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager-current {
  min-width: 44px;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  text-align: center;
}

/* 策略下拉占固定宽度，避免整行被拉满后控件离标签太远 */
.form-control {
  width: 240px;
}

.note {
  margin: 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-text-tertiary);
}

.note.is-warn {
  padding: 0 var(--co-row-gutter);
  color: var(--color-warning);
}

/* ---------- 编辑用户 ---------- */

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.edit-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.edit-field .co-input,
.edit-field .co-select {
  width: 100%;
}

.edit-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-tertiary);
}

.btn-compact {
  height: 26px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

/* 卡片内空态：不加外框，只做一处居中弱化文字 */
.empty-note {
  margin: 0;
  padding: 26px var(--co-row-gutter);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-align: center;
}

.notice-inline {
  margin: 10px var(--co-row-gutter) 0;
  font-size: var(--font-size-xs);
  line-height: 1.6;
  color: var(--color-warning);
}

/* ---------- 工具条 / 新建表单 ---------- */

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px var(--co-row-gutter);
  border-bottom: 1px solid var(--color-border-primary);
}

.toolbar .co-btn:last-child {
  margin-left: auto;
}

.search-input {
  width: 200px;
}

.filter-select {
  width: 132px;
}

.create-box {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
  padding: 10px var(--co-row-gutter);
  border-bottom: 1px solid var(--color-border-primary);
  background: var(--color-bg-secondary);
}

.create-box .co-btn {
  justify-self: start;
}

/* ---------- 表格 ---------- */

.table-scroll {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 520px;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.table th,
.table td {
  padding: 8px var(--co-row-gutter);
  text-align: left;
  border-bottom: 1px solid var(--color-border-primary);
}

.table tbody tr:last-child td {
  border-bottom: none;
}

.table th {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-tertiary);
  text-transform: none;
  white-space: nowrap;
}

.table td {
  color: var(--color-text-primary);
}

.usage-title {
  margin: 12px var(--co-row-gutter) 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.username {
  font-weight: var(--font-weight-medium);
}

.sub {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.empty {
  padding: 20px 0;
  text-align: center;
  color: var(--color-text-tertiary);
}

/* ---------- 状态徽标 ---------- */

.badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--color-bg-tertiary);
  font-size: 11px;
  line-height: 18px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.badge.active {
  background: var(--color-success-light);
  color: var(--color-success);
}

.badge.pending {
  background: var(--color-warning-light);
  color: var(--color-warning);
}

.badge.disabled {
  background: var(--color-error-light);
  color: var(--color-error);
}

/* 连续登录失败触发的临时锁定：与账号状态分开展示 */
.badge.locked {
  background: var(--color-warning-light);
  color: var(--color-warning);
}

.status-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
}

/* ---------- 行内操作 ---------- */

.ops {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.btn-link {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.btn-link:hover {
  color: var(--color-text-primary);
}

.btn-link.is-danger {
  color: var(--color-error);
}

.btn-link:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---------- 提示 ---------- */

.toast {
  position: sticky;
  bottom: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--color-success-light);
  color: var(--color-success);
  font-size: var(--font-size-sm);
}

.toast.error {
  background: var(--color-error-light);
  color: var(--color-error);
}

@media (max-width: 680px) {
  .form-control,
  .search-input,
  .filter-select {
    width: 100%;
  }

  .toolbar .co-btn:last-child {
    margin-left: 0;
  }
}
</style>
