---
name: agent-team-manager
description: 多智能体团队管理。创建、查看、修改、删除 CountBot 的多智能体团队，管理团队成员（角色）和团队级自定义模型配置。当用户要新建 Pipeline/Graph/Council 团队、调整成员分工、修改依赖关系、开关技能系统、设置团队专属模型时使用。
version: 1.0.0
always: false
---

# 多智能体团队管理

通过命令行管理 CountBot 的多智能体团队，覆盖团队 CRUD、成员 CRUD、以及团队级模型配置。

## 使用场景

- 用户说“帮我新建一个多智能体团队” -> 创建团队
- 用户说“做一个文档深度分析团队” -> 按模板创建团队
- 用户说“把这个团队改成依赖图模式” -> 修改团队
- 用户说“给团队加一个审稿角色” -> 添加成员
- 用户说“把 analyzer 的任务改一下” -> 修改成员
- 用户说“把这个角色的提示词优化一下” -> 先看当前成员配置，再修改 `task` 和/或 `system_prompt`
- 用户说“删掉 summarizer 这个角色” -> 删除成员
- 用户说“给这个团队单独配置模型” -> 配置团队自定义模型
- 用户说“看看有哪些团队/成员” -> 列表或详情

## 调用方式

所有操作通过 `exec` 工具执行：

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py <command> [args]
```

## 严格语法

- 只有这些一级命令：`list`、`info`、`template-list`、`create`、`update`、`delete`、`member-list`、`member-add`、`member-update`、`member-delete`、`config`、`config-set`、`config-reset`
- `info` / `member-list` / `update` / `config-set` 的团队参数都是位置参数，不支持 `--team`
- `member-update` 的成员参数是第二个位置参数 `member_ref`，不支持 `--id`
- 开关技能系统要用团队命令 `update "团队名" --enable-skills` 或 `--disable-skills`
- 先看 `--help`，再按帮助里的位置参数顺序执行；不要自行发明子命令或参数名

## 常用命令

### 列出团队

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py list
```

### 查看团队详情

`team_ref` 支持团队名称、完整 ID、ID 前缀。

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py info "文档深度分析"
```

### 创建团队

```bash
# 创建空团队，后续再逐个添加成员
python3 skills/agent-team-manager/scripts/agent_team_manager.py create \
  --name "文档深度分析" \
  --description "理解文档 → 提取要点 → 分析问题 → 生成总结报告" \
  --mode pipeline \
  --enable-skills

# 直接按内置模板创建
python3 skills/agent-team-manager/scripts/agent_team_manager.py create \
  --template document-analysis
```

### 修改团队

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py update "文档深度分析" \
  --mode graph \
  --description "先并行抽取，再汇总结论" \
  --active

python3 skills/agent-team-manager/scripts/agent_team_manager.py update "文档深度分析" \
  --disable-skills
```

### 删除团队

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py delete "文档深度分析"
```

## 成员管理

### 列出成员

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-list "文档深度分析"
```

### 添加成员

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-add "文档深度分析" \
  --id reader \
  --role "文档理解专家" \
  --task "通读文档，理解整体结构和核心内容" \
  --system-prompt "你是文档理解专家，先识别文档结构，再提炼核心主题。"
```

Graph 模式可附带依赖与条件：

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-add "代码检查团队" \
  --id refactor \
  --role "重构建议专家" \
  --task "基于前序检查结果给出重构建议" \
  --depends-on syntax-checker,logic-analyzer \
  --condition-type output_contains \
  --condition-node logic-analyzer \
  --condition-text 严重
```

Council 模式建议填写 `--perspective`：

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-add "投资评审会" \
  --id risk \
  --role "风险分析师" \
  --perspective "风险与合规"
```

### 修改成员

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-update "文档深度分析" analyzer \
  --task "重点分析论证链、信息缺口和潜在偏见" \
  --system-prompt "你是批判性分析专家，输出问题、证据和风险。"
```

### 修改现有角色提示词（强约束）

凡是用户表达以下意图，统一按“修改现有角色提示词”处理：

- 优化角色提示词
- 改 prompt / 改系统提示词
- 调整角色设定、语气、边界、输出要求
- 让某个成员“更专业 / 更严格 / 更像某类专家”

强制执行顺序如下。

#### 1. 先读取当前真实配置，不允许凭印象修改

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py info "文档深度分析"
```

必须先看目标成员当前是否存在 `task`、`system_prompt`，再决定修改哪个字段。
禁止在未读取当前配置前直接生成 `member-update` 命令。

#### 2. 字段归属判定规则

1. 若目标成员只有 `task`，没有 `system_prompt`
2. 说明该团队把提示词主体直接存放在 `task`
3. 此时用户说“改提示词”，默认优先修改 `--task`
4. 若目标成员已有 `system_prompt`
5. 涉及角色人格、专家身份、口吻、原则、边界、长期行为约束时，优先修改 `--system-prompt`
6. 涉及具体工作内容、执行步骤、输出结构、交付格式、检查项时，优先修改 `--task`
7. 若当前 `task` 本身是一整段提示词式文本，且用户想做系统化重构，应同时修改 `--task` 与 `--system-prompt`

#### 3. 执行规范

- 修改必须落库，最终动作一定是执行 `member-update`
- `member-update` 的正确形式是：
  `python3 skills/agent-team-manager/scripts/agent_team_manager.py member-update "团队名" 成员ID [flags]`
- 成员标识使用位置参数 `member_ref`，不要写成 `--id`
- 修改完成后，建议再次执行 `info "团队名"` 复核结果
- 如果用户要求“修改提示词”，但当前配置里只有 `task`，不要只改 `system_prompt`
- 如果用户要求“系统提示词更专业”，但旧的长提示还残留在 `task` 中，应判断是否需要同步精简 `task`

示例：当前成员只有 `task`，没有 `system_prompt`

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-update "小红书文案团队" reviewer \
  --task "审核小红书文案，检查敏感词、风格统一、内容完整、平台规范和可读性；输出审核结论、修改建议、最终发布版与发布提醒。"
```

示例：明确修改系统提示词

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-update "小红书文案团队" reviewer \
  --system-prompt "你是严格的小红书内容审核专家，优先识别违规风险和夸大表达，输出结论必须清晰、克制、可执行。"
```

示例：把旧的提示词式 task 拆成“任务 + 系统提示词”

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-update "小红书文案团队" reviewer \
  --task "审核小红书文案并输出审核结论、修改建议、最终发布版与发布提醒。" \
  --system-prompt "你是严格的小红书内容审核专家，重点检查敏感词、极限词、医疗宣称、风格统一、内容完整和平台规范。"
```

#### 4. 专业处理原则

- 目标是“修改有效配置”，不是“输出一段看起来更好的文案”
- 先识别现有数据结构，再决定改哪个字段
- 以最小必要修改为原则，避免只新增字段而保留旧冲突内容
- 若用户未指定字段名，“提示词”一词要结合当前存储结构解释，不得机械等同于 `system_prompt`

### 删除成员

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py member-delete "文档深度分析" summarizer
```

## 团队模型配置

### 查看当前配置

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py config "文档深度分析"
```

### 设置自定义模型

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py config-set "文档深度分析" \
  --provider zhipu \
  --model glm-5 \
  --temperature 0.5 \
  --max-tokens 8192
```

### 重置为全局默认

```bash
python3 skills/agent-team-manager/scripts/agent_team_manager.py config-reset "文档深度分析"
```

## 参数说明

- `mode` 仅支持 `pipeline`、`graph`、`council`
- `--enable-skills` 开启后，子 Agent 可读取并使用 `skills/*`
- `--cross-review` / `--no-cross-review` 仅对 `council` 模式有意义
- `depends_on` 仅对 `graph` 模式有意义
- `perspective` 主要用于 `council` 模式
- `task` 会作为执行阶段的 `# Your Task` 传给子 Agent，是实际任务说明
- `system_prompt` 是角色长期人格/职责设定
- 如果 `system_prompt` 为空，系统会基于 `role + task` 自动生成默认系统提示词
- 如果 `system_prompt` 有值，会直接作为系统消息使用；但 `task` 仍然会继续传入执行提示中
- 因此：已有成员只有 `task` 时，优先更新 `task`；需要稳定角色口吻/边界时，再补或修改 `system_prompt`
- 很多历史团队把整段“提示词式描述”直接写进了 `task`，这不是脚本失效，而是数据本来就这样存的
- 所以“提示词改了没生效”时，优先检查是不是旧提示还躺在 `task` 里

## 内置模板

当前内置：

- `document-analysis`：文档深度分析，`pipeline` 模式，默认开启技能系统

## 注意事项

- 团队名称必须唯一
- 成员 ID 在同一团队内必须唯一
- 修改成员本质上会读取团队详情后整体回写 `agents`
- 如果团队启用了专属模型，执行 `workflow_run(team_name="团队名", goal="...")` 时会自动继承该模型配置
- 如果 CountBot 后端未启动，脚本会直接报连接失败
