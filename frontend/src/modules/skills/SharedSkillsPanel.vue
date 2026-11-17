<template>
  <div class="shared-skills">
    <header class="head">
      <div>
        <h3 class="title">共享技能</h3>
        <p class="desc" v-if="isAdmin">
          共享只由管理员发起：选择技能发布为不可变快照，分发给全站或指定用户。
          之后修改原技能不会影响已分发的版本。
        </p>
        <p class="desc" v-else>
          这里显示管理员共享给你的技能。停用只影响你自己的对话，不改变其他用户的可见性。
        </p>
      </div>
      <button class="btn" :disabled="loading" @click="refresh">刷新</button>
    </header>

    <div v-if="isAdmin" class="publish-box">
      <div class="publish-row">
        <select v-model="selectedName" class="input">
          <option value="">选择要共享的技能</option>
          <option v-for="name in publishableSkills" :key="name" :value="name">
            {{ name }}
          </option>
        </select>
        <button class="btn primary" :disabled="!selectedName || publishing" @click="publishSkill">
          {{ publishing ? '处理中…' : '设为共享' }}
        </button>
      </div>
      <p class="hint">发布时会把技能目录整体复制为只读快照，普通用户随后可在技能库看到并自行启停；取消共享后立即不可见。</p>
      <p v-if="!loading && !publishableSkills.length" class="hint">
        当前没有可共享的技能。可在技能库新建技能后再共享。
      </p>
    </div>

    <p v-if="message" class="msg" :class="{ error: messageIsError }">{{ message }}</p>

    <div v-if="items.length" class="skill-list">
      <article v-for="item in items" :key="item.id" class="skill-item">
        <div class="skill-main">
          <div class="skill-title-line">
            <span class="name">{{ item.name }}</span>
            <span class="badge" :class="`is-${item.status}`">{{ statusText(item.status) }}</span>
          </div>
          <p class="sub">{{ item.description || '—' }}</p>
          <p v-if="item.reject_reason" class="sub reject">原因：{{ item.reject_reason }}</p>
        </div>

        <div class="skill-meta">
          <span class="meta-text">v{{ item.version }}</span>
          <span v-if="isAdmin" class="meta-text">
            {{ item.audience && item.audience.length ? `${item.audience.length} 个用户` : '全站' }}
          </span>
        </div>

        <div class="ops">
          <template v-if="isAdmin">
            <button
              v-if="item.status === 'approved'"
              class="btn danger"
              @click="revoke(item)"
            >
              撤回共享
            </button>
            <template v-else>
              <button class="btn" @click="review(item, true)">通过</button>
              <button class="btn danger" @click="review(item, false)">驳回</button>
            </template>
          </template>
          <button
            v-else-if="item.status === 'approved'"
            class="btn"
            :disabled="busyId === item.id"
            @click="toggleState(item)"
          >
            {{ item.enabled ? '停用' : '启用' }}
          </button>
          <span v-else class="sub">—</span>
        </div>
      </article>
    </div>

    <p v-else-if="!loading" class="hint">
      {{ isAdmin ? '暂无共享技能记录。' : '管理员还没有共享技能给你。' }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { sharedSkillsAPI, type SharedSkillItem } from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const items = ref<SharedSkillItem[]>([])
const loading = ref(false)
const message = ref('')
const messageIsError = ref(false)
const publishableSkills = ref<string[]>([])
const selectedName = ref('')
const publishing = ref(false)
const busyId = ref('')

function notify(text: string, isError = false) {
  message.value = text
  messageIsError.value = isError
  window.setTimeout(() => (message.value = ''), 3000)
}

function statusText(status: SharedSkillItem['status']): string {
  return (
    {
      draft: '草稿',
      pending: '待审核',
      approved: '已通过',
      rejected: '已驳回',
      revoked: '已撤回',
    }[status] || status
  )
}

async function refresh() {
  loading.value = true
  try {
    items.value = await sharedSkillsAPI.list()
  } catch (err: any) {
    notify(err?.message || '加载失败', true)
  } finally {
    loading.value = false
  }
}

async function loadPublishable() {
  if (!isAdmin.value) return
  try {
    publishableSkills.value = await sharedSkillsAPI.publishable()
  } catch {
    publishableSkills.value = []
  }
}

async function publishSkill() {
  const name = selectedName.value
  if (!name) return
  publishing.value = true
  try {
    await sharedSkillsAPI.publish({ name, audience: null })
    notify(`「${name}」已设为共享`)
    selectedName.value = ''
    await refresh()
  } catch (err: any) {
    notify(err?.message || '设为共享失败', true)
  } finally {
    publishing.value = false
  }
}

async function toggleState(item: SharedSkillItem) {
  busyId.value = item.id
  try {
    await sharedSkillsAPI.setState(item.id, !item.enabled)
    notify(item.enabled ? '已停用' : '已启用')
    await refresh()
  } catch (err: any) {
    notify(err?.message || '操作失败', true)
  } finally {
    busyId.value = ''
  }
}

async function review(item: SharedSkillItem, approved: boolean) {
  let reason = ''
  if (!approved) {
    reason = window.prompt('驳回原因：') || ''
    if (!reason.trim()) return
  }
  try {
    await sharedSkillsAPI.review(item.id, approved, reason)
    notify(approved ? '已通过审核' : '已驳回')
    await refresh()
  } catch (err: any) {
    notify(err?.message || '操作失败', true)
  }
}

async function revoke(item: SharedSkillItem) {
  const reason = window.prompt('撤回原因（可选）：') ?? ''
  try {
    await sharedSkillsAPI.revoke(item.id, reason)
    notify('已撤回')
    await refresh()
  } catch (err: any) {
    notify(err?.message || '撤回失败', true)
  }
}

onMounted(() => {
  void refresh()
  void loadPublishable()
})
</script>

<style scoped>
.shared-skills {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
}

.desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary, #9ca3af);
  max-width: 720px;
}

.publish-box {
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
}

.publish-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.input {
  padding: 6px 8px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  background: var(--bg-primary, #fff);
  font-size: 13px;
  min-width: 220px;
}

.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
}

.msg {
  font-size: 12px;
  color: var(--color-success, #16a34a);
}

.msg.error {
  color: var(--color-error, #dc2626);
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  background: var(--bg-primary, #fff);
}

.skill-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.skill-title-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.name {
  font-size: 13px;
  font-weight: 600;
}

.sub {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary, #9ca3af);
  word-break: break-word;
}

.sub.reject {
  color: var(--color-error, #dc2626);
}

.skill-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 2px;
}

.meta-text {
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
  white-space: nowrap;
}

.badge {
  display: inline-block;
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.6;
  white-space: nowrap;
  border: 1px solid var(--border-color, #e5e7eb);
}

.badge.is-approved {
  color: var(--color-success, #16a34a);
  border-color: var(--color-success, #16a34a);
}

.badge.is-pending {
  color: var(--color-warning, #d97706);
  border-color: var(--color-warning, #d97706);
}

.badge.is-rejected,
.badge.is-revoked {
  color: var(--color-error, #dc2626);
  border-color: var(--color-error, #dc2626);
}

.ops {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  flex-shrink: 0;
  padding-top: 1px;
}

.btn {
  padding: 4px 12px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 6px;
  background: var(--bg-primary, #fff);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.btn.primary {
  border-color: var(--color-accent, #2563eb);
  color: var(--color-accent, #2563eb);
}

.btn.danger {
  color: var(--color-error, #dc2626);
  border-color: var(--color-error, #dc2626);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .skill-item {
    flex-wrap: wrap;
  }

  .skill-main {
    flex-basis: 100%;
  }

  .skill-meta {
    padding-top: 0;
  }
}
</style>
