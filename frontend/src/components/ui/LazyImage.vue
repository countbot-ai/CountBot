<template>
  <div
    ref="elementRef"
    class="lazy-image"
    :class="{ 'is-loaded': isLoaded, 'has-error': hasError }"
  >
    <img
      v-if="isVisible && currentSrc"
      :src="currentSrc"
      :alt="alt"
      :class="imageClass"
      @load="handleLoad"
      @error="handleError"
    >
    <div
      v-else-if="!hasError"
      class="lazy-image-placeholder"
    >
      <slot name="placeholder">
        <div class="lazy-image-skeleton" />
      </slot>
    </div>
    <div
      v-if="hasError"
      class="lazy-image-error"
    >
      <slot name="error">
        <span class="error-text">{{ $t('common.imageLoadError') }}</span>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useLazyImage } from '@/composables/useLazyLoad'

interface Props {
  src: string
  alt?: string
  imageClass?: string
  rootMargin?: string
  threshold?: number
}

const props = withDefaults(defineProps<Props>(), {
  alt: '',
  imageClass: '',
  rootMargin: '50px',
  threshold: 0.01
})

const { elementRef, isVisible, isLoaded: lazyLoaded, hasError: lazyError, currentSrc } = useLazyImage(
  props.src,
  {
    rootMargin: props.rootMargin,
    threshold: props.threshold
  }
)

const isLoaded = ref(false)
const hasError = ref(false)

const handleLoad = () => {
  isLoaded.value = true
  hasError.value = false
}

const handleError = () => {
  hasError.value = true
  isLoaded.value = false
}
</script>

<style scoped>
.lazy-image {
  position: relative;
  overflow: hidden;
  background: var(--bg-secondary);
}

.lazy-image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lazy-image-skeleton {
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    var(--bg-secondary) 0%,
    var(--bg-tertiary) 50%,
    var(--bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s ease-in-out infinite;
}

@keyframes skeleton-loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.lazy-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.3s ease-in-out;
}

.lazy-image.is-loaded img {
  opacity: 1;
}

.lazy-image-error {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.error-text {
  font-size: var(--font-size-sm);
}
</style>
