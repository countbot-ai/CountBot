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
@import './styles/PersonalityEditDialog.css';
</style>
