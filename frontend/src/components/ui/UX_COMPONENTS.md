# 用户体验优化组件 (Task 7.14)

本文档介绍任务 7.14 中实现的用户体验优化组件和工具。

## 组件列表

### 7.14.1 加载状态组件

#### Skeleton (骨架屏)
用于在内容加载时显示占位符。

```vue
<template>
  <!-- 文本骨架 -->
  <Skeleton variant="text" width="80%" />
  
  <!-- 圆形骨架 (头像) -->
  <Skeleton variant="circular" width="48px" height="48px" />
  
  <!-- 矩形骨架 -->
  <Skeleton variant="rectangular" width="200px" height="100px" />
  
  <!-- 圆角矩形 -->
  <Skeleton variant="rounded" width="100%" height="200px" />
</template>

<script setup>
import { Skeleton } from '@/components/ui'
</script>
```

**Props:**
- `variant`: 'text' | 'circular' | 'rectangular' | 'rounded' (默认: 'text')
- `width`: string | number (可选)
- `height`: string | number (可选)
- `animated`: boolean (默认: true)

#### LoadingState (加载状态)
组合加载指示器和消息的高级组件。

```vue
<template>
  <!-- Spinner 加载 -->
  <LoadingState type="spinner" message="加载中..." />
  
  <!-- Skeleton 加载 -->
  <LoadingState type="skeleton" :lines="3" />
  
  <!-- 自定义 Skeleton -->
  <LoadingState type="skeleton">
    <template #skeleton>
      <Skeleton variant="circular" width="48px" height="48px" />
      <Skeleton variant="text" width="80%" />
      <Skeleton variant="text" width="60%" />
    </template>
  </LoadingState>
</template>

<script setup>
import { LoadingState, Skeleton } from '@/components/ui'
</script>
```

**Props:**
- `type`: 'spinner' | 'skeleton' (默认: 'spinner')
- `size`: 'small' | 'medium' | 'large' (默认: 'medium')
- `message`: string (可选)
- `lines`: number (默认: 3, 仅用于 skeleton)

### 7.14.3 空状态组件

#### EmptyState
用于显示空状态和引导用户操作。

```vue
<template>
  <EmptyState
    icon="inbox"
    title="暂无数据"
    description="这里还没有任何内容"
    action="创建第一个"
    @action="handleCreate"
  />
  
  <!-- 自定义插槽 -->
  <EmptyState title="自定义空状态">
    <template #icon>
      <CustomIcon />
    </template>
    <template #description>
      <p>自定义描述内容</p>
    </template>
    <template #action>
      <Button>自定义按钮</Button>
    </template>
  </EmptyState>
</template>

<script setup>
import { EmptyState, Button } from '@/components/ui'

const handleCreate = () => {
  console.log('创建新项目')
}
</script>
```

**Props:**
- `icon`: string (可选)
- `title`: string (可选)
- `description`: string (可选)
- `action`: string (可选)
- `actionVariant`: 'primary' | 'secondary' | 'outline' (默认: 'primary')
- `size`: 'small' | 'medium' | 'large' (默认: 'medium')

**Events:**
- `action`: 当点击操作按钮时触发

### 7.14.4 确认对话框

#### ConfirmDialog
用于需要用户确认的操作。

```vue
<template>
  <ConfirmDialog
    :show="showDialog"
    title="确认删除"
    message="确定要删除这个项目吗？此操作无法撤销。"
    type="danger"
    confirm-text="删除"
    confirm-variant="danger"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  />
</template>

<script setup>
import { ref } from 'vue'
import { ConfirmDialog } from '@/components/ui'

const showDialog = ref(false)

const handleConfirm = () => {
  console.log('确认')
  showDialog.value = false
}

const handleCancel = () => {
  console.log('取消')
  showDialog.value = false
}
</script>
```

**Props:**
- `show`: boolean (必需)
- `title`: string (可选)
- `message`: string (可选)
- `icon`: string (可选)
- `type`: 'danger' | 'warning' | 'info' | 'success' (默认: 'warning')
- `confirmText`: string (可选)
- `cancelText`: string (可选)
- `confirmVariant`: 'primary' | 'danger' | 'warning' (默认: 'primary')
- `loading`: boolean (默认: false)
- `size`: 'small' | 'medium' | 'large' (默认: 'small')

**Events:**
- `confirm`: 点击确认按钮时触发
- `cancel`: 点击取消按钮时触发
- `close`: 关闭对话框时触发

#### useConfirm Composable
提供编程式的确认对话框。

```vue
<script setup>
import { useConfirm } from '@/composables/useConfirm'

const { confirm, confirmDelete, confirmClear } = useConfirm()

// 通用确认
const handleAction = async () => {
  const result = await confirm({
    title: '确认操作',
    message: '确定要执行此操作吗？',
    type: 'warning'
  })
  
  if (result) {
    // 用户确认
    console.log('执行操作')
  }
}

// 删除确认
const handleDelete = async () => {
  const result = await confirmDelete('项目名称')
  if (result) {
    // 执行删除
  }
}

// 清空确认
const handleClear = async () => {
  const result = await confirmClear()
  if (result) {
    // 执行清空
  }
}
</script>
```

### 7.14.5 快捷键支持

#### useKeyboard Composable
用于注册和管理键盘快捷键。

```vue
<script setup>
import { useKeyboard, commonShortcuts } from '@/composables/useKeyboard'

// 使用预定义的快捷键
useKeyboard([
  commonShortcuts.send(() => {
    console.log('发送消息 (Ctrl/Cmd + Enter)')
  }),
  commonShortcuts.escape(() => {
    console.log('取消 (Escape)')
  }),
  commonShortcuts.search(() => {
    console.log('搜索 (Ctrl/Cmd + K)')
  })
])

// 自定义快捷键
useKeyboard([
  {
    key: 'Enter',
    ctrl: true,
    shift: true,
    handler: () => {
      console.log('Ctrl/Cmd + Shift + Enter')
    },
    description: 'Custom shortcut'
  }
])
</script>
```

**预定义快捷键:**
- `send`: Ctrl/Cmd + Enter
- `escape`: Escape
- `search`: Ctrl/Cmd + K
- `new`: Ctrl/Cmd + N
- `save`: Ctrl/Cmd + S
- `toggleSidebar`: Ctrl/Cmd + /
- `settings`: Ctrl/Cmd + ,
- `toggleTheme`: Ctrl/Cmd + Shift + D

### 7.14.6 虚拟滚动

#### VirtualScroll
用于优化长列表的渲染性能。

```vue
<template>
  <VirtualScroll
    ref="scrollRef"
    :items="items"
    :item-height="50"
    :buffer="5"
    key-field="id"
  >
    <template #default="{ item, index }">
      <div class="item">
        {{ index }}: {{ item.name }}
      </div>
    </template>
  </VirtualScroll>
</template>

<script setup>
import { ref } from 'vue'
import { VirtualScroll } from '@/components/ui'

const items = ref(Array.from({ length: 10000 }, (_, i) => ({
  id: i,
  name: `Item ${i}`
})))

const scrollRef = ref()

// 滚动到指定索引
const scrollToItem = (index) => {
  scrollRef.value?.scrollToIndex(index)
}

// 滚动到底部
const scrollToBottom = () => {
  scrollRef.value?.scrollToBottom()
}

// 滚动到顶部
const scrollToTop = () => {
  scrollRef.value?.scrollToTop()
}
</script>
```

**Props:**
- `items`: T[] (必需)
- `itemHeight`: number (必需)
- `buffer`: number (默认: 5)
- `keyField`: keyof T (默认: 'id')

**Methods:**
- `scrollToIndex(index, behavior?)`: 滚动到指定索引
- `scrollToBottom(behavior?)`: 滚动到底部
- `scrollToTop(behavior?)`: 滚动到顶部

### 7.14.7 图片懒加载

#### LazyImage
用于延迟加载图片，提升页面性能。

```vue
<template>
  <LazyImage
    src="/path/to/image.jpg"
    alt="描述"
    error-text="加载失败"
  >
    <template #placeholder>
      <Spinner />
    </template>
    <template #error>
      <div>自定义错误显示</div>
    </template>
  </LazyImage>
</template>

<script setup>
import { LazyImage, Spinner } from '@/components/ui'
</script>
```

**Props:**
- `src`: string (必需)
- `alt`: string (默认: '')
- `imageClass`: string (可选)
- `errorText`: string (可选)
- `rootMargin`: string (默认: '50px')
- `threshold`: number (默认: 0.01)

#### v-lazy-load 指令
用于原生 img 标签的懒加载。

```vue
<template>
  <!-- 简单用法 -->
  <img v-lazy-load="'/path/to/image.jpg'" alt="..." />
  
  <!-- 带占位图和错误图 -->
  <img
    v-lazy-load="{
      src: '/path/to/image.jpg',
      loading: '/loading.gif',
      error: '/error.png'
    }"
    alt="..."
  />
</template>

<script setup>
import { vLazyLoad } from '@/directives/lazyLoad'
</script>
```

### 7.14.8 防抖和节流

#### 防抖 (Debounce)

```vue
<script setup>
import { ref } from 'vue'
import { useDebounce, useDebounceFn } from '@/composables/useDebounce'

// 防抖响应式值
const input = ref('')
const debouncedInput = useDebounce(input, 300)

// 防抖函数
const handleSearch = useDebounceFn((query) => {
  console.log('搜索:', query)
}, 300)
</script>
```

#### 节流 (Throttle)

```vue
<script setup>
import { ref } from 'vue'
import { useThrottle, useThrottleFn, useRafThrottle } from '@/composables/useThrottle'

// 节流响应式值
const scrollY = ref(0)
const throttledScrollY = useThrottle(scrollY, 300)

// 节流函数
const handleScroll = useThrottleFn(() => {
  console.log('滚动事件')
}, 300)

// RAF 节流 (用于动画)
const handleMouseMove = useRafThrottle((event) => {
  console.log('鼠标移动:', event.clientX, event.clientY)
})
</script>
```

#### 性能工具函数

```typescript
import {
  debounce,
  throttle,
  rafThrottle,
  runWhenIdle,
  batch,
  memoize,
  once,
  sleep,
  retry
} from '@/utils/performance'

// 防抖
const debouncedFn = debounce(() => console.log('执行'), 300)

// 节流
const throttledFn = throttle(() => console.log('执行'), 300)

// RAF 节流
const rafFn = rafThrottle(() => console.log('动画帧'))

// 空闲时执行
runWhenIdle(() => console.log('浏览器空闲时执行'))

// 批量执行
const batchFn = batch((items) => {
  console.log('批量处理:', items)
}, 100)

// 记忆化
const memoizedFn = memoize((a, b) => a + b)

// 只执行一次
const onceFn = once(() => console.log('只执行一次'))

// 延迟
await sleep(1000)

// 重试
await retry(
  async () => {
    // 可能失败的操作
  },
  {
    maxAttempts: 3,
    delay: 1000,
    backoff: 2
  }
)
```

## 使用示例

查看 `src/examples/UXComponentsDemo.vue` 获取完整的使用示例。

## 最佳实践

1. **加载状态**: 对于快速操作使用 Spinner，对于慢速操作使用 Skeleton
2. **空状态**: 始终提供清晰的指引和操作按钮
3. **确认对话框**: 对于破坏性操作（删除、清空）使用 danger 类型
4. **快捷键**: 确保快捷键不与浏览器或系统快捷键冲突
5. **虚拟滚动**: 仅在列表项超过 100 个时使用
6. **图片懒加载**: 对于页面中的所有图片使用懒加载
7. **防抖**: 用于搜索输入、表单验证等
8. **节流**: 用于滚动、窗口调整大小等高频事件

## 无障碍支持

所有组件都包含适当的 ARIA 标签和键盘导航支持：

- 使用 `role` 和 `aria-*` 属性
- 支持键盘导航 (Tab, Enter, Escape)
- 提供屏幕阅读器友好的文本
- 适当的焦点管理

## 主题支持

所有组件都支持深色/浅色主题，使用 CSS 变量进行样式定制。
