# 贡献指南

感谢你对 CountBot 的关注！我们欢迎所有形式的贡献。

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/countbot-ai/countbot.git
cd countbot

# 安装后端依赖
pip install -r requirements.txt

# 启动开发服务器（热重载）
python start_dev.py
```

## Commit 规范

本项目使用中文 Commit 规范，格式如下：

```
<类型>(<范围>): <简短描述>
```

### 类型说明

| 类型 | 用途 |
|------|------|
| `初始化` | 项目初始化 |
| `功能` | 新增功能 |
| `修复` | 修复 Bug |
| `文档` | 文档变更 |
| `重构` | 代码重构 |
| `优化` | 性能优化 |
| `构建` | 构建/CI 相关 |
| `杂项` | 其他变更 |

### 示例

```bash
git commit -m "功能(记忆): 添加关键词搜索功能"
git commit -m "修复(渠道): 修复飞书消息延迟问题"
git commit -m "文档(README): 更新快速开始指南"
git commit -m "优化(Agent): 降低上下文 Token 消耗"
```

## 添加新组件

- 新 LLM 提供商 → `backend/modules/providers/`
- 新消息渠道 → `backend/modules/channels/`
- 新工具 → `backend/modules/tools/`
- 新技能 → `skills/<skill-name>/`

## 代码风格

- Python: 遵循 PEP 8，使用 flake8 检查
- 注释使用中文
- 变量/函数名使用英文

## 提交 PR

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交变更（遵循 Commit 规范）
4. 推送到你的 Fork (`git push origin feature/xxx`)
5. 创建 Pull Request

## 问题反馈

- Bug 报告：使用 [Bug 报告模板](https://github.com/countbot-ai/countbot/issues/new?template=bug_report.md)
- 功能建议：使用 [功能请求模板](https://github.com/countbot-ai/countbot/issues/new?template=feature_request.md)
