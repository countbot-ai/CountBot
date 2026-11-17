<template>
  <div class="shared-skills">
    <header class="head">
      <div>
        <h3 class="title">{{ $t('skills.shared.title') }}</h3>
        <p class="desc" v-if="isAdmin">
          {{ $t('skills.shared.adminDesc') }}
        </p>
        <p class="desc" v-else>
          {{ $t('skills.shared.userDesc') }}
        </p>
      </div>
      <button class="btn" :disabled="loading" @click="refresh">{{ $t('common.refresh') }}</button>
    </header>

    <div v-if="isAdmin" class="publish-box">
      <div class="publish-row">
        <select v-model="selectedName" class="input">
          <option value="">{{ $t('skills.shared.selectPlaceholder') }}</option>
          <option v-for="name in publishableSkills" :key="name" :value="name">
            {{ name }}
          </option>
        </select>
        <button class="btn primary" :disabled="!selectedName || publishing" @click="publishSkill">
          {{ publishing ? $t('skills.shared.processing') : $t('skills.shared.publish') }}
        </button>
      </div>
      <p class="hint">{{ $t('skills.shared.publishHint') }}</p>
      <p v-if="!loading && !publishableSkills.length" class="hint">
        {{ $t('skills.shared.emptyPublishable') }}
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
          <p v-if="item.reject_reason" class="sub reject">{{ $t('skills.shared.rejectReason', { reason: item.reject_reason }) }}</p>
        </div>

        <div class="skill-meta">
          <span class="meta-text">v{{ item.version }}</span>
          <span v-if="isAdmin" class="meta-text">
            {{ item.audience && item.audience.length ? $t('skills.shared.audienceUsers', { n: item.audience.length }) : $t('skills.shared.audienceAll') }}
          </span>
        </div>

        <div class="ops">
          <template v-if="isAdmin">
            <button
              v-if="item.status === 'approved'"
              class="btn danger"
              @click="revoke(item)"
            >
              {{ $t('skills.shared.revoke') }}
            </button>
            <template v-else>
              <button class="btn" @click="review(item, true)">{{ $t('skills.shared.approve') }}</button>
              <button class="btn danger" @click="review(item, false)">{{ $t('skills.shared.reject') }}</button>
            </template>
          </template>
          <button
            v-else-if="item.status === 'approved'"
            class="btn"
            :disabled="busyId === item.id"
            @click="toggleState(item)"
          >
            {{ item.enabled ? $t('skills.shared.disable') : $t('skills.shared.enable') }}
          </button>
          <span v-else class="sub">—</span>
        </div>
      </article>
    </div>

    <p v-else-if="!loading" class="hint">
      {{ isAdmin ? $t('skills.shared.emptyAdmin') : $t('skills.shared.emptyUser') }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { sharedSkillsAPI, type SharedSkillItem } from '@/api'
import { useUserStore } from '@/store/user'

const { t } = useI18n()
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
      draft: t('skills.shared.statusDraft'),
      pending: t('skills.shared.statusPending'),
      approved: t('skills.shared.statusApproved'),
      rejected: t('skills.shared.statusRejected'),
      revoked: t('skills.shared.statusRevoked'),
    }[status] || status
  )
}

async function refresh() {
  loading.value = true
  try {
    items.value = await sharedSkillsAPI.list()
  } catch (err: any) {
    notify(err?.message || t('skills.shared.loadFailed'), true)
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
    notify(t('skills.shared.publishSuccess', { name }))
    selectedName.value = ''
    await refresh()
  } catch (err: any) {
    notify(err?.message || t('skills.shared.publishFailed'), true)
  } finally {
    publishing.value = false
  }
}

async function toggleState(item: SharedSkillItem) {
  busyId.value = item.id
  try {
    await sharedSkillsAPI.setState(item.id, !item.enabled)
    notify(item.enabled ? t('skills.shared.stateOff') : t('skills.shared.stateOn'))
    await refresh()
  } catch (err: any) {
    notify(err?.message || t('skills.shared.actionFailed'), true)
  } finally {
    busyId.value = ''
  }
}

async function review(item: SharedSkillItem, approved: boolean) {
  let reason = ''
  if (!approved) {
    reason = window.prompt(t('skills.shared.rejectPrompt')) || ''
    if (!reason.trim()) return
  }
  try {
    await sharedSkillsAPI.review(item.id, approved, reason)
    notify(approved ? t('skills.shared.approved') : t('skills.shared.rejected'))
    await refresh()
  } catch (err: any) {
    notify(err?.message || t('skills.shared.actionFailed'), true)
  }
}

async function revoke(item: SharedSkillItem) {
  const reason = window.prompt(t('skills.shared.revokePrompt')) ?? ''
  try {
    await sharedSkillsAPI.revoke(item.id, reason)
    notify(t('skills.shared.revoked'))
    await refresh()
  } catch (err: any) {
    notify(err?.message || t('skills.shared.revokeFailed'), true)
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
