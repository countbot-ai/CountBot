#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天气查询命令行工具 - 基于 wttr.in v2"""
import argparse
import sys
import json
import io
import os
import urllib.request
import urllib.parse
import urllib.error

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "https://v2.wttr.in"
V1_URL = "https://wttr.in"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch_url(url, timeout=15):
    """请求 URL 并返回文本内容"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8')


def query_weather_json(city, lang="zh", units=None):
    """查询天气，返回 JSON 数据"""
    encoded = urllib.parse.quote(city)
    params = ["format=j1"]
    if lang:
        params.append(f"lang={lang}")
    if units == "uscs":
        params.append("u")
    elif units == "metric":
        params.append("m")
    url = f"{V1_URL}/{encoded}?{'&'.join(params)}"
    raw = fetch_url(url)
    return json.loads(raw)


def query_weather_text(city, lang="zh", units=None):
    """查询天气，返回可读文本（v2 格式）"""
    encoded = urllib.parse.quote(city)
    params = ["T"]
    if lang:
        params.append(f"lang={lang}")
    if units == "uscs":
        params.append("u")
    elif units == "metric":
        params.append("m")
    url = f"{BASE_URL}/{encoded}?{'&'.join(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8')


def query_brief(city, lang="zh"):
    """简洁模式：一行天气"""
    encoded = urllib.parse.quote(city)
    url = f"{V1_URL}/{encoded}?format=3&lang={lang}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8').strip()


def format_current(data):
    """格式化当前天气"""
    cur = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0]

    city_name = ""
    if area.get("areaName"):
        city_name = area["areaName"][0].get("value", "")
    country = ""
    if area.get("country"):
        country = area["country"][0].get("value", "")

    lines = []
    lines.append(f"📍 {city_name}, {country}")
    lines.append(f"🌡️  温度: {cur.get('temp_C', '?')}°C (体感 {cur.get('FeelsLikeC', '?')}°C)")
    lines.append(f"☁️  天气: {cur.get('weatherDesc', [{}])[0].get('value', '?')}")
    lines.append(f"💧 湿度: {cur.get('humidity', '?')}%")
    lines.append(f"💨 风速: {cur.get('windspeedKmph', '?')} km/h {cur.get('winddir16Point', '')}")
    lines.append(f"👁️  能见度: {cur.get('visibility', '?')} km")
    lines.append(f"🌧️  降水: {cur.get('precipMM', '0')} mm")
    lines.append(f"☀️  UV指数: {cur.get('uvIndex', '?')}")
    return "\n".join(lines)


def extract_essential_data(data, days=1):
    """提取天气数据的关键信息，减少输出长度
    
    Args:
        data: wttr.in 原始 JSON 数据
        days: 预报天数，默认 1（仅当天）
    """
    cur = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0]
    
    # 提取位置信息
    location = {
        "city": area.get("areaName", [{}])[0].get("value", ""),
        "country": area.get("country", [{}])[0].get("value", ""),
        "region": area.get("region", [{}])[0].get("value", "")
    }
    
    # 提取当前天气
    current = {
        "temp_c": cur.get("temp_C", ""),
        "feels_like_c": cur.get("FeelsLikeC", ""),
        "weather_desc": cur.get("weatherDesc", [{}])[0].get("value", ""),
        "humidity": cur.get("humidity", ""),
        "wind_speed_kmph": cur.get("windspeedKmph", ""),
        "wind_dir": cur.get("winddir16Point", ""),
        "visibility_km": cur.get("visibility", ""),
        "precip_mm": cur.get("precipMM", ""),
        "uv_index": cur.get("uvIndex", ""),
        "cloud_cover": cur.get("cloudcover", "")
    }
    
    # 提取预报（简化版）
    forecast = []
    for day in data.get("weather", [])[:days]:
        day_info = {
            "date": day.get("date", ""),
            "max_temp_c": day.get("maxtempC", ""),
            "min_temp_c": day.get("mintempC", ""),
            "sunrise": day.get("astronomy", [{}])[0].get("sunrise", ""),
            "sunset": day.get("astronomy", [{}])[0].get("sunset", ""),
            "hourly": []
        }
        
        # 只保留关键时段（6:00, 12:00, 18:00, 21:00）
        key_hours = ["600", "1200", "1800", "2100"]
        for hour_data in day.get("hourly", []):
            time_val = hour_data.get("time", "0")
            if time_val in key_hours:
                day_info["hourly"].append({
                    "time": time_val,
                    "temp_c": hour_data.get("tempC", ""),
                    "weather_desc": hour_data.get("weatherDesc", [{}])[0].get("value", ""),
                    "chance_of_rain": hour_data.get("chanceofrain", "0")
                })
        
        forecast.append(day_info)
    
    result = {
        "location": location,
        "current": current,
    }
    if days > 0:
        result["forecast"] = forecast
    return result


def format_forecast(data, days=3):
    """格式化多日预报"""
    lines = []
    weather_list = data.get("weather", [])[:days]

    for day in weather_list:
        date = day.get("date", "?")
        max_t = day.get("maxtempC", "?")
        min_t = day.get("mintempC", "?")
        sun_rise = day.get("astronomy", [{}])[0].get("sunrise", "?")
        sun_set = day.get("astronomy", [{}])[0].get("sunset", "?")

        lines.append(f"\n📅 {date}")
        lines.append(f"   🌡️  {min_t}°C ~ {max_t}°C")
        lines.append(f"   🌅 日出 {sun_rise} / 日落 {sun_set}")

        # 时段预报 - 只显示关键时段
        key_hours = ["600", "1200", "1800", "2100"]
        for hour_data in day.get("hourly", []):
            time_val = hour_data.get("time", "0")
            if time_val in key_hours:
                time_val_padded = time_val.zfill(4)
                hour_str = f"{time_val_padded[:2]}:{time_val_padded[2:]}"
                desc = hour_data.get("weatherDesc", [{}])[0].get("value", "?")
                temp = hour_data.get("tempC", "?")
                rain = hour_data.get("chanceofrain", "0")
                lines.append(f"   {hour_str}  {temp}°C  {desc}  🌧️{rain}%")

    return "\n".join(lines)


def cmd_query(args):
    """查询当前天气"""
    try:
        if args.json:
            data = query_weather_json(args.city, lang=args.lang, units=args.units)
            # 精简 JSON 输出，query 默认只显示当天
            simplified = extract_essential_data(data, days=1)
            print(json.dumps(simplified, ensure_ascii=False, indent=2))
            return

        if args.detailed:
            # 详细模式：格式化文本
            data = query_weather_json(args.city, lang=args.lang, units=args.units)
            print(format_current(data))
            return

        # 默认：简洁模式（一行输出）
        print(query_brief(args.city, lang=args.lang))

    except urllib.error.HTTPError as e:
        print(f"查询失败: HTTP {e.code} - 请检查城市名是否正确", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_forecast(args):
    """查询多日预报"""
    try:
        data = query_weather_json(args.city, lang=args.lang, units=args.units)

        if args.json:
            # 精简 JSON 输出，forecast 按指定天数
            simplified = extract_essential_data(data, days=args.days)
            print(json.dumps(simplified, ensure_ascii=False, indent=2))
            return

        print(format_current(data))
        print(f"\n{'='*40}")
        print(f"📆 {args.days} 日预报")
        print(format_forecast(data, days=args.days))

    except urllib.error.HTTPError as e:
        print(f"查询失败: HTTP {e.code} - 请检查城市名是否正确", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"查询失败: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='天气查询工具（基于 wttr.in）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s query 北京
  %(prog)s query 上海 --detailed
  %(prog)s query London --lang en
  %(prog)s query 东莞 --json
  %(prog)s forecast 深圳
  %(prog)s forecast 广州 --days 1
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # query 子命令
    q_parser = subparsers.add_parser('query', help='查询当前天气')
    q_parser.add_argument('city', help='城市名（中文/英文/拼音）')
    q_parser.add_argument('--detailed', action='store_true', help='详细模式（多行格式化输出）')
    q_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    q_parser.add_argument('--lang', default='zh', help='语言（默认: zh）')
    q_parser.add_argument('--units', choices=['metric', 'uscs'], help='单位制')

    # forecast 子命令
    f_parser = subparsers.add_parser('forecast', help='多日天气预报')
    f_parser.add_argument('city', help='城市名（中文/英文/拼音）')
    f_parser.add_argument('--days', type=int, default=3, choices=[1, 2, 3], help='预报天数（默认: 3）')
    f_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    f_parser.add_argument('--lang', default='zh', help='语言（默认: zh）')
    f_parser.add_argument('--units', choices=['metric', 'uscs'], help='单位制')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'query':
        cmd_query(args)
    elif args.command == 'forecast':
        cmd_forecast(args)


if __name__ == '__main__':
    main()
