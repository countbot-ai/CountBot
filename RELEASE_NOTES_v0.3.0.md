# CountBot v0.3.0 发布说明

> 🎉 重大功能更新：多智能体工作流、子代理优化、定时任务增强

---

## 🌟 核心亮点

### 1. 多智能体工作流系统 ⭐⭐⭐

**三种协作模式**：
- **Pipeline（流水线）**：顺序执行，适合有明确流程的任务
- **Graph（依赖图）**：自动并行调度，适合复杂工作流
- **Council（多视角）**：多角度分析，支持交叉评审和独立评审

**便捷调用**：
```
# 聊天窗口直接 @ 团队
@内容创作流水线 帮我写一篇关于 AI 的文章

# 飞书等渠道
@CountBot @技术方案评审 评估微服务架构方案
```

**特性**：
- 每个 Agent 独立的系统提示词
- 实时 WebSocket 推送工作流进度
- 工具调用数据持久化
- 支持用户随时取消

---

### 2. 子代理系统优化 ⭐⭐

**性能提升**：
- 迭代次数优化（15 次 vs 主 Agent 25 次）
- 工具注册表精简（只注册必要工具）
- 内存使用优化（自动清理旧任务）

**前端增强**：
- 实时进度条和状态显示
- 工具调用详情可视化
- 支持任务取消操作
- 刷新后状态恢复

**新增功能**：
- 任务统计信息（total/running/completed/failed/cancelled）
- 自动清理旧任务（可配置保留时间）
- 任务列表过滤（按状态、会话）

---

### 3. 定时任务增强 ⭐

**新增功能**：
- **一次性任务**：执行一次后自动禁用
- 任务执行历史记录
- 任务执行统计

**使用示例**：
```python
{
  "name": "明天提醒我开会",
  "schedule": "0 9 * * *",
  "message": "提醒：今天有重要会议",
  "once": true  # 一次性任务标记
}
```

---

### 4. 工作空间管理系统

**功能**：
- 统一的工作空间路径管理
- 临时文件自动管理和清理
- 工作空间信息统计（文件数、大小）

**性能优化**：
- 30秒缓存机制
- 深度限制（10层）
- 自动过滤大型目录（node_modules、.git 等）
- 跳过超大文件（>100MB）

---

### 5. 终端会话控制技能

**新增技能**：`terminal-session`

**功能**：
- 通过 tmux 管理持久化终端会话
- 向交互式程序发送输入（Claude Code、Codex、SSH 等）
- 读取 tmux 会话输出
- 跨多轮对话保持进程状态

**支持平台**：Linux/macOS（Windows 需 WSL2）

---

### 6. 增强的 Web 工具

**新增工具**：
- `web_enhanced` - 增强版 Web 抓取
- `web_fetch_advanced` - 高级 Web 抓取

**功能增强**：
- 多引擎支持（httpx、scrapling、playwright、camoufox）
- JavaScript 渲染支持
- 反爬虫绕过
- 智能内容提取

---

### 7. 完善的文档体系

**新增文档**：
- `docs/AI_QUICK_REFERENCE.md` - AI 快速参考手册（1792 行）
  - 完整的 UI 操作指南
  - 功能详细说明
  - 常见问题排查
  - AI 自查指引

---

## 📦 新增文件

- **API**: 1 个（agent_teams.py）
- **模型**: 1 个（agent_team.py）
- **模块**: 3 个（workflow.py, workspace/, workflow_tool.py）
- **工具**: 2 个（web_enhanced.py, web_fetch_advanced.py）
- **技能**: 1 个（terminal-session/）
- **文档**: 1 个（AI_QUICK_REFERENCE.md）
- **脚本**: 1 个（init_agent_teams.py）
- **前端**: 4 个构建文件更新

---

## 🚀 快速开始

### 创建多智能体团队

```bash
curl -X POST http://localhost:8000/api/agent-teams/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "内容创作团队",
    "mode": "pipeline",
    "agents": [
      {
        "id": "writer",
        "role": "撰稿人",
        "system_prompt": "你是专业撰稿人...",
        "task": "撰写初稿"
      },
      {
        "id": "reviewer",
        "role": "审核员",
        "task": "审核并优化"
      }
    ]
  }'
```

### 使用团队

```
# 方式1：聊天窗口
@内容创作团队 帮我写一篇技术文章

# 方式2：飞书等渠道
@CountBot @内容创作团队 写一篇产品介绍
```

### 创建一次性任务

```bash
curl -X POST http://localhost:8000/api/cron/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "明天提醒",
    "schedule": "0 9 * * *",
    "message": "提醒：今天有重要会议",
    "once": true
  }'
```

---

## 📈 性能影响

### 多智能体工作流

- **Pipeline 模式**：顺序执行，资源消耗与单 Agent 相当
- **Graph 模式**：并行执行，CPU 和内存消耗增加
- **Council 模式**：并发执行多个 Agent，资源消耗最高

**建议**：
- 合理控制 Agent 数量（2-5 个）
- Graph 模式注意依赖关系
- Council 模式适合决策场景

### 子代理系统

- **优化后**：迭代次数减少 40%（15 vs 25）
- **内存优化**：自动清理旧任务
- **响应速度**：工具注册表精简，启动更快

---

## 🔄 升级指南

### 从 v0.2.0 升级

```bash
# 1. 备份数据
cp data/countbot.db data/countbot.db.v0.2.0.bak
cp memory/MEMORY.md memory/MEMORY.md.v0.2.0.bak

# 2. 更新代码
git pull origin main

# 3. 安装依赖
pip install -r requirements.txt

# 4. 初始化数据库
python backend/scripts/init_agent_teams.py

# 5. 重启应用
python start_app.py

# 6. 验证功能
curl http://localhost:8000/api/agent-teams/
curl http://localhost:8000/api/workspace/info
```

---

## 🐛 已知问题

1. **工作空间统计性能**：大型项目（>10万文件）统计较慢
   - 缓解：30秒缓存、深度限制、过滤大型目录

2. **Council 模式轮数**：当前固定 2 轮
   - 计划：未来支持自定义轮数

3. **终端会话 Windows 支持**：需要 WSL2
   - 解决：使用 WSL2 或其他终端复用工具

---

## 📝 后续计划

### v0.3.1（计划中）

- [ ] 工作流模板市场
- [ ] Agent 性能监控和统计
- [ ] 工作流可视化编辑器
- [ ] Council 模式自定义轮数

### v0.4.0（规划中）

- [ ] 分布式多智能体执行
- [ ] Agent 能力评估和自动选择
- [ ] 工作流版本控制
- [ ] 工作流执行历史回放

---

## 🙏 致谢

感谢所有贡献者和用户的反馈！

---

## 📞 联系方式

- GitHub: https://github.com/countbot-ai/countbot
- Issues: https://github.com/countbot-ai/countbot/issues
- 官网: https://654321.ai

---

**CountBot v0.3.0 - 让 AI 协作更强大！**
