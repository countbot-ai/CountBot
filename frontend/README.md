<div align="center">
  <h1>CountBot Frontend</h1>
  <p>CountBot AI Agent 框架的现代化 Web 前端界面</p>
  
  <p>
    <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3.3+-4FC08D?logo=vue.js&logoColor=white" alt="Vue 3"></a>
    <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-5.3+-3178C6?logo=typescript&logoColor=white" alt="TypeScript"></a>
    <a href="https://vitejs.dev/"><img src="https://img.shields.io/badge/Vite-5.0+-646CFF?logo=vite&logoColor=white" alt="Vite"></a>
    <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## 简介

CountBot Frontend 是 CountBot AI Agent 框架的 Web 用户界面，采用现代化的前端技术栈构建，提供流畅、直观的用户体验。

### 核心特性

- **现代化技术栈** - Vue 3 Composition API + TypeScript + Vite
- **响应式设计** - 适配桌面和移动设备
- **实时通信** - WebSocket 支持，消息即时推送
- **国际化支持** - 中文/英文双语切换
- **主题系统** - 明暗主题自由切换
- **模块化架构** - 清晰的代码组织，易于维护和扩展

---

## 技术栈

### 核心框架

- **Vue 3.3+** - 渐进式 JavaScript 框架，使用 Composition API
- **TypeScript 5.3+** - 类型安全，提升开发体验
- **Vite 5.0+** - 下一代前端构建工具，极速开发体验

### 状态管理与路由

- **Pinia 2.3** - 轻量级状态管理
- **Vue Router 4.6** - 官方路由管理器

### UI 与交互

- **Lucide Vue Next** - 现代化图标库，300+ 精美图标
- **Marked** - Markdown 渲染，支持富文本消息
- **Highlight.js** - 代码高亮显示
- **@vueuse/core** - Vue 组合式工具集

### 网络通信

- **Axios 1.13** - HTTP 客户端，支持请求拦截和自动重试

### 国际化

- **Vue I18n 9.14** - 完整的国际化解决方案

### 开发工具

- **ESLint** - 代码质量检查
- **Prettier** - 代码格式化
- **Vitest** - 单元测试框架
- **Playwright** - E2E 测试框架
- **Vue TSC** - Vue 类型检查

---

## 快速开始

### 环境要求

- Node.js >= 18.0.0
- npm >= 9.0.0

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

访问 `http://localhost:5173` 查看开发环境。

### 生产构建

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

### 预览构建结果

```bash
npm run preview
```

---

## 可用脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器（热重载） |
| `npm run build` | 生产环境构建 |
| `npm run build:check` | 构建前进行类型检查 |
| `npm run preview` | 预览生产构建结果 |
| `npm run type-check` | TypeScript 类型检查 |
| `npm run lint` | ESLint 检查并自动修复 |
| `npm run lint:check` | ESLint 检查（不修复） |
| `npm run format` | Prettier 格式化代码 |
| `npm run format:check` | 检查代码格式 |
| `npm run test` | 运行单元测试 |
| `npm run test:watch` | 监听模式运行测试 |
| `npm run test:e2e` | 运行 E2E 测试 |
| `npm run test:e2e:ui` | E2E 测试 UI 模式 |
| `npm run test:e2e:debug` | E2E 测试调试模式 |

---

## 项目结构

```
frontend/
├── dist/                    # 构建产物（已上传）
├── public/                  # 静态资源
├── src/                     # 源代码（即将开源）
│   ├── api/                 # API 接口封装
│   ├── assets/              # 资源文件
│   ├── components/          # 通用组件
│   │   └── ui/              # UI 基础组件
│   ├── i18n/                # 国际化配置
│   │   └── locales/         # 语言文件
│   ├── modules/             # 功能模块
│   │   ├── chat/            # 聊天模块
│   │   └── settings/        # 设置模块
│   ├── router/              # 路由配置
│   ├── stores/              # Pinia 状态管理
│   ├── types/               # TypeScript 类型定义
│   ├── utils/               # 工具函数
│   ├── App.vue              # 根组件
│   └── main.ts              # 应用入口
├── index.html               # HTML 模板
├── package.json             # 项目配置
├── tsconfig.json            # TypeScript 配置
├── vite.config.ts           # Vite 配置
└── README.md                # 本文档
```

---

## 主要功能模块

### 聊天模块

- 实时消息收发
- Markdown 渲染
- 代码高亮显示
- 会话管理
- 消息历史
- 时间线视图

### 设置模块

- LLM 提供商配置
- 消息渠道管理
- 个性化设置
- 用户管理
- 系统配置

### UI 组件

- 主题切换（明暗模式）
- 语言切换（中英文）
- 响应式布局
- 加载状态
- 错误提示

---

## 开发指南

### 代码规范

项目使用 ESLint 和 Prettier 保证代码质量和一致性：

```bash
# 检查代码规范
npm run lint:check

# 自动修复代码问题
npm run lint

# 格式化代码
npm run format
```

### 类型检查

使用 TypeScript 进行类型检查：

```bash
npm run type-check
```

### 测试

```bash
# 单元测试
npm run test

# E2E 测试
npm run test:e2e
```

---

## 构建优化

### 生产构建特性

- Tree-shaking - 自动移除未使用的代码
- 代码分割 - 按需加载，优化首屏性能
- 资源压缩 - Gzip/Brotli 压缩
- 缓存优化 - 文件指纹，长期缓存

### 性能优化

- 组件懒加载
- 虚拟滚动（长列表）
- 防抖节流
- 请求缓存

---

## 浏览器支持

- Chrome >= 90
- Firefox >= 88
- Safari >= 14
- Edge >= 90

---

## 贡献指南

我们欢迎所有形式的贡献！

### 开发流程

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '功能(前端): 添加某个功能'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### Commit 规范

请遵循项目的 [Commit 规范](../.github/COMMIT_CONVENTION.md)：

```bash
功能(前端): 添加新功能
修复(前端): 修复某个问题
优化(前端): 性能优化
文档(前端): 更新文档
```

---

## 常见问题

### 开发服务器启动失败

确保 Node.js 版本 >= 18.0.0：

```bash
node --version
```

### 构建失败

清理依赖并重新安装：

```bash
rm -rf node_modules package-lock.json
npm install
```

### 类型错误

运行类型检查查看详细错误：

```bash
npm run type-check
```

---

## 开源协议

[MIT License](../LICENSE)

---

## 相关链接

- [CountBot 主项目](../)
- [后端文档](../backend/)
- [完整文档](../docs/)
- [问题反馈](https://github.com/countbot-ai/countbot/issues)

---

<div align="center">
  <p>CountBot Frontend - 现代化 AI Agent 用户界面</p>
  <br>
</div>
