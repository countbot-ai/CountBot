---
name: web-design
description: 网页设计与部署。生成精美的单页 HTML 网页（报告、落地页、数据可视化等），支持一键部署到 Cloudflare Pages。使用 Tailwind CSS + Chart.js + Font Awesome 技术栈。当用户要求制作网页、生成报告页面、创建落地页、数据可视化展示、部署网页到线上时使用。
homepage: https://github.com/countbot-ai/CountBot
---

# 网页设计与部署

生成精美单页 HTML 并部署到 Cloudflare Pages。

## 设计规范

### 设计语言

根据用户需求自由设计，每次生成的页面应有独特的视觉风格，避免千篇一律。

设计约束：
- 不使用紫色渐变配色
- 不使用 Emoji 表情符号，统一使用 Font Awesome 图标代替
- 布局：灵活运用 Tailwind CSS 的 Grid / Flex 布局，根据内容量和类型选择合适的排版
- 卡片组件：圆角、阴影、悬停动效等可根据风格调整
- 图标：使用 Font Awesome 6.x `<i class="fa-solid fa-xxx">`
- 图表：使用 Chart.js，支持 bar / line / doughnut / radar / polarArea 等
- 响应式：确保移动端和桌面端都有良好的展示效果

### 推荐在线资源（CDN）

```html
<!-- 核心 -->
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">

<!-- 动画 -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">
<script src="https://unpkg.com/aos@2.3.4/dist/aos.js"></script>
<link rel="stylesheet" href="https://unpkg.com/aos@2.3.4/dist/aos.css">

<!-- 字体 -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap">

<!-- 图表增强 -->
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>

<!-- 轮播 -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css">
<script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>

<!-- 代码高亮（技术类页面） -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

<!-- 数字滚动动画 -->
<script src="https://cdn.jsdelivr.net/npm/countup.js@2/dist/countUp.umd.min.js"></script>

<!-- 打字机效果 -->
<script src="https://cdn.jsdelivr.net/npm/typed.js@2.1.0/dist/typed.umd.js"></script>

<!-- 粒子背景 -->
<script src="https://cdn.jsdelivr.net/npm/tsparticles-slim@2/tsparticles.slim.bundle.min.js"></script>

<!-- Markdown 渲染（文档类页面） -->
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

<!-- 图片灯箱 -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/lightgallery@2/css/lightgallery-bundle.min.css">
<script src="https://cdn.jsdelivr.net/npm/lightgallery@2/lightgallery.umd.min.js"></script>
```

按需引入，不必全部加载。根据页面类型选择合适的资源。

按需参考 `assets/template.html` 了解一种可能的实现方式（白底卡片式布局），但不要每次都照搬。

## 部署到 Cloudflare Pages

### 重要规则

- 如果用户没有明确指定部署到哪个项目，必须使用八位随机字母数字前缀 + 内容名称作为项目名（如 `a3f8k2m1-product-intro`、`x7b9d4e2-annual-report`），避免项目名冲突
- 只有用户明确说"部署到 xxx 项目"或"更新 xxx"时，才部署到已有项目
- 随机前缀使用小写字母和数字混合，每次部署生成新的前缀

### 配置

编辑 `skills/web-design/scripts/config.json`：

```json
{
  "api_token": "YOUR_CLOUDFLARE_API_TOKEN"
}
```

API Token 获取：[Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens) > Create Token > Cloudflare Pages: Edit

`account_id` 无需配置，脚本会通过 API 自动获取。

### 命令行调用

纯 Python + REST API 实现，无需 wrangler 或 Node.js。

```bash
# 部署单个 HTML 文件（自动创建项目，自动作为 index.html）
python3 skills/web-design/scripts/deploy.py deploy index.html --project my-site

# 部署整个目录
python3 skills/web-design/scripts/deploy.py deploy ./dist --project my-site

# 部署到预览分支
python3 skills/web-design/scripts/deploy.py deploy ./dist --project my-site --branch preview

# 查看项目列表
python3 skills/web-design/scripts/deploy.py list

# 查看项目部署历史
python3 skills/web-design/scripts/deploy.py deployments --project my-site

```

部署成功后会返回 `https://<project>.pages.dev` 的访问地址。

## AI 调用场景

用户说"帮我做一个产品介绍页"：

1. 根据用户需求设计独特的页面风格
2. 生成 HTML 并保存到本地文件

用户说"部署到线上"（未指定项目）：

```bash
# 八位随机前缀 + 内容名称，避免冲突
python3 skills/web-design/scripts/deploy.py deploy 文件路径 --project a3f8k2m1-product-intro
```

用户说"更新 xxxx 网站"：

```bash
python3 skills/web-design/scripts/deploy.py deploy 文件路径 --project prompt123
```

## 注意事项

- 单文件部署时自动复制为 index.html
- 单文件限制 10MB
- 项目名会作为子域名：`<project>.pages.dev`
- 首次部署会自动创建项目
- 纯 Python 标准库实现，无需 Node.js 或 wrangler
