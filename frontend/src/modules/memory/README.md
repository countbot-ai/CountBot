# Memory Module - 记忆系统模块

记忆系统模块提供长期记忆和每日笔记功能，支持 Markdown 格式，实时预览和搜索。

## 功能特性

### 1. 长期记忆 (Long-term Memory)
- 存储重要的长期信息
- 支持 Markdown 格式
- 实时预览
- 编辑和保存

### 2. 每日笔记 (Daily Notes)
- 按日期组织的笔记
- 日期选择器
- 支持 Markdown 格式
- 实时预览

### 3. 记忆搜索 (Memory Search)
- 全文搜索
- 搜索长期记忆和每日笔记
- 高亮显示匹配结果
- 快速跳转到查看/编辑

## 组件结构

```
memory/
├── MemoryPanel.vue      # 主面板，整合所有功能
├── MemoryViewer.vue     # 记忆查看器
├── MemoryEditor.vue     # 记忆编辑器（支持 Markdown）
├── MemorySearch.vue     # 记忆搜索
├── index.ts             # 导出文件
└── README.md            # 本文档
```

## 使用方法

### 在路由中使用

```typescript
import { MemoryPanel } from '@/modules/memory'

const routes = [
  {
    path: '/memory',
    component: MemoryPanel
  }
]
```

### 在组件中使用

```vue
<template>
  <MemoryPanel ref="memoryPanelRef" />
</template>

<script setup>
import { ref } from 'vue'
import { MemoryPanel } from '@/modules/memory'

const memoryPanelRef = ref(null)

// 切换到搜索模式
const switchToSearch = () => {
  memoryPanelRef.value?.switchToSearch()
}

// 切换到查看模式
const switchToView = () => {
  memoryPanelRef.value?.switchToView()
}
</script>
```

## API 集成

### Store (Pinia)

```typescript
import { useMemoryStore } from '@/store/memory'

const memoryStore = useMemoryStore()

// 加载长期记忆
await memoryStore.loadLongTermMemory()

// 保存长期记忆
await memoryStore.saveLongTermMemory(content)

// 加载每日笔记
await memoryStore.loadDailyNote('2024-01-01')

// 保存每日笔记
await memoryStore.saveDailyNote('2024-01-01', content)

// 搜索记忆
const results = memoryStore.searchMemory('关键词')
```

### API 端点

```typescript
import { memoryAPI } from '@/api/endpoints'

// GET /api/memory/long-term
const response = await memoryAPI.getLongTerm()

// PUT /api/memory/long-term
await memoryAPI.updateLongTerm({ content: '...' })

// GET /api/memory/daily/:date
const dailyResponse = await memoryAPI.getDaily('2024-01-01')

// PUT /api/memory/daily/:date
await memoryAPI.updateDaily('2024-01-01', { content: '...' })
```

## 国际化

记忆模块支持中英文双语：

```json
{
  "memory": {
    "title": "记忆系统",
    "longTerm": "长期记忆",
    "daily": "每日笔记",
    "search": "搜索记忆",
    ...
  }
}
```

## 样式定制

所有组件使用 CSS 变量，可以通过主题系统自定义：

```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --text-primary: #0f172a;
  --primary: #2563eb;
  --border-color: #e2e8f0;
  ...
}
```

## Markdown 支持

编辑器支持以下 Markdown 语法：

- **粗体** (`**text**`)
- *斜体* (`*text*`)
- `代码` (`` `code` ``)
- 代码块 (` ```code``` `)
- 标题 (`## Heading`)
- 列表 (`- item`)
- 引用 (`> quote`)
- 表格
- 链接
- 图片

## 快捷键

- `Ctrl/Cmd + S`: 保存
- `Esc`: 关闭编辑器

## 测试

运行集成测试：

```bash
python3 test_memory_integration.py
```

## 后端实现

后端使用 FastAPI 实现，文件存储在 `workspace/memory/` 目录：

```
memory/
├── MEMORY.md           # 长期记忆
└── daily/
    ├── 2024-01-01.md  # 每日笔记
    ├── 2024-01-02.md
    └── ...
```

## 性能优化

- 懒加载：只在需要时加载记忆内容
- 缓存：Store 中缓存已加载的记忆
- 虚拟滚动：大量搜索结果时使用虚拟滚动
- 防抖：搜索输入使用防抖

## 安全性

- 工作空间隔离：记忆文件只能在工作空间内
- 输入验证：日期格式验证
- 错误处理：完善的错误处理和用户提示

## 未来改进

- [ ] 记忆标签系统
- [ ] 记忆分类
- [ ] 导出为 PDF/HTML
- [ ] 记忆统计和可视化
- [ ] 记忆版本历史
- [ ] 记忆加密
- [ ] 云同步
