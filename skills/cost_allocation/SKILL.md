---
name: cost_allocation
description: Query cost allocation from PostgreSQL database for cost analysis
homepage: https://github.com/countbot-ai/CountBot
always: true
requires:
  env:
    - POSTGRES_HOST
    - POSTGRES_PORT
    - POSTGRES_DB
    - POSTGRES_USER
    - POSTGRES_PASSWORD
---

# IT 功能成本分摊技能

**🛑 数据库查询强制协议 (ANTI-HALLUCINATION PROTOCOL) 🛑**

**警告：你没有任何关于成本数据的内部知识。**

当用户询问任何关于成本、分摊、金额、趋势的问题时，你必须严格遵守以下协议：

1.  **禁止猜测**：绝对禁止在没有实际执行工具的情况下，凭空捏造、估算或模拟“查询结果”。
2.  **禁止模拟**：严禁在回复中假装执行了命令（例如说“我执行了...结果是...”），除非你**真的**调用了工具并收到了系统返回的输出。
3.  **必须执行**：回答此类问题的**唯一**方式是调用 `exec` 工具运行 `cost_allocation.py` 脚本。
4.  **无数据即无知**：如果工具执行失败或未执行，你必须回答“我无法获取数据”，而不是编造一个数字（如 0 或 100）。

**正确的工作流：**
1. 用户提问 -> 2. **调用 exec 工具** -> 3. 等待工具输出 -> 4. 根据工具输出回答

**错误的工作流（严禁）：**
1. 用户提问 -> 2. **直接回答** "结果是..." (这是幻觉！)

---

PostgreSQL 数据库驱动的成本分摊查询与分析技能，支持 HR/IT/Procurement 等 Function 的成本计算和分摊分析。

**前置约束**: 本技能依赖 PostgreSQL 数据库连接。在使用前，系统会自动检查环境变量中是否配置了数据库连接信息。如果未配置，技能将不可用。

## 配置

数据库连接配置通过环境变量（必须配置，否则技能无法加载）：

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=cost_allocation
POSTGRES_USER=postgres
POSTGRES_PASSWORD=123456
```

## AI 调用场景

**重要：使用绝对路径执行脚本！**

**核心原则（MANDATORY）：**
1. **必须查询数据库**：回答任何有关成本、分摊或趋势的问题时，**必须**调用 `cost_allocation.py` 脚本查询数据库。
2. **严禁编造数据**：绝对禁止在没有执行脚本并获得输出的情况下，凭空捏造、估算或“根据经验”回答数字。
3. **数据来源唯一性**：数据库是唯一的事实来源（Single Source of Truth）。如果脚本执行失败或返回空结果，必须如实告知用户“无法获取数据”，不得尝试自行计算或给出模拟数据。
4. **参数准确性**：必须严格按照用户问题的意图提取准确的年份（FY25/FY26）、场景（Actual/Budget1）和部门（HR/IT等）作为脚本参数。

脚本完整路径：`D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py`

### 解决问题流程

当用户提出问题时，你需要按照以下步骤将自然语言转换为 SQL 查询：

1.  **理解意图**：分析用户想查询的是“基础成本”、“分摊结果”还是“趋势分析”。
2.  **提取实体**：识别问题中的关键实体，如年份 (FYxx)、场景 (Actual/Budget)、功能 (IT/HR/Procurement)、成本中心 (CC)、业务线 (BL) 等。
3.  **映射字段**：将提取的实体映射到数据库表的字段。参考下方的“数据字典与映射关系”。
4.  **构建查询**：使用 `cost_allocation.py` 脚本构建查询命令。

### 数据字典与映射关系

参考 `Function cost allocation analysis to IT 20260104.xlsx` 的结构：

#### 1. 费率表 (`rate_table`)
| 字段 | 说明 | 示例值 |
|------|------|--------|
| `bl` | 业务线 (Business Line) | CT, CS, MP, XP |
| `cc` | 成本中心 (Cost Center) | 412011, 413021 |
| `year` | 财年 | FY24, FY25, FY26 |
| `scenario` | 场景 | Actual, Budget1 |
| `month` | 月份 | Oct, Nov, ..., Sep |
| `key` | 分摊依据 Key | WCW, SAM, Win Acc |
| `rate_no` | 分摊比例 | 0.228 (22.8%) |

#### 2. 成本数据库表 (`cost_database`)
| 字段 | 说明 | 示例值 |
|------|------|--------|
| `year` | 财年 | FY25, FY26 |
| `scenario` | 场景 | Actual, Budget1 |
| `function` | 功能部门 | IT, HR, Procurement, IT Allocation |
| `cost_text` | 成本项描述 | 详见下方“可用 Cost Text 列表” |
| `key` | 分摊 Key (关联 Rate 表) | WCW, SAM |
| `amount` | 金额 | 161138.50 |
| `month` | 月份 | Oct, Nov |

### 可用 Cost Text 列表 (数据库真实值)

**Function: IT (原始成本)**
- `5547 DLP`
- `5547 GS IT`
- `7092 GS IT_End user` (注意拼写)
- `7092 GS IT_SW`
- `CMO`
- `ISD & AHD`
- `M365 Collaboration`
- `M365 Messaging`
- `MWP`
- `P41`
- `Printing`
- `SD-LAN Hub`
- `SD-LAN Local`

**Function: IT Allocation (分摊结果)**
- `Function IT allocation to BL CC` (所有 IT 成本汇总为这一项)
- **注意**: 分摊表中不包含原始 IT 服务的明细。无法查询“分摊给某 CC 的 M365 费用”，只能查询“分摊给某 CC 的 IT 总费用”。

**Function: HR (原始成本)**
- `Field HR`
- `GBS H2R`
- `HR`

**Function: HR Allocation (分摊结果)**
- `Function HR allocation to BL CC`

**Function: Procurement (原始成本)**
- `GBS P2P`
- `Pooling & MPC`
- `Procurement`
- `SOP SCM`

**Function: Procurement Allocation (分摊结果)**
- `Function P IM allocation to BL CC`
- `Function P Pooling allocation to BL CC`

### 用户问题 -> SQL 映射示例

#### 场景 1：查询某个月的具体分摊
**用户问**：“412011 在 FY26 预算的 10月份，分摊到了 IT 总费用多少钱？”

**分析**：
- **Year**: FY26
- **Scenario**: Budget1
- **Month**: Oct (10月)
- **CC**: 412011
- **Function**: IT Allocation
- **Cost Text**: Function IT allocation to BL CC (根据上述规则自动推断)

**SQL 逻辑**：
```sql
SELECT SUM(ABS(cd.amount) * rt.rate_no)
FROM cost_database cd
JOIN rate_table rt ON ...
WHERE cd.year = 'FY26' 
AND cd.scenario = 'Budget1'
AND cd.month = 'Oct'
AND cd.function = 'IT Allocation'
AND cd.cost_text = 'Function IT allocation to BL CC'
AND rt.cc = '412011'
```

**对应命令**：
```bash
exec(command='D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type allocation --year FY26 --scenario Budget1 --function "IT Allocation" --party-cc 412011 --month Oct --json')
```

**注意**：如果不指定 `--cost-text`，脚本默认汇总该 Function 下的所有分摊项，这通常是正确的做法。

#### 场景 2：查询原始成本明细 (支持具体服务)
**用户问**：“FY26 预算中，IT 部门在 M365 上花了多少钱？”

**分析**：
- **Function**: IT (查询原始成本，非 Allocation)
- **Cost Text**: M365 Collaboration (模糊匹配或精确匹配)

**对应命令**：
```bash
exec(command='D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function IT --cost-text "M365 Collaboration" --json')
```

#### 场景 3：手动计算分摊（高级场景）
当用户问到特定原始服务（如 `7092 GS IT_End user`）分摊给某 CC 的金额时，由于 Allocation 表不包含明细，可以通过“原始成本 * 分摊比例”手动计算：

**用户问**：“FY26 BGT 10月份 412011被分到的7092 GS IT_End user服务的金额？”

**逻辑**：
1. 查询原始成本：Cost页中 Year=FY26, Scenario=Budget1, Cost text=7092 GS IT_End user, Month=Oct 下的金额。
2. 查询分摊比例：Rate页中 FY26, Budget1, Oct, Key=WCW+software usage (需通过知识库知道该服务对应的 Key), CC=412011 的比例。
3. 计算：原始金额 * 比例。

**目前脚本支持**：脚本尚未内置自动关联 Key 的逻辑。如果需要支持此类深度问答，建议提示用户先查询原始成本，再查询分摊比例（目前脚本未公开 Rate 查询接口）。

### 常用命令模板

**必须**执行脚本查询，严禁编造！

**1. 基础成本查询**
```bash
exec(command='D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function HR --json')
```

**2. 分摊计算 (按 CC)**
```bash
exec(command='D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type allocation --year FY26 --scenario Budget1 --function "IT Allocation" --party-cc 412011 --json')
```

**3. 趋势分析**
```bash
exec(command='D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type trend --function Procurement --cost-text "Pooling & MPC" --json')
```

## 命令行调用示例

```bash
# 基础成本查询
D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type cost --year FY26 --scenario Budget1 --function HR

# IT 分摊到 CT
D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py query --type allocation --year FY25 --scenario Actual --function "IT Allocation" --party-bl CT

# 运行测试
D:/countbot/countbot/venv/Scripts/python D:/countbot/countbot/skills/cost_allocation/scripts/cost_allocation.py test
```

## 核心业务规则

### 1. 成本查询（--type cost）
直接查询 cost_database 表，返回基础成本信息。支持 `--month` 过滤。

### 2. 分摊计算（--type allocation）
分摊公式：ABS(cost_amount) * rate_no
需要关联 rate_table 获取分摊比例。支持 `--month` 和 `--cost-text` 过滤。

### 3. 趋势分析（--type trend）
对比 FY25 Actual 和 FY26 Budget：
- 变化值 = FY26 - FY25
- 变化率 = (FY26 - FY25) / FY25 * 100%

