# 业务元数据（精简）

> 仅维护业务表名映射与意图/关键词到表的映射。
> 表结构由数据源中间件按需从数据库自动获取，元数据不包含字段级结构。

```json
{
  "tables": [
    "SSME_FI_InsightBot_SSME_FI_InsightBot_DataBase",
    "SSME_FI_InsightBot_Rate",
    "SSME_FI_InsightBot_CCMapping"
  ],
  "default_tables": ["SSME_FI_InsightBot_CostDataBase"],
  "intent_table_map": {
    "allocation": [
      "SSME_FI_InsightBot_CostDataBase",
      "SSME_FI_InsightBot_Rate"
    ],
    "general_query": ["SSME_FI_InsightBot_CostDataBase"],
    "compare_budget_vs_actual": [
      "SSME_FI_InsightBot_CostDataBase",
      "SSME_FI_InsightBot_Rate"
    ],
    "trend": ["SSME_FI_InsightBot_CostDataBase", "SSME_FI_InsightBot_Rate"]
  },
  "keyword_table_map": {
    "分摊": ["SSME_FI_InsightBot_CostDataBase", "SSME_FI_InsightBot_Rate"],
    "allocation": [
      "SSME_FI_InsightBot_CostDataBase",
      "SSME_FI_InsightBot_Rate"
    ],
    "预算": ["SSME_FI_InsightBot_CostDataBase"],
    "实际": ["SSME_FI_InsightBot_CostDataBase"],
    "趋势": ["SSME_FI_InsightBot_CostDataBase"],
    "对比": ["SSME_FI_InsightBot_CostDataBase"],
    "费率": ["SSME_FI_InsightBot_Rate"],
    "比例": ["SSME_FI_InsightBot_Rate"]
  }
}
```
