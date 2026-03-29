---
name: find-skills
description: 基于腾讯 SkillHub 搜索、安装和管理技能。用户提到“找技能”“安装 skill”“扩展功能”“启用/禁用 skill”“删除 skill”“安装 SkillHub CLI”时优先使用。
homepage: https://github.com/countbot-ai/CountBot
---

# 技能搜索、安装与管理

## 入口

```bash
python3 skills/find-skills/scripts/skillhub_tool.py search "关键词" --json
python3 skills/find-skills/scripts/skillhub_tool.py install <slug> --json
python3 skills/find-skills/scripts/skillhub_tool.py list --json
python3 skills/find-skills/scripts/skillhub_tool.py enable <slug> --json
python3 skills/find-skills/scripts/skillhub_tool.py disable <slug> --json
python3 skills/find-skills/scripts/skillhub_tool.py delete <slug> --json
python3 skills/find-skills/scripts/skillhub_tool.py bootstrap --cli-only --json
```

## 命令与参数

### `search`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py search "关键词" [--limit N] [--json]
```

参数说明：

- `query`
  搜索关键词，必填。建议使用 1 个简洁词组。
- `--limit`
  返回数量，可选。范围 `1-50`，默认 `10`。
- `--json`
  以 JSON 输出结果，可选。

返回字段：

- `slug`
- `name`
- `description`
- `version`

### `install`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py install <slug> [--force] [--json]
```

参数说明：

- `slug`
  技能唯一标识，必填。
- `--force`
  目标目录已存在时覆盖安装，可选。
- `--json`
  以 JSON 输出安装结果，可选。

行为说明：

- 默认安装到当前 workspace 的 `workspace/skills/<slug>/`
- 安装结果会写入 `workspace/skills/.skills_store_lock.json`

### `list`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py list [--json]
```

参数说明：

- `--json`
  以 JSON 输出当前 workspace 技能列表，可选。

返回字段：

- `slug`
- `path`
- `status`
- `enabled`
- `managed`
- `name`
- `version`
- `source`

### `enable`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py enable <slug> [--json]
```

参数说明：

- `slug`
  要启用的技能 slug，必填。
- `--json`
  以 JSON 输出结果，可选。

行为说明：

- 启用状态会写入 `workspace/.skills_config.json`

### `disable`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py disable <slug> [--json]
```

参数说明：

- `slug`
  要禁用的技能 slug，必填。
- `--json`
  以 JSON 输出结果，可选。

行为说明：

- 禁用状态会写入 `workspace/.skills_config.json`

### `delete`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py delete <slug> [--json]
```

参数说明：

- `slug`
  要删除的技能 slug，必填。
- `--json`
  以 JSON 输出结果，可选。

行为说明：

- 删除 `workspace/skills/<slug>/`
- 同时清理 `workspace/skills/.skills_store_lock.json`
- 同时清理 `workspace/.skills_config.json` 中对应禁用状态

### `bootstrap`

```bash
python3 skills/find-skills/scripts/skillhub_tool.py bootstrap [--cli-only | --skill-only | --plugin-only] [--no-skills | --with-skills] [--restart-gateway] [--json]
```

参数说明：

- `--cli-only`
  仅安装 SkillHub CLI。
- `--skill-only`
  仅安装 SkillHub 自带技能模板。
- `--plugin-only`
  仅安装 SkillHub 插件。
- `--no-skills`
  跳过 workspace skill 模板安装。
- `--with-skills`
  强制安装 workspace skill 模板。
- `--restart-gateway`
  安装完成后尝试重启 gateway。
- `--json`
  以 JSON 输出结果，可选。

行为说明：

- CLI 安装到用户目录
- skill 模板默认写入当前 CountBot workspace
- 不覆盖已存在的本地 skill

## 工作流

1. 用户询问有没有某类技能时，先执行 `search`
2. 返回 1 到 3 个最相关结果
3. 用户确认后执行 `install`
4. 用户明确要求管理已安装技能时，再执行 `list`、`enable`、`disable`、`delete`
5. 用户明确要求安装 SkillHub CLI 时，再执行 `bootstrap`

## 规则

- 搜索和安装依托 `https://skillhub.tencent.com/` 的公开接口与下载地址
- 用户已经给出明确 `slug` 时，可以直接安装
- 用户只是在问“有没有某类技能”时，先搜索，不要直接安装
- 输出保持简洁，不补充无关说明
