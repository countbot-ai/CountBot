---
rules:
  - id: allocation_calculation
    description: "分摊计算公式"
    rule: "分摊金额 = ABS(cost_amount) * rate_no"

  - id: function_key_mapping
    description: "Function 与 Key 的对应关系"
    rule: "不同 Function 使用固定 Key 进行分摊（如 IT/HR/Procurement 的 Allocation Key）。"

  - id: cost_data_sign
    description: "成本数据符号"
    rule: "Original 为正，Allocation 为负，同一 Function Total + Allocation = 0。"

  - id: fiscal_year
    description: "财年周期"
    rule: "财年周期为 10 月至次年 9 月。"

  - id: query_priority
    description: "分摊优先级"
    rule: "能明确到 CC 时优先按 CC 维度计算。"
---

# 业务规则（摘要）

本文件仅保留规则摘要，字段结构由数据源自动获取。
