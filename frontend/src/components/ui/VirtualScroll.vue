<template>
  <div
    ref="containerRef"
    class="virtual-scroll"
    @scroll="handleScroll"
  >
    <div
      class="virtual-scroll-spacer"
      :style="{ height: `${totalHeight}px` }"
    >
      <div
        class="virtual-scroll-content"
        :style="{ transform: `translateY(${offsetY}px)` }"
      >
        <div
          v-for="item in visibleItems"
          :key="getItemKey(item)"
          class="virtual-scroll-item"
          :data-index="item.index"
        >
          <slot
            :item="item.data"
            :index="item.index"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts" generic="T">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

interface Props {
  items: T[]
  itemHeight: number
  buffer?: number
  keyField?: keyof T
}

const props = withDefaults(defineProps<Props>(), {
  buffer: 5,
  keyField: 'id' as any
})

const containerRef = ref<HTMLElement>()
const scrollTop = ref(0)
const containerHeight = ref(0)

// 计算总高度
const totalHeight = computed(() => props.items.length * props.itemHeight)

// 计算可见范围
const visibleRange = computed(() => {
  const start = Math.floor(scrollTop.value / props.itemHeight)
  const end = Math.ceil((scrollTop.value + containerHeight.value) / props.itemHeight)
  
  return {
    start: Math.max(0, start - props.buffer),
    end: Math.min(props.items.length, end + props.buffer)
  }
})

// 计算偏移量
const offsetY = computed(() => visibleRange.value.start * props.itemHeight)

// 可见项目
const visibleItems = computed(() => {
  const { start, end } = visibleRange.value
  return props.items.slice(start, end).map((data, i) => ({
    data,
    index: start + i
  }))
})

const handleScroll = (event: Event) => {
  const target = event.target as HTMLElement
  scrollTop.value = target.scrollTop
}

const getItemKey = (item: { data: T; index: number }) => {
  if (props.keyField && typeof item.data === 'object' && item.data !== null) {
    return (item.data as any)[props.keyField]
  }
  return item.index
}

// 滚动到指定索引
const scrollToIndex = (index: number, behavior: ScrollBehavior = 'smooth') => {
  if (!containerRef.value) return
  
  const targetScrollTop = index * props.itemHeight
  containerRef.value.scrollTo({
    top: targetScrollTop,
    behavior
  })
}

// 滚动到底部
const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
  scrollToIndex(props.items.length - 1, behavior)
}

// 滚动到顶部
const scrollToTop = (behavior: ScrollBehavior = 'smooth') => {
  scrollToIndex(0, behavior)
}

// 更新容器高度
const updateContainerHeight = () => {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight
  }
}

onMounted(() => {
  updateContainerHeight()
  window.addEventListener('resize', updateContainerHeight)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateContainerHeight)
})

// 监听 items 变化，自动滚动到底部（可选）
watch(() => props.items.length, (newLength, oldLength) => {
  if (newLength > oldLength) {
    // 如果用户已经在底部附近，自动滚动到新底部
    const isNearBottom = scrollTop.value + containerHeight.value >= totalHeight.value - props.itemHeight * 2
    if (isNearBottom) {
      setTimeout(() => scrollToBottom('auto'), 0)
    }
  }
})

defineExpose({
  scrollToIndex,
  scrollToBottom,
  scrollToTop
})
</script>

<style scoped>
.virtual-scroll {
  overflow-y: auto;
  overflow-x: hidden;
  height: 100%;
  position: relative;
}

.virtual-scroll-spacer {
  position: relative;
  width: 100%;
}

.virtual-scroll-content {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  will-change: transform;
}

.virtual-scroll-item {
  width: 100%;
}
</style>
