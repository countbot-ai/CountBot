#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高德地图路线规划命令行工具"""
import argparse
import sys
import json
import os
from map_manager import MapManager, load_config

# 修复 Windows CMD 下的编码问题
if sys.platform == 'win32':
    # 设置环境变量强制使用 UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'


def main():
    parser = argparse.ArgumentParser(description='高德地图路线规划工具')
    subparsers = parser.add_subparsers(dest='command', help='路线规划类型')
    
    # 驾车路线规划
    driving_parser = subparsers.add_parser('driving', help='驾车路线规划')
    driving_parser.add_argument('--origin', required=True, help='起点 (地址或经纬度)')
    driving_parser.add_argument('--destination', required=True, help='终点 (地址或经纬度)')
    driving_parser.add_argument('--origin-city', help='起点城市 (用于地址解析)')
    driving_parser.add_argument('--dest-city', help='终点城市 (用于地址解析)')
    driving_parser.add_argument('--strategy', type=int, default=32, help='驾车策略 (默认32-高德推荐)')
    driving_parser.add_argument('--waypoints', help='途经点 (多个用;分隔)')
    driving_parser.add_argument('--plate', help='车牌号')
    driving_parser.add_argument('--cartype', type=int, default=0, choices=[0, 1, 2], 
                               help='车辆类型 (0-燃油, 1-纯电, 2-插混)')
    driving_parser.add_argument('--show-fields', help='返回字段控制 (如: cost,polyline)')
    driving_parser.add_argument('--show-steps', action='store_true', help='显示详细路线步骤')
    driving_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 步行路线规划
    walking_parser = subparsers.add_parser('walking', help='步行路线规划')
    walking_parser.add_argument('--origin', required=True, help='起点 (地址或经纬度)')
    walking_parser.add_argument('--destination', required=True, help='终点 (地址或经纬度)')
    walking_parser.add_argument('--origin-city', help='起点城市 (用于地址解析)')
    walking_parser.add_argument('--dest-city', help='终点城市 (用于地址解析)')
    walking_parser.add_argument('--alternative', type=int, choices=[1, 2, 3], 
                               help='返回路线条数 (1-3)')
    walking_parser.add_argument('--show-fields', help='返回字段控制')
    walking_parser.add_argument('--show-steps', action='store_true', help='显示详细路线步骤')
    walking_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 骑行路线规划
    bicycling_parser = subparsers.add_parser('bicycling', help='骑行路线规划')
    bicycling_parser.add_argument('--origin', required=True, help='起点经纬度')
    bicycling_parser.add_argument('--destination', required=True, help='终点经纬度')
    bicycling_parser.add_argument('--alternative', type=int, choices=[1, 2, 3], 
                                 help='返回路线条数 (1-3)')
    bicycling_parser.add_argument('--show-fields', help='返回字段控制')
    bicycling_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 电动车路线规划
    electrobike_parser = subparsers.add_parser('electrobike', help='电动车路线规划')
    electrobike_parser.add_argument('--origin', required=True, help='起点经纬度')
    electrobike_parser.add_argument('--destination', required=True, help='终点经纬度')
    electrobike_parser.add_argument('--alternative', type=int, choices=[1, 2, 3], 
                                   help='返回路线条数 (1-3)')
    electrobike_parser.add_argument('--show-fields', help='返回字段控制')
    electrobike_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 公交路线规划
    transit_parser = subparsers.add_parser('transit', help='公交路线规划')
    transit_parser.add_argument('--origin', required=True, help='起点 (地址或经纬度)')
    transit_parser.add_argument('--destination', required=True, help='终点 (地址或经纬度)')
    transit_parser.add_argument('--city1', required=True, help='起点城市编码')
    transit_parser.add_argument('--city2', required=True, help='终点城市编码')
    transit_parser.add_argument('--strategy', type=int, default=0, 
                               help='换乘策略 (0-推荐, 1-最经济, 2-最少换乘, 3-最少步行)')
    transit_parser.add_argument('--alternative', type=int, default=5, 
                               help='返回方案条数 (1-10)')
    transit_parser.add_argument('--nightflag', type=int, default=0, choices=[0, 1],
                               help='是否考虑夜班车 (0-不考虑, 1-考虑)')
    transit_parser.add_argument('--show-fields', help='返回字段控制')
    transit_parser.add_argument('--show-steps', action='store_true', help='显示详细换乘步骤')
    transit_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # POI搜索
    search_parser = subparsers.add_parser('search', help='POI搜索')
    search_parser.add_argument('--keywords', required=True, help='搜索关键词 (如: 景点, 美食, 酒店)')
    search_parser.add_argument('--city', required=True, help='城市名称')
    search_parser.add_argument('--types', help='POI类型编码 (如: 110000=风景名胜, 050100=中餐厅)')
    search_parser.add_argument('--page-size', type=int, default=10, help='返回结果数量 (1-25)')
    search_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 景点搜索（快捷方式）
    attractions_parser = subparsers.add_parser('attractions', help='搜索景点（只返回风景名胜）')
    attractions_parser.add_argument('--city', required=True, help='城市名称')
    attractions_parser.add_argument('--page-size', type=int, default=20, help='返回结果数量 (1-25)')
    attractions_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    # 餐厅搜索（快捷方式）
    restaurants_parser = subparsers.add_parser('restaurants', help='搜索餐厅（排除快餐）')
    restaurants_parser.add_argument('--city', required=True, help='城市名称')
    restaurants_parser.add_argument('--page-size', type=int, default=20, help='返回结果数量 (1-25)')
    restaurants_parser.add_argument('--json', action='store_true', help='输出JSON格式')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        # 加载配置
        config = load_config()
        manager = MapManager(config['amap_key'])
        
        # 执行命令
        if args.command == 'driving':
            result = manager.driving_route(
                origin=args.origin,
                destination=args.destination,
                origin_city=getattr(args, 'origin_city', None),
                dest_city=getattr(args, 'dest_city', None),
                strategy=args.strategy,
                waypoints=args.waypoints,
                plate=args.plate,
                cartype=args.cartype,
                show_fields=args.show_fields or ('cost,navi' if args.show_steps else 'cost')
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_driving_result(result, show_steps=args.show_steps))
        
        elif args.command == 'walking':
            result = manager.walking_route(
                origin=args.origin,
                destination=args.destination,
                origin_city=getattr(args, 'origin_city', None),
                dest_city=getattr(args, 'dest_city', None),
                alternative_route=args.alternative,
                show_fields=args.show_fields or ('cost,navi' if args.show_steps else 'cost')
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_walking_result(result, show_steps=args.show_steps))
        
        elif args.command == 'bicycling':
            result = manager.bicycling_route(
                origin=args.origin,
                destination=args.destination,
                alternative_route=args.alternative,
                show_fields=args.show_fields
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_walking_result(result))
        
        elif args.command == 'electrobike':
            result = manager.electrobike_route(
                origin=args.origin,
                destination=args.destination,
                alternative_route=args.alternative,
                show_fields=args.show_fields
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_walking_result(result))
        
        elif args.command == 'transit':
            result = manager.transit_route(
                origin=args.origin,
                destination=args.destination,
                city1=args.city1,
                city2=args.city2,
                strategy=args.strategy,
                alternative_route=args.alternative,
                nightflag=args.nightflag,
                show_fields=args.show_fields or ('cost' if not args.show_steps else 'cost')
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_transit_result(result, show_steps=args.show_steps))
        
        elif args.command == 'search':
            result = manager.search_poi(
                keywords=args.keywords,
                city=args.city,
                types=args.types,
                page_size=args.page_size
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_poi_result(result))
        
        elif args.command == 'attractions':
            result = manager.search_attractions(
                city=args.city,
                page_size=args.page_size
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_poi_result(result))
        
        elif args.command == 'restaurants':
            result = manager.search_restaurants(
                city=args.city,
                page_size=args.page_size
            )
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_poi_result(result))
        
        return 0
    
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
