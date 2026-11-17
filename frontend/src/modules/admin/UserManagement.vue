<template>
  <div class="user-management">
    <div class="um-tabs co-segmented" role="tablist" :aria-label="$t('admin.users.tabs.aria')">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        class="co-segmented-item"
        :class="{ 'is-active': activeTab === tab.key }"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="activeTab = tab.key"
      >
        {{ $t(tab.labelKey) }}
      </button>
    </div>

    <!-- 注册与准入 -->
    <template v-if="activeTab === 'access'">
    <SettingsCard
      :title="$t('admin.users.access.title')"
      :description="$t('admin.users.access.description')"
      flush
    >
      <template v-if="settings">
        <SettingsRow :label="$t('admin.users.access.enable')" :description="$t('admin.users.access.enableHint')">
          <SwitchToggle
            v-model="settings.enabled"
            :width="40"
            :height="22"
            :aria-label="$t('admin.users.access.enable')"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow :label="$t('admin.users.access.openRegistration')" :description="$t('admin.users.access.openRegistrationHint')">
          <SwitchToggle
            v-model="settings.registration_open"
            :width="40"
            :height="22"
            :disabled="!settings.enabled"
            :aria-label="$t('admin.users.access.openRegistration')"
            @change="handleRegistrationChange"
          />
        </SettingsRow>
        <SettingsRow :label="$t('admin.users.access.approval')" :description="$t('admin.users.access.approvalHint')">
          <select v-model="settings.approval" class="co-select form-control" @change="saveSettings">
            <option value="manual">{{ $t('admin.users.access.approvalManual') }}</option>
            <option value="auto">{{ $t('admin.users.access.approvalAuto') }}</option>
          </select>
        </SettingsRow>
        <p v-if="settings.registration_open" class="note is-warn">
          {{ $t('admin.users.access.openWarning') }}
        </p>
      </template>
      <p v-else class="empty-note">{{ $t('admin.users.common.loadingSettings') }}</p>
    </SettingsCard>

    <p v-if="settings && !settings.allow_local_admin_bypass" class="note is-warn">
      {{ $t('admin.users.access.bypassDisabled') }}
    </p>
    </template>

    <!-- 资源共享 -->
    <template v-if="activeTab === 'resources'">
    <SettingsCard
      :title="$t('admin.users.resources.title')"
      :description="$t('admin.users.resources.description')"
      flush
    >
      <template v-if="settings">
        <SettingsRow :label="$t('admin.users.resources.mode')" :description="$t('admin.users.resources.modeHint')">
          <select v-model="settings.mode" class="co-select form-control" @change="saveSettings">
            <option value="shared">{{ $t('admin.users.resources.modeShared') }}</option>
            <option value="isolated">{{ $t('admin.users.resources.modeIsolated') }}</option>
          </select>
        </SettingsRow>
        <SettingsRow :label="$t('admin.users.resources.sharedProviders')" :description="$t('admin.users.resources.sharedProvidersHint')">
          <SwitchToggle
            v-model="settings.shared_providers"
            :width="40"
            :height="22"
            :aria-label="$t('admin.users.resources.sharedProviders')"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow :label="$t('admin.users.resources.sharedSkills')" :description="$t('admin.users.resources.sharedSkillsHint')">
          <SwitchToggle
            v-model="settings.shared_skills_wiki_mcp"
            :width="40"
            :height="22"
            :aria-label="$t('admin.users.resources.sharedSkills')"
            @change="saveSettings"
          />
        </SettingsRow>
        <p v-if="settings.shared_skills_wiki_mcp" class="note is-warn">
          {{ $t('admin.users.resources.sharedWarning') }}
        </p>
        <SettingsRow :label="$t('admin.users.resources.allowUserMcp')" :description="$t('admin.users.resources.allowUserMcpHint')">
          <SwitchToggle
            v-model="settings.allow_user_mcp"
            :width="40"
            :height="22"
            :aria-label="$t('admin.users.resources.allowUserMcp')"
            @change="saveSettings"
          />
        </SettingsRow>
        <SettingsRow :label="$t('admin.users.resources.stdioAllowlist')" layout="block">
          <input
            v-model="stdioAllowlistText"
            class="co-input"
            placeholder="npx, uvx"
            @change="saveSettings"
          >
          <p class="note">{{ $t('admin.users.resources.stdioHint') }}</p>
        </SettingsRow>
      </template>
      <p v-else class="co-empty co-empty--inline">{{ $t('admin.users.common.loadingSettings') }}</p>
    </SettingsCard>
    </template>

    <!-- 共享模型总览 -->
    <template v-if="activeTab === 'models'">
    <SettingsCard
      :title="$t('admin.users.models.title')"
      :description="$t('admin.users.models.description')"
      flush
    >
      <template #actions>
        <button class="co-btn co-btn--secondary btn-compact" @click="loadSharedModels">{{ $t('admin.users.common.refresh') }}</button>
      </template>

      <p v-if="sharedModels && !sharedModels.enabled" class="notice-inline">
        {{ $t('admin.users.models.disabledNotice', { mode: sharedModels.mode === 'shared' ? $t('admin.users.models.modeSharedNoProviders') : $t('admin.users.models.modeIsolated') }) }}
      </p>

      <div v-if="sharedModels && sharedModels.items.length" class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>{{ $t('admin.users.models.colAlias') }}</th>
              <th>{{ $t('admin.users.models.colProviderModel') }}</th>
              <th>{{ $t('admin.users.models.colDailyLimit') }}</th>
              <th>{{ $t('admin.users.models.colTodayCalls') }}</th>
              <th>{{ $t('admin.users.models.colTotalCalls') }}</th>
              <th>{{ $t('admin.users.models.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sharedModels.items" :key="item.ref">
              <td>
                <div class="username">{{ item.alias }}</div>
                <div class="sub" v-if="item.note">{{ item.note }}</div>
              </td>
              <td class="sub">{{ item.provider_name }} / {{ item.model }}</td>
              <td>{{ item.daily_limit ? $t('admin.users.models.calls', { n: item.daily_limit }) : $t('admin.users.models.unlimited') }}</td>
              <td>{{ usageFor(item).todayCalls }}</td>
              <td>{{ usageFor(item).totalCalls }}</td>
              <td class="ops">
                <button
                  class="btn-link is-danger"
                  :disabled="removingSharedRef === item.ref"
                  @click="removeSharedModel(item)"
                >
                  {{ removingSharedRef === item.ref ? $t('admin.users.common.removing') : $t('admin.users.actions.delete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="sharedModels" class="empty-note">{{ $t('admin.users.models.empty') }}</p>
      <p v-else class="empty-note">{{ $t('admin.users.common.loadingModels') }}</p>

      <template v-if="sharedModels && sharedModels.usage.length">
        <h4 class="usage-title">{{ $t('admin.users.models.usageTitle') }}</h4>
        <div class="table-scroll">
          <table class="table">
            <thead>
              <tr>
                <th>{{ $t('admin.users.models.colUser') }}</th>
                <th>{{ $t('admin.users.models.colModel') }}</th>
                <th>{{ $t('admin.users.models.colTodayCalls') }}</th>
                <th>{{ $t('admin.users.models.colTotalCalls') }}</th>
                <th>{{ $t('admin.users.models.colTodayTokens') }}</th>
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
    <SettingsCard :title="$t('admin.users.list.title')" :description="$t('admin.users.list.count', { total })" flush>
      <div class="toolbar">
        <input
          v-model="query"
          class="co-input search-input"
          :placeholder="$t('admin.users.list.searchPlaceholder')"
          @keyup.enter="handleFilter"
        >
        <select v-model="statusFilter" class="co-select filter-select" @change="handleFilter">
          <option value="">{{ $t('admin.users.list.statusAll') }}</option>
          <option value="pending">{{ $t('admin.users.status.pending') }}</option>
          <option value="active">{{ $t('admin.users.status.active') }}</option>
          <option value="disabled">{{ $t('admin.users.status.disabled') }}</option>
        </select>
        <button class="co-btn co-btn--secondary btn-compact" @click="loadUsers">{{ $t('admin.users.common.refresh') }}</button>
        <button class="co-btn co-btn--primary btn-compact" @click="showCreate = !showCreate">
          {{ showCreate ? $t('common.cancel') : $t('admin.users.list.create') }}
        </button>
      </div>

      <div v-if="showCreate" class="create-box">
        <input v-model="createForm.username" class="co-input" :placeholder="$t('admin.users.list.createUsername')">
        <input v-model="createForm.password" class="co-input" type="password" :placeholder="$t('admin.users.list.createPassword')">
        <input v-model="createForm.display_name" class="co-input" :placeholder="$t('admin.users.list.createDisplayName')">
        <select v-model="createForm.role" class="co-select">
          <option value="user">{{ $t('admin.users.roles.user') }}</option>
          <option value="admin">{{ $t('admin.users.roles.admin') }}</option>
        </select>
        <select v-model="createForm.chat_mode_policy" class="co-select" :disabled="createForm.role === 'admin'">
          <option value="all">{{ $t('admin.users.policy.all') }}</option>
          <option value="chat">{{ $t('admin.users.policy.chat') }}</option>
          <option value="agent">{{ $t('admin.users.policy.agent') }}</option>
        </select>
        <button class="co-btn co-btn--primary" :disabled="creating" @click="createUser">
          {{ creating ? $t('admin.users.list.creating') : $t('admin.users.list.createSubmit') }}
        </button>
      </div>

      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>{{ $t('admin.users.cols.username') }}</th>
              <th>{{ $t('admin.users.cols.role') }}</th>
              <th>{{ $t('admin.users.cols.status') }}</th>
              <th>{{ $t('admin.users.cols.policy') }}</th>
              <th>{{ $t('admin.users.cols.lastLogin') }}</th>
              <th>{{ $t('admin.users.models.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>
                <div class="username">{{ user.username }}</div>
                <div class="sub" v-if="user.display_name">{{ user.display_name }}</div>
              </td>
              <td>{{ user.role === 'admin' ? $t('admin.users.roles.admin') : $t('admin.users.roles.user') }}</td>
              <td>
                <div class="status-cell">
                  <span class="badge" :class="user.status">{{ statusText(user.status) }}</span>
                  <span
                    v-if="user.login_locked"
                    class="badge locked"
                    :title="$t('admin.users.list.lockedTitle', { time: formatLockRemaining(user.login_locked) })"
                  >
                    {{ $t('admin.users.list.lockedBadge') }}
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
                  <option value="all">{{ $t('admin.users.policy.allShort') }}</option>
                  <option value="chat">{{ $t('admin.users.policy.chatShort') }}</option>
                  <option value="agent">{{ $t('admin.users.policy.agentShort') }}</option>
                </select>
                <span v-else class="sub">{{ $t('admin.users.policy.allShort') }}</span>
              </td>
              <td class="sub">{{ formatTime(user.last_login_at) }}</td>
              <td class="ops">
                <Tooltip v-if="user.status === 'pending'" :content="$t('admin.users.actions.pass')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.pass')" @click="setStatus(user, 'active')">
                    <Check :size="16" />
                  </button>
                </Tooltip>
                <Tooltip v-if="user.status === 'pending'" :content="$t('admin.users.actions.reject')">
                  <button class="icon-btn is-danger" :aria-label="$t('admin.users.actions.reject')" @click="setStatus(user, 'disabled')">
                    <XCircle :size="16" />
                  </button>
                </Tooltip>
                <Tooltip v-if="user.status === 'active'" :content="$t('admin.users.actions.disable')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.disable')" @click="setStatus(user, 'disabled')">
                    <Ban :size="16" />
                  </button>
                </Tooltip>
                <Tooltip v-if="user.status === 'disabled'" :content="$t('admin.users.actions.enable')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.enable')" @click="setStatus(user, 'active')">
                    <Check :size="16" />
                  </button>
                </Tooltip>
                <Tooltip v-if="user.login_locked" :content="$t('admin.users.actions.unlock')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.unlock')" @click="unlockUser(user)">
                    <LockKeyhole :size="16" />
                  </button>
                </Tooltip>
                <Tooltip :content="$t('admin.users.actions.edit')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.edit')" @click="openEditUser(user)">
                    <Pencil :size="16" />
                  </button>
                </Tooltip>
                <Tooltip :content="$t('admin.users.actions.resetPassword')">
                  <button class="icon-btn" :aria-label="$t('admin.users.actions.resetPassword')" @click="resetPassword(user)">
                    <KeyRound :size="16" />
                  </button>
                </Tooltip>
                <Tooltip :content="$t('admin.users.actions.delete')">
                  <button class="icon-btn is-danger" :aria-label="$t('admin.users.actions.delete')" @click="removeUser(user)">
                    <Trash2 :size="16" />
                  </button>
                </Tooltip>
              </td>
            </tr>
            <tr v-if="!users.length">
              <td colspan="6" class="empty">{{ $t('admin.users.list.empty') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager">
        <span class="pager-info">{{ $t('admin.users.list.total', { total }) }}</span>
        <div class="pager-actions">
          <button
            class="co-btn co-btn--secondary btn-compact"
            :disabled="page <= 1"
            @click="changePage(page - 1)"
          >
            {{ $t('admin.users.list.prev') }}
          </button>
          <span class="pager-current">{{ page }} / {{ totalPages }}</span>
          <button
            class="co-btn co-btn--secondary btn-compact"
            :disabled="page >= totalPages"
            @click="changePage(page + 1)"
          >
            {{ $t('admin.users.list.next') }}
          </button>
        </div>
      </div>
    </SettingsCard>
    </template>

    <p v-if="message" class="toast" :class="{ error: messageIsError }">{{ message }}</p>

    <Modal
      v-model="showEdit"
      :title="$t('admin.users.edit.title')"
      size="medium"
      show-footer
      :confirm-text="$t('common.save')"
      :confirm-loading="editing"
      @confirm="saveEditUser"
    >
      <div class="edit-form">
        <div class="edit-field">
          <label class="edit-label">{{ $t('admin.users.edit.username') }}</label>
          <input :value="editForm.username" class="co-input" disabled>
        </div>
        <div class="edit-field">
          <label class="edit-label">{{ $t('admin.users.edit.displayName') }}</label>
          <input v-model="editForm.display_name" class="co-input" :placeholder="$t('admin.users.list.createDisplayName')">
        </div>
        <div class="edit-field">
          <label class="edit-label">{{ $t('admin.users.edit.role') }}</label>
          <select v-model="editForm.role" class="co-select">
            <option value="user">{{ $t('admin.users.roles.user') }}</option>
            <option value="admin">{{ $t('admin.users.roles.admin') }}</option>
          </select>
        </div>
        <div class="edit-field">
          <label class="edit-label">{{ $t('admin.users.edit.status') }}</label>
          <select v-model="editForm.status" class="co-select">
            <option value="pending">{{ $t('admin.users.status.pending') }}</option>
            <option value="active">{{ $t('admin.users.status.active') }}</option>
            <option value="disabled">{{ $t('admin.users.status.disabled') }}</option>
          </select>
        </div>
        <div class="edit-field">
          <label class="edit-label">{{ $t('admin.users.edit.policy') }}</label>
          <select
            v-model="editForm.chat_mode_policy"
            class="co-select"
            :disabled="editForm.role === 'admin'"
          >
            <option value="all">{{ $t('admin.users.policy.all') }}</option>
            <option value="chat">{{ $t('admin.users.policy.chat') }}</option>
            <option value="agent">{{ $t('admin.users.policy.agent') }}</option>
          </select>
          <p class="edit-hint">{{ $t('admin.users.edit.hint') }}</p>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, Check, KeyRound, LockKeyhole, Pencil, Trash2, XCircle } from 'lucide-vue-next'
import Tooltip from '@/components/ui/Tooltip.vue'
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

const { t } = useI18n()

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
const TABS: { key: TabKey; labelKey: string }[] = [
  { key: 'users', labelKey: 'admin.users.tabs.users' },
  { key: 'access', labelKey: 'admin.users.tabs.access' },
  { key: 'resources', labelKey: 'admin.users.tabs.resources' },
  { key: 'models', labelKey: 'admin.users.tabs.models' },
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
  return { pending: t('admin.users.status.pending'), active: t('admin.users.status.active'), disabled: t('admin.users.status.disabled') }[status] || status
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
    notify(err?.message || t('admin.users.messages.loadUsersFailed'), true)
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
    notify(err?.message || t('admin.users.messages.loadSettingsFailed'), true)
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
    notify(t('admin.users.messages.settingsSaved'))
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.saveFailed'), true)
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
    title: t('admin.users.confirm.openRegistrationTitle'),
    message: t('admin.users.confirm.openRegistrationMessage'),
    type: 'warning',
    confirmText: t('admin.users.confirm.openRegistrationConfirm'),
    cancelText: t('common.cancel'),
    confirmVariant: 'primary',
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
    notify(t('admin.users.messages.created'))
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
    notify(err?.message || t('admin.users.messages.createFailed'), true)
  } finally {
    creating.value = false
  }
}

async function setStatus(user: AdminUserItem, status: string) {
  try {
    await adminAPI.updateUser(user.id, { status })
    notify(t('admin.users.messages.statusUpdated'))
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.updateFailed'), true)
  }
}

async function setChatModePolicy(user: AdminUserItem, policy: ChatModePolicy) {
  try {
    const updated = await adminAPI.updateUser(user.id, { chat_mode_policy: policy })
    user.chat_mode_policy = updated.chat_mode_policy
    notify(t('admin.users.messages.policyUpdated'))
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.policyUpdateFailed'), true)
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
    notify(t('admin.users.messages.userUpdated'))
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.saveFailed'), true)
  } finally {
    editing.value = false
  }
}

function formatLockRemaining(seconds: number) {
  if (!seconds || seconds <= 0) return ''
  const minutes = Math.ceil(seconds / 60)
  return minutes <= 1 ? t('admin.users.messages.lessThanMinute') : t('admin.users.messages.minutes', { n: minutes })
}

async function unlockUser(user: AdminUserItem) {
  try {
    const result = await adminAPI.unlockUser(user.id)
    notify(result.message || t('admin.users.messages.unlocked'))
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.unlockFailed'), true)
  }
}

async function resetPassword(user: AdminUserItem) {
  const next = window.prompt(t('admin.users.messages.resetPrompt', { name: user.username }))
  if (!next) return
  try {
    await adminAPI.resetPassword(user.id, next)
    notify(t('admin.users.messages.resetSuccess'))
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.resetFailed'), true)
  }
}

async function removeUser(user: AdminUserItem) {
  if (!window.confirm(t('admin.users.messages.deleteConfirm', { name: user.username }))) return
  try {
    await adminAPI.deleteUser(user.id)
    notify(t('admin.users.messages.deleted'))
    await loadUsers()
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.deleteFailed'), true)
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
    notify(err?.message || t('admin.users.messages.sharedLoadFailed'), true)
  }
}

/**
 * 从共享清单移除：只把模型的 shared 关掉，供应商里的模型本身保留，
 * 避免为了清理共享而误删管理员已配置的模型。
 */
async function removeSharedModel(item: SharedModelItem) {
  const confirmed = await confirm({
    title: t('admin.users.confirm.removeSharedTitle'),
    message: t('admin.users.confirm.removeSharedMessage', { name: item.alias }),
    type: 'warning',
    confirmText: t('admin.users.confirm.removeSharedConfirm'),
    confirmVariant: 'danger',
  })
  if (!confirmed) return

  removingSharedRef.value = item.ref
  try {
    await settingsAPI.updateProviderModel(item.provider, item.model, { shared: false })
    notify(t('admin.users.messages.sharedRemoved'))
  } catch (err: any) {
    notify(err?.message || t('admin.users.messages.sharedRemoveFailed'), true)
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
  flex-wrap: nowrap;
  align-items: center;
  gap: 2px;
}

.ops .icon-btn {
  width: 30px;
  height: 30px;
}

.ops .icon-btn.is-danger {
  color: var(--color-error);
}

.ops .icon-btn.is-danger:hover {
  color: var(--color-error);
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
