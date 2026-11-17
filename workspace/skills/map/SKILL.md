---
name: map
description: 高德地图路线规划与 POI 搜索。支持驾车、步行、骑行、公交路线规划，以及景点、餐厅搜索。当用户询问路线、行程规划、景点推荐、餐厅推荐时使用。
homepage: https://github.com/countbot-ai/CountBot
---

# 地图路线规划与 POI 搜索

基于高德地图 API 的路线规划和 POI 搜索服务。

## 配置

编辑 `skills/map/scripts/config.json`，填写高德地图 API Key：

```json
{
  "amap_key": "YOUR_AMAP_KEY"
}
```

## AI 调用示例

用户说"我想去东莞玩3天"：

```bash
# 1. 搜索景点
python3 skills/map/scripts/map.py attractions --city 东莞 --page-size 20 --json

# 2. 查询景点间路线
python3 skills/map/scripts/map.py driving --origin "旗峰公园" --destination "可园博物馆" --origin-city 东莞 --dest-city 东莞
```

用户说"东莞有什么好吃的"：

```bash
python3 skills/map/scripts/map.py restaurants --city 东莞 --page-size 20 --json
```

用户说"从天安门到鸟巢坐地铁怎么走"：

```bash
python3 skills/map/scripts/map.py transit --origin "天安门" --destination "鸟巢" --city1 010 --city2 010
```

## 命令行参考

### 路线规划

```bash
# 驾车
python3 skills/map/scripts/map.py driving --origin "起点" --destination "终点" --origin-city 城市 --dest-city 城市

# 步行
python3 skills/map/scripts/map.py walking --origin "起点" --destination "终点" --origin-city 城市 --dest-city 城市

# 公交（需要城市编码）
python3 skills/map/scripts/map.py transit --origin "起点" --destination "终点" --city1 编码 --city2 编码

# 显示详细步骤
python3 skills/map/scripts/map.py driving --origin "起点" --destination "终点" --show-steps
```

### POI 搜索

```bash
# 景点搜索（风景名胜 + 博物馆）
python3 skills/map/scripts/map.py attractions --city 城市 --page-size 20

# 餐厅搜索（排除快餐）
python3 skills/map/scripts/map.py restaurants --city 城市 --page-size 20

# 通用搜索
python3 skills/map/scripts/map.py search --keywords 关键词 --city 城市
```

## 常用城市编码

| 城市 | 编码 | 城市 | 编码 |
|------|------|------|------|
| 北京 | 010 | 上海 | 021 |
| 广州 | 020 | 深圳 | 0755 |
| 东莞 | 0769 | 杭州 | 0571 |

## 注意事项

- 支持地址名称或经纬度坐标作为起终点，系统自动识别
- 建议提供城市参数以提高地址解析准确性
- 公交路线必须提供城市编码
- 所有搜索命令支持 `--json` 输出
