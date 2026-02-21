---
name: weather
description: 天气查询与预报。支持全球城市天气查询、多日预报、详细气象数据。无需 API Key。当用户询问天气、气温、是否下雨、穿衣建议、出行天气等场景时使用。JSON 输出已优化，只返回关键信息。
homepage: https://github.com/countbot-ai/CountBot
---

# 天气查询

免费天气服务，无需 API Key，支持中文。


## 命令行调用

```bash
# 查询城市天气（默认简洁一行输出）
python3 skills/weather/scripts/weather.py query 北京

# 详细模式（多行格式化输出）
python3 skills/weather/scripts/weather.py query 上海 --detailed

# 查看多日预报
python3 skills/weather/scripts/weather.py forecast 深圳

# 仅今天
python3 skills/weather/scripts/weather.py forecast 广州 --days 1

# JSON 输出（推荐 AI 使用，已优化为精简格式）
python3 skills/weather/scripts/weather.py query 东莞 --json

# 英文城市名
python3 skills/weather/scripts/weather.py query London --lang en

# 指定单位（metric/uscs）
python3 skills/weather/scripts/weather.py query Tokyo --units uscs
```

## AI 调用场景

用户说"今天北京天气怎么样"：

```bash
python3 skills/weather/scripts/weather.py query 北京 --json
```

用户说"这周末适合出去玩吗"：

```bash
python3 skills/weather/scripts/weather.py forecast 当前城市 --json
```

用户说"明天要不要带伞"：

```bash
python3 skills/weather/scripts/weather.py query 当前城市 --json
```

## 备用方式（curl）

如果 Python 脚本不可用，可直接使用 curl：

```bash
# 快速查询
curl -s "wttr.in/Beijing?format=3"

# 完整预报
curl -s "wttr.in/Beijing?lang=zh"

# 自定义格式
curl -s "wttr.in/Beijing?format=%l:+%c+%t+%h+%w"
```

格式码：`%c` 天气 · `%t` 温度 · `%h` 湿度 · `%w` 风速 · `%l` 地点 · `%m` 月相

## 注意事项

- 城市名支持中文、英文、拼音
- URL 中空格用 `+` 替代
- 支持机场代码（如 JFK）
- `?m` 公制 / `?u` 美制
