---
name: terminal-session
description: tmux 持久化终端会话控制。通过向 tmux 发送按键、读取输出，管理 Claude Code、Codex、SSH 等长时间运行的交互式进程。跨多轮对话保持进程状态。需预装 tmux（Linux/macOS 默认提供；Windows 用户需 WSL2）。
---

# 终端会话控制（tmux）

> 本技能完全通过已有的 `exec` 工具调用系统级 `tmux` CLI，无需任何新工具或依赖。

---

## 使用时机

### ✅ 应当使用本技能的场景

- 监控 Claude Code / Codex 在 tmux 中的运行状态
- 向交互式终端程序发送输入（回答提示、选择选项）
- 读取 tmux 中长时间运行进程的输出
- 跨多轮对话操作同一个后台进程
- 检查已有 tmux 会话中的后台任务进度

### ❌ 不应使用本技能的场景

- **一次性 shell 命令**（ls、grep、python script.py 等）→ 直接用 `exec`
- **启动新后台进程**（无需交互）→ 用 `exec` 执行命令（末尾加 `&`）
- **非交互式脚本** → 直接用 `exec`
- **进程不在 tmux 中** → 无法操作
- **创建新 tmux 会话** → 用 `exec` 执行 `tmux new-session`（本技能专注于操控已有会话）
- **Windows 原生（无 WSL）** → tmux 不可用，告知用户需要 WSL2

---

## 常用会话名称约定

| 会话名 | 用途 |
|--------|------|
| `shared` | 主交互会话 |
| `worker-2` ~ `worker-8` | 并行工作会话 |
| `ssh_prod` | 生产环境 SSH |
| `claude_task` | Claude Code 任务会话 |

---

## 常用命令

### 列出会话

```bash
tmux list-sessions
tmux ls
```

### 读取输出

```bash
# 读取当前屏幕最后 20 行
tmux capture-pane -t shared -p | tail -20

# 读取完整滚动历史
tmux capture-pane -t shared -p -S -

# 读取指定窗口/面板（格式: 会话:窗口.面板）
tmux capture-pane -t shared:0.0 -p
```

### 发送输入

```bash
# 发送文本（不回车）
tmux send-keys -t shared "hello"

# 发送文本并回车
tmux send-keys -t shared "ls -la" Enter

# 特殊按键
tmux send-keys -t shared Enter        # 回车
tmux send-keys -t shared Escape       # Esc
tmux send-keys -t shared C-c          # Ctrl+C（中断）
tmux send-keys -t shared C-d          # Ctrl+D（EOF / 退出 REPL）
tmux send-keys -t shared C-z          # Ctrl+Z（挂起）
```

### 窗口 / 面板导航

```bash
# 切换窗口
tmux select-window -t shared:0

# 切换面板
tmux select-pane -t shared:0.1

# 列出会话所有窗口
tmux list-windows -t shared
```

### 会话管理

```bash
# 创建新会话（后台运行）
tmux new-session -d -s newsession

# 创建并直接启动程序
tmux new-session -d -s claude_task 'claude-code /workspace/project'

# 关闭会话
tmux kill-session -t sessionname

# 重命名会话
tmux rename-session -t old new

# 检查会话是否存在
tmux has-session -t my_session 2>/dev/null && echo "存在" || echo "不存在"
```

---

## 安全发送输入（重要）

对于交互式 TUI 程序（Claude Code、Codex 等），**必须将文本和 Enter 拆开发送**，避免多行粘贴导致的异常：

```bash
# ✅ 正确：先发文本，短暂等待，再发 Enter
tmux send-keys -t shared -l -- "Please apply the patch in src/foo.ts"
sleep 0.1
tmux send-keys -t shared Enter

# ❌ 错误：一次性发送可能引发多行粘贴问题
tmux send-keys -t shared "Please apply the patch in src/foo.ts" Enter
```

---

## Claude Code 会话操作模式

### 检查会话是否在等待输入

```bash
# 查找常见提示符（❯、Yes/No、proceed、permission 等）
tmux capture-pane -t worker-3 -p | tail -10 | grep -E "❯|Yes.*No|proceed|permission|approve"
```

### 确认 Claude Code 提示

```bash
# 发送 y 确认
tmux send-keys -t worker-3 'y' Enter

# 选择编号选项
tmux send-keys -t worker-3 '2' Enter
```

### 向会话发送任务

```bash
tmux send-keys -t worker-4 -l -- "Fix the authentication bug in auth.js"
sleep 0.1
tmux send-keys -t worker-4 Enter
```

### 批量检查所有工作会话状态

```bash
for s in shared worker-2 worker-3 worker-4 worker-5 worker-6 worker-7 worker-8; do
  echo "=== $s ==="
  tmux capture-pane -t $s -p 2>/dev/null | tail -5
done
```

---

## 完整工作流示例

### 启动 Claude Code 并交互

```bash
# 1. 创建会话并启动
tmux new-session -d -s coder 'claude-code /workspace'

# 2. 等待启动（约 3 秒），读取初始状态
sleep 3 && tmux capture-pane -t coder -p | tail -20

# 3. 安全发送任务指令
tmux send-keys -t coder -l -- "Refactor the auth module to use JWT tokens"
sleep 0.1
tmux send-keys -t coder Enter

# 4. 等待执行，周期读取输出
sleep 10 && tmux capture-pane -t coder -p -S -100

# 5. 如有确认提示，回答 y
tmux capture-pane -t coder -p | tail -5 | grep -q "proceed" && \
  tmux send-keys -t coder 'y' Enter

# 6. 完成后关闭会话
tmux kill-session -t coder
```

### SSH 远程操作

```bash
# 建立连接（禁用首次连接确认）
tmux new-session -d -s ssh_prod 'ssh -o StrictHostKeyChecking=no user@10.0.0.1'

# 等待登录完成
sleep 2 && tmux capture-pane -t ssh_prod -p | tail -5

# 执行远程命令
tmux send-keys -t ssh_prod 'df -h && free -m' Enter
sleep 2 && tmux capture-pane -t ssh_prod -p | tail -20
```

---

## 注意事项

- `capture-pane` 必须加 `-p` 才会输出到 stdout（脚本中必须）
- `-S -` 读取完整滚动历史；`-S -200` 读取最近 200 行
- 目标格式：`会话:窗口.面板`（如 `shared:0.0`）
- tmux 会话在 SSH 断开后依然存活，无需重新连接
- 任务完成后务必 `kill-session`，防止僵尸进程堆积
- `exec` 工具的安全策略仍然有效，危险命令仍会被拦截

# https://skills.sh/steipete/clawdis/tmux