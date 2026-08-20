<template>
  <MultiBotChannelEditor
    :channel-id="channelId"
    :config="config"
    :create-default-account="createDefaultAccount"
    :enable-title="t('settings.channels.xiaozhi.enabled')"
    :enable-hint="t('settings.channels.xiaozhi.enableHint')"
    :disabled-warning="t('settings.channels.xiaozhi.disabledWarning')"
    :can-test="canTest"
    :testing-account-id="testingAccountId"
    @update="(nextChannelId, nextConfig) => emit('update', nextChannelId, nextConfig)"
    @test="(nextChannelId, nextConfig, accountId) => emit('test', nextChannelId, nextConfig, accountId)"
  >
    <template #fields="{ model, handleChange }">
      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.xiaozhi.endpoint') }} <span class="required">*</span></label>
        <input
          v-model="model.endpoint"
          type="text"
          :placeholder="t('settings.channels.xiaozhi.endpointPlaceholder')"
          class="config-input"
          @input="handleChange"
        />
        <p class="config-hint">
          <strong>{{ t('settings.channels.xiaozhi.endpointNoticeLabel') }}</strong>{{ t('settings.channels.xiaozhi.endpointHint') }}
          <br>{{ t('settings.channels.xiaozhi.endpointGuide') }}
        </p>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.xiaozhi.mode') }}</label>
        <div class="mode-cards">
          <div
            class="mode-card"
            :class="{ active: !model.enable_conversation }"
            @click="model.enable_conversation = false; handleChange()"
          >
            <div class="mode-card-header">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6"></polyline>
                <polyline points="8 6 2 12 8 18"></polyline>
              </svg>
              <span>{{ t('settings.channels.xiaozhi.toolModeTitle') }}</span>
              <span v-if="!model.enable_conversation" class="mode-badge">{{ t('settings.channels.xiaozhi.currentMode') }}</span>
            </div>
            <p class="mode-desc">{{ t('settings.channels.xiaozhi.toolModeDesc') }}</p>
          </div>

          <div
            class="mode-card"
            :class="{ active: model.enable_conversation }"
            @click="model.enable_conversation = true; handleChange()"
          >
            <div class="mode-card-header">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              <span>{{ t('settings.channels.xiaozhi.conversationModeTitle') }}</span>
              <span v-if="model.enable_conversation" class="mode-badge">{{ t('settings.channels.xiaozhi.currentMode') }}</span>
            </div>
            <p class="mode-desc">{{ t('settings.channels.xiaozhi.conversationModeDesc') }}</p>
          </div>
        </div>

        <div class="timeout-notice">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <span><strong>{{ t('settings.channels.xiaozhi.timeoutNoticeTitle') }}</strong>{{ t('settings.channels.xiaozhi.timeoutNotice') }}</span>
        </div>
      </div>

      <div class="config-section">
        <label class="config-label">{{ t('settings.channels.xiaozhi.allowFrom') }}</label>
        <div class="allow-list">
          <div v-for="(_, index) in model.allow_from" :key="index" class="allow-item">
            <input
              v-model="model.allow_from[index]"
              type="text"
              :placeholder="t('settings.channels.xiaozhi.userIdPlaceholder')"
              class="config-input"
              @input="handleChange"
            />
            <button type="button" class="remove-button" @click="model.allow_from.splice(index, 1); handleChange()">×</button>
          </div>
          <button type="button" class="add-button" @click="model.allow_from.push(''); handleChange()">+ {{ t('settings.channels.xiaozhi.addUser') }}</button>
        </div>
        <p class="config-hint">{{ t('settings.channels.xiaozhi.allowFromHint') }}</p>
      </div>
    </template>
  </MultiBotChannelEditor>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MultiBotChannelEditor from './MultiBotChannelEditor.vue'

interface Props {
  channelId: string
  config: Record<string, any>
  testingAccountId?: string | null
}

defineProps<Props>()
const emit = defineEmits<{
  update: [channelId: string, config: Record<string, any>]
  test: [channelId: string, config?: Record<string, any>, accountId?: string]
}>()
const { t } = useI18n()

const createDefaultAccount = () => ({
  enabled: false,
  display_name: '',
  account_id: 'default',
  endpoint: '',
  enable_conversation: false,
  allow_from: []
})

const canTest = (account: Record<string, any>) => Boolean(account.endpoint)
</script>

<style scoped>
.mode-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mode-card {
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.mode-card:hover {
  border-color: rgba(59, 130, 246, 0.26);
  background: rgba(59, 130, 246, 0.03);
}

.mode-card.active {
  border-color: rgba(59, 130, 246, 0.36);
  background: rgba(59, 130, 246, 0.05);
}

.mode-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.mode-badge {
  margin-left: auto;
  font-size: 11px;
  background: rgba(59, 130, 246, 0.12);
  color: #2563eb;
  padding: 2px 8px;
  border-radius: 10px;
}

.mode-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  padding-left: 26px;
}

.timeout-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 11px 12px;
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 251, 245, 0.98));
  border: 1px solid rgba(245, 158, 11, 0.22);
  border-radius: 10px;
  font-size: 12px;
  color: #9a3412;
  margin-top: 4px;
}

.timeout-notice svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: #f97316;
}

:root[data-theme='dark'] .mode-card {
  border-color: rgba(56, 70, 90, 0.58);
  background: linear-gradient(180deg, rgba(24, 31, 41, 0.98), rgba(18, 24, 33, 0.99));
}

:root[data-theme='dark'] .mode-card:hover,
:root[data-theme='dark'] .mode-card.active {
  border-color: rgba(121, 143, 182, 0.36);
}

:root[data-theme='dark'] .mode-card.active {
  background: linear-gradient(180deg, rgba(31, 40, 52, 0.96), rgba(23, 30, 41, 0.99));
}

:root[data-theme='dark'] .mode-badge {
  background: rgba(121, 143, 182, 0.18);
  color: #b6c6e1;
}

:root[data-theme='dark'] .timeout-notice {
  background: linear-gradient(180deg, rgba(43, 33, 24, 0.94), rgba(35, 27, 19, 0.98));
  border-color: rgba(191, 138, 82, 0.24);
  color: #cfbb9f;
}

:root[data-theme='dark'] .timeout-notice strong {
  color: #e0cfb7;
}

:root[data-theme='dark'] .timeout-notice svg {
  color: #c99258;
}

@media (max-width: 640px) {
  .mode-card {
    padding: 13px 14px;
  }

  .mode-card-header {
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .mode-badge {
    margin-left: 0;
  }

  .mode-desc {
    padding-left: 0;
  }
}
</style>
