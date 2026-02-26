<template>
  <div class="dialog-overlay" @click.self="$emit('cancel')">
    <div class="dialog-content">
      <div class="dialog-header">
        <h3>{{ isNew ? $t('settings.persona.createPersonality') : $t('settings.persona.editPersonality') }}</h3>
        <button class="close-btn" @click="$emit('cancel')">
          <component :is="XIcon" :size="20" />
        </button>
      </div>

      <div class="dialog-body">
        <div class="form-group">
          <label class="label">{{ $t('settings.persona.personalityId') }}</label>
          <input
            v-model="localPersonality.id"
            type="text"
            class="input"
            :placeholder="$t('settings.persona.personalityIdPlaceholder')"
            :disabled="!isNew"
            pattern="[a-z0-9_-]+"
          />
          <p class="hint">{{ $t('settings.persona.personalityIdHint') }}</p>
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.personalityName') }}</label>
          <input
            v-model="localPersonality.name"
            type="text"
            class="input"
            :placeholder="$t('settings.persona.personalityNamePlaceholder')"
          />
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.personalityDescription') }}</label>
          <textarea
            v-model="localPersonality.description"
            class="textarea"
            :placeholder="$t('settings.persona.personalityDescriptionPlaceholder')"
            rows="3"
          />
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.personalityTraits') }}</label>
          <div class="traits-input">
            <div class="trait-tags">
              <span v-for="(trait, index) in localPersonality.traits" :key="index" class="trait-tag">
                {{ trait }}
                <button @click="removeTrait(index)" class="remove-trait">
                  <component :is="XIcon" :size="12" />
                </button>
              </span>
            </div>
            <input
              v-model="newTrait"
              type="text"
              class="input"
              :placeholder="$t('settings.persona.addTraitPlaceholder')"
              @keydown.enter.prevent="addTrait"
            />
          </div>
          <p class="hint">{{ $t('settings.persona.traitsHint') }}</p>
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.speakingStyle') }}</label>
          <textarea
            v-model="localPersonality.speaking_style"
            class="textarea"
            :placeholder="$t('settings.persona.speakingStylePlaceholder')"
            rows="6"
          />
        </div>

        <div class="form-group">
          <label class="label">{{ $t('settings.persona.icon') }}</label>
          <div class="icon-selector">
            <button
              v-for="iconName in availableIcons"
              :key="iconName"
              class="icon-btn"
              :class="{ active: localPersonality.icon === iconName }"
              @click="localPersonality.icon = iconName"
            >
              <component :is="getIcon(iconName)" :size="24" />
            </button>
          </div>
        </div>
      </div>

      <div class="dialog-footer">
        <button class="btn btn-secondary" @click="$emit('cancel')">
          {{ $t('common.cancel') }}
        </button>
        <button class="btn btn-primary" @click="save" :disabled="!isValid">
          {{ $t('common.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  X as XIcon,
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
} from 'lucide-vue-next'
import type { Personality } from '@/api/personalities'

interface Props {
  personality: Personality
  isNew: boolean
}

interface Emits {
  (e: 'save', personality: Personality): void
  (e: 'cancel'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t } = useI18n()

const localPersonality = ref<Personality>({ ...props.personality })
const newTrait = ref('')

const availableIcons = [
  'CloudLightning',
  'Frown',
  'Heart',
  'Target',
  'Snowflake',
  'MessageSquare',
  'BookOpen',
  'Smile',
  'Laugh',
  'TrendingUp',
  'Gamepad2',
  'Clock',
]

const iconMap: Record<string, any> = {
  CloudLightning,
  Frown,
  Heart,
  Target,
  Snowflake,
  MessageSquare,
  BookOpen,
  Smile,
  Laugh,
  TrendingUp,
  Gamepad2,
  Clock,
}

const getIcon = (iconName: string) => iconMap[iconName] || Smile

const isValid = computed(() => {
  return (
    localPersonality.value.id &&
    localPersonality.value.name &&
    localPersonality.value.description &&
    localPersonality.value.traits.length > 0 &&
    localPersonality.value.speaking_style
  )
})

const addTrait = () => {
  if (newTrait.value.trim()) {
    localPersonality.value.traits.push(newTrait.value.trim())
    newTrait.value = ''
  }
}

const removeTrait = (index: number) => {
  localPersonality.value.traits.splice(index, 1)
}

const save = () => {
  if (isValid.value) {
    emit('save', localPersonality.value)
  }
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.dialog-content {
  background: var(--bg-primary);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.dialog-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dialog-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: 20px;
}

.label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.input,
.textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  transition: all 0.2s;
}

.input:focus,
.textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.input:disabled {
  background: var(--bg-tertiary);
  cursor: not-allowed;
}

.textarea {
  resize: vertical;
  min-height: 80px;
  line-height: 1.5;
}

.hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.traits-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trait-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 32px;
}

.trait-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: var(--primary-color);
}

.remove-trait {
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--primary-color);
  cursor: pointer;
  border-radius: 2px;
  transition: all 0.2s;
}

.remove-trait:hover {
  background: rgba(59, 130, 246, 0.2);
}

.icon-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(50px, 1fr));
  gap: 8px;
}

.icon-btn {
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn:hover {
  border-color: var(--primary-color);
  background: var(--bg-hover);
}

.icon-btn.active {
  border-color: var(--primary-color);
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary-color);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
