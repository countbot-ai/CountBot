# -*- coding: utf-8 -*-
"""高德地图路线规划核心模块"""
import requests
import json
import os
import re
from typing import Dict, List, Optional, Tuple

# 修复 Windows CMD 下的编码问题
if os.name == 'nt':  # Windows
    os.environ['PYTHONIOENCODING'] = 'utf-8'


class MapManager:
    """高德地图管理器"""
    
    def __init__(self, api_key: str):
        """初始化地图管理器
        
        Args:
            api_key: 高德地图API Key
        """
        self.api_key = api_key
        self.base_url = "https://restapi.amap.com/v5/direction"
        self.geocode_url = "https://restapi.amap.com/v3/geocode/geo"
        self.poi_search_url = "https://restapi.amap.com/v5/place/text"
        self.poi_around_url = "https://restapi.amap.com/v5/place/around"
    
    def _is_coordinate(self, location: str) -> bool:
        """判断是否为坐标格式
        
        Args:
            location: 位置字符串
            
        Returns:
            是否为坐标格式
        """
        # 匹配经纬度格式：数字,数字
        pattern = r'^-?\d+\.?\d*,-?\d+\.?\d*$'
        return bool(re.match(pattern, location.strip()))
    
    def geocode(self, address: str, city: Optional[str] = None) -> Tuple[str, str]:
        """地理编码：将地址转换为坐标
        
        Args:
            address: 地址描述
            city: 城市名称（可选，用于提高准确性）
            
        Returns:
            (经纬度坐标, 格式化地址)
        """
        params = {
            'key': self.api_key,
            'address': address,
            'output': 'json'
        }
        
        if city:
            params['city'] = city
        
        try:
            response = requests.get(self.geocode_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == '1' and data.get('geocodes'):
                geocode = data['geocodes'][0]
                location = geocode.get('location', '')
                formatted_address = geocode.get('formatted_address', address)
                
                if not location:
                    raise Exception(f"无法获取地址坐标: {address}")
                
                return location, formatted_address
            else:
                raise Exception(f"地理编码失败: {data.get('info', '未知错误')}")
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"地理编码请求失败: {str(e)}")
    
    def smart_location(self, location: str, city: Optional[str] = None) -> Tuple[str, str]:
        """智能位置解析：自动判断是坐标还是地址
        
        Args:
            location: 位置（可以是坐标或地址）
            city: 城市名称（可选）
            
        Returns:
            (经纬度坐标, 显示名称)
        """
        if self._is_coordinate(location):
            return location, location
        else:
            coord, formatted_addr = self.geocode(location, city)
            return coord, formatted_addr
    
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
            
        Returns:
            API响应数据
        """
        params['key'] = self.api_key
        params['output'] = 'json'
        
        try:
            response = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == '1':
                return data
            else:
                raise Exception(f"API错误: {data.get('info', '未知错误')}")
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {str(e)}")
    
    def driving_route(self, 
                     origin: str, 
                     destination: str,
                     strategy: int = 32,
                     waypoints: Optional[str] = None,
                     avoidpolygons: Optional[str] = None,
                     plate: Optional[str] = None,
                     cartype: int = 0,
                     ferry: int = 0,
                     show_fields: Optional[str] = None,
                     origin_city: Optional[str] = None,
                     dest_city: Optional[str] = None) -> Dict:
        """驾车路线规划
        
        Args:
            origin: 起点 (可以是经纬度或地址)
            destination: 终点 (可以是经纬度或地址)
            strategy: 驾车策略 (默认32-高德推荐)
            waypoints: 途经点 (多个用;分隔)
            avoidpolygons: 避让区域
            plate: 车牌号
            cartype: 车辆类型 (0-燃油, 1-纯电, 2-插混)
            ferry: 是否使用轮渡 (0-使用, 1-不使用)
            show_fields: 返回字段控制
            origin_city: 起点城市（用于地理编码）
            dest_city: 终点城市（用于地理编码）
            
        Returns:
            路线规划结果（包含origin_name和dest_name字段）
        """
        # 智能解析起点和终点
        origin_coord, origin_name = self.smart_location(origin, origin_city)
        dest_coord, dest_name = self.smart_location(destination, dest_city)
        
        params = {
            'origin': origin_coord,
            'destination': dest_coord,
            'strategy': strategy,
            'cartype': cartype,
            'ferry': ferry
        }
        
        if waypoints:
            params['waypoints'] = waypoints
        if avoidpolygons:
            params['avoidpolygons'] = avoidpolygons
        if plate:
            params['plate'] = plate
        if show_fields:
            params['show_fields'] = show_fields
        
        result = self._make_request('driving', params)
        # 添加地址信息到结果中
        result['origin_name'] = origin_name
        result['dest_name'] = dest_name
        return result
    
    def walking_route(self,
                     origin: str,
                     destination: str,
                     alternative_route: Optional[int] = None,
                     show_fields: Optional[str] = None,
                     isindoor: int = 0,
                     origin_city: Optional[str] = None,
                     dest_city: Optional[str] = None) -> Dict:
        """步行路线规划
        
        Args:
            origin: 起点 (可以是经纬度或地址)
            destination: 终点 (可以是经纬度或地址)
            alternative_route: 返回路线条数 (1-3)
            show_fields: 返回字段控制
            isindoor: 是否需要室内算路 (0-不需要, 1-需要)
            origin_city: 起点城市（用于地理编码）
            dest_city: 终点城市（用于地理编码）
            
        Returns:
            路线规划结果
        """
        # 智能解析起点和终点
        origin_coord, origin_name = self.smart_location(origin, origin_city)
        dest_coord, dest_name = self.smart_location(destination, dest_city)
        
        params = {
            'origin': origin_coord,
            'destination': dest_coord,
            'isindoor': isindoor
        }
        
        if alternative_route:
            params['alternative_route'] = alternative_route
        if show_fields:
            params['show_fields'] = show_fields
        
        result = self._make_request('walking', params)
        result['origin_name'] = origin_name
        result['dest_name'] = dest_name
        return result
    
    def bicycling_route(self,
                       origin: str,
                       destination: str,
                       alternative_route: Optional[int] = None,
                       show_fields: Optional[str] = None) -> Dict:
        """骑行路线规划
        
        Args:
            origin: 起点经纬度
            destination: 终点经纬度
            alternative_route: 返回路线条数 (1-3)
            show_fields: 返回字段控制
            
        Returns:
            路线规划结果
        """
        params = {
            'origin': origin,
            'destination': destination
        }
        
        if alternative_route:
            params['alternative_route'] = alternative_route
        if show_fields:
            params['show_fields'] = show_fields
        
        return self._make_request('bicycling', params)
    
    def electrobike_route(self,
                         origin: str,
                         destination: str,
                         alternative_route: Optional[int] = None,
                         show_fields: Optional[str] = None) -> Dict:
        """电动车路线规划
        
        Args:
            origin: 起点经纬度
            destination: 终点经纬度
            alternative_route: 返回路线条数 (1-3)
            show_fields: 返回字段控制
            
        Returns:
            路线规划结果
        """
        params = {
            'origin': origin,
            'destination': destination
        }
        
        if alternative_route:
            params['alternative_route'] = alternative_route
        if show_fields:
            params['show_fields'] = show_fields
        
        return self._make_request('electrobike', params)
    
    def transit_route(self,
                     origin: str,
                     destination: str,
                     city1: str,
                     city2: str,
                     strategy: int = 0,
                     alternative_route: int = 5,
                     nightflag: int = 0,
                     show_fields: Optional[str] = None,
                     date: Optional[str] = None,
                     time: Optional[str] = None) -> Dict:
        """公交路线规划
        
        Args:
            origin: 起点 (可以是经纬度或地址)
            destination: 终点 (可以是经纬度或地址)
            city1: 起点城市编码
            city2: 终点城市编码
            strategy: 换乘策略 (0-推荐, 1-最经济, 2-最少换乘, 3-最少步行, 4-最舒适)
            alternative_route: 返回方案条数 (1-10)
            nightflag: 是否考虑夜班车 (0-不考虑, 1-考虑)
            show_fields: 返回字段控制
            date: 请求日期 (格式: YYYY-MM-DD)
            time: 请求时间 (格式: HH-MM)
            
        Returns:
            路线规划结果
        """
        # 智能解析起点和终点（公交使用city1/city2作为城市参数）
        origin_coord, origin_name = self.smart_location(origin, city1)
        dest_coord, dest_name = self.smart_location(destination, city2)
        
        params = {
            'origin': origin_coord,
            'destination': dest_coord,
            'city1': city1,
            'city2': city2,
            'strategy': strategy,
            'AlternativeRoute': alternative_route,
            'nightflag': nightflag
        }
        
        if show_fields:
            params['show_fields'] = show_fields
        if date:
            params['date'] = date
        if time:
            params['time'] = time
        
        result = self._make_request('transit/integrated', params)
        result['origin_name'] = origin_name
        result['dest_name'] = dest_name
        return result
    
    def format_driving_result(self, result: Dict, show_steps: bool = False, simple: bool = True) -> str:
        """格式化驾车路线结果
        
        Args:
            result: API返回的原始结果
            show_steps: 是否显示详细路线步骤（需要API返回navi字段）
            simple: 是否使用简洁模式（默认True，只显示推荐路线）
            
        Returns:
            格式化后的文本
        """
        if result.get('status') != '1':
            return f"查询失败: {result.get('info', '未知错误')}"
        
        route = result.get('route', {})
        paths = route.get('paths', [])
        
        if not paths:
            return "未找到路线"
        
        output = []
        # 显示地址信息
        origin_name = result.get('origin_name', route.get('origin', ''))
        dest_name = result.get('dest_name', route.get('destination', ''))
        
        output.append(f"{origin_name} -> {dest_name}")
        
        # 简洁模式：只显示第一条（推荐）路线
        if simple:
            path = paths[0]
            distance = float(path.get('distance', 0))
            
            if 'cost' in path:
                cost = path['cost']
                duration = int(cost.get('duration', 0))
                tolls = cost.get('tolls', '0')
                output.append(f"[驾车] 距离 {distance/1000:.1f}公里 | 耗时 {duration//60}分钟 | 过路费 {tolls}元")
            else:
                output.append(f"[驾车] 距离 {distance/1000:.1f}公里")
            
            restriction = path.get('restriction', '0')
            if restriction == '1':
                output.append(f"[注意] 该路线有限行路段")
        else:
            # 完整模式：显示所有路线
            output.append(f"共找到 {len(paths)} 条路线\n")
            
            for idx, path in enumerate(paths, 1):
                distance = float(path.get('distance', 0))
                output.append(f"方案 {idx}:")
                output.append(f"  距离: {distance/1000:.2f} 公里")
                
                if 'cost' in path:
                    cost = path['cost']
                    duration = int(cost.get('duration', 0))
                    tolls = cost.get('tolls', '0')
                    output.append(f"  耗时: {duration//60} 分钟")
                    output.append(f"  过路费: {tolls} 元")
                
                restriction = path.get('restriction', '0')
                if restriction == '1':
                    output.append(f"  [注意] 该路线有限行路段")
                
                output.append("")
        
        # 显示详细路线步骤（仅在show_steps=True时）
        if show_steps and 'steps' in paths[0]:
            output.append(f"\n详细路线指引:")
            steps = paths[0]['steps']
            # 只显示前10步，避免输出过长
            max_steps = min(10, len(steps))
            for step_idx, step in enumerate(steps[:max_steps], 1):
                instruction = step.get('instruction', '')
                road_name = step.get('road_name', '')
                step_distance = float(step.get('step_distance', 0))
                
                if road_name:
                    output.append(f"  {step_idx}. {instruction} ({road_name}, {step_distance/1000:.1f}km)")
                else:
                    output.append(f"  {step_idx}. {instruction} ({step_distance/1000:.1f}km)")
            
            if len(steps) > max_steps:
                output.append(f"  ... 还有 {len(steps) - max_steps} 步（使用--show-all查看完整路线）")
        
        return "\n".join(output)
    
    def format_walking_result(self, result: Dict, show_steps: bool = False, simple: bool = True) -> str:
        """格式化步行路线结果
        
        Args:
            result: API返回的原始结果
            show_steps: 是否显示详细路线步骤
            simple: 是否使用简洁模式（默认True）
            
        Returns:
            格式化后的文本
        """
        if result.get('status') != '1':
            return f"查询失败: {result.get('info', '未知错误')}"
        
        route = result.get('route', {})
        paths = route.get('paths', [])
        
        if not paths:
            return "未找到路线"
        
        output = []
        origin_name = result.get('origin_name', route.get('origin', ''))
        dest_name = result.get('dest_name', route.get('destination', ''))
        
        output.append(f"{origin_name} -> {dest_name}")
        
        # 简洁模式
        if simple:
            path = paths[0]
            distance = float(path.get('distance', 0))
            
            if 'cost' in path:
                cost = path['cost']
                duration = int(cost.get('duration', 0))
                output.append(f"[步行] 距离 {distance/1000:.1f}公里 | 步行约 {duration//60}分钟")
            else:
                output.append(f"[步行] 距离 {distance/1000:.1f}公里")
        else:
            output.append(f"共找到 {len(paths)} 条路线\n")
            for idx, path in enumerate(paths, 1):
                distance = float(path.get('distance', 0))
                output.append(f"方案 {idx}: {distance/1000:.2f}公里")
                if 'cost' in path:
                    duration = int(path['cost'].get('duration', 0))
                    output.append(f"  耗时: {duration//60}分钟")
                output.append("")
        
        return "\n".join(output)
    
    def format_transit_result(self, result: Dict, show_steps: bool = False, simple: bool = True) -> str:
        """格式化公交路线结果
        
        Args:
            result: API返回的原始结果
            show_steps: 是否显示详细换乘步骤
            simple: 是否使用简洁模式（默认True，只显示推荐路线）
            
        Returns:
            格式化后的文本
        """
        if result.get('status') != '1':
            return f"查询失败: {result.get('info', '未知错误')}"
        
        route = result.get('route', {})
        transits = route.get('transits', [])
        
        if not transits:
            return "未找到路线"
        
        output = []
        origin_name = result.get('origin_name', route.get('origin', ''))
        dest_name = result.get('dest_name', route.get('destination', ''))
        
        output.append(f"{origin_name} -> {dest_name}")
        
        # 简洁模式：只显示推荐路线
        if simple:
            transit = transits[0]
            distance = float(transit.get('distance', 0))
            
            if 'cost' in transit:
                cost = transit['cost']
                duration = int(cost.get('duration', 0))
                transit_fee = cost.get('transit_fee', '0')
                output.append(f"[公交] 距离 {distance/1000:.1f}公里 | 耗时 {duration//60}分钟 | 票价 {transit_fee}元")
            
            # 简要显示换乘信息
            if 'segments' in transit:
                bus_lines = []
                for segment in transit['segments']:
                    if 'bus' in segment:
                        bus = segment['bus']
                        for busline in bus.get('buslines', []):
                            bus_lines.append(busline.get('name', ''))
                if bus_lines:
                    output.append(f"   换乘: {' → '.join(bus_lines)}")
        else:
            output.append(f"共找到 {len(transits)} 条路线\n")
            for idx, transit in enumerate(transits[:3], 1):  # 最多显示3条
                distance = float(transit.get('distance', 0))
                output.append(f"方案 {idx}: {distance/1000:.1f}公里")
                if 'cost' in transit:
                    duration = int(transit['cost'].get('duration', 0))
                    transit_fee = transit['cost'].get('transit_fee', '0')
                    output.append(f"  耗时: {duration//60}分钟 | 票价: {transit_fee}元")
                output.append("")
        
        return "\n".join(output)
    
    def search_poi(self, keywords: str, city: Optional[str] = None, types: Optional[str] = None, page_size: int = 10) -> Dict:
        """POI搜索 - 用于旅游规划
        
        Args:
            keywords: 搜索关键词（如"景点"、"美食"、"酒店"）
            city: 城市名称或编码
            types: POI类型编码（如"110000"表示风景名胜，多个用|分隔）
                  常用类型：
                  - 110000: 风景名胜（推荐用于景点搜索）
                  - 050000: 餐饮服务
                  - 100000: 住宿服务
                  - 140000: 科教文化（博物馆等）
            page_size: 返回结果数量（1-25）
            
        Returns:
            POI搜索结果
        """
        params = {
            'key': self.api_key,
            'keywords': keywords,
            'page_size': min(page_size, 25),
            'output': 'json'
        }
        
        if city:
            params['region'] = city
        if types:
            params['types'] = types
        
        try:
            response = requests.get(self.poi_search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == '1':
                return data
            else:
                raise Exception(f"POI搜索失败: {data.get('info', '未知错误')}")
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"POI搜索请求失败: {str(e)}")
    
    def search_attractions(self, city: str, page_size: int = 20) -> Dict:
        """搜索景点（只返回风景名胜类POI）
        
        Args:
            city: 城市名称
            page_size: 返回结果数量（1-25）
            
        Returns:
            景点搜索结果
        """
        # 使用类型编码110000（风景名胜）来精确搜索景点
        return self.search_poi(
            keywords="景点",
            city=city,
            types="110000|140100",  # 风景名胜 | 博物馆
            page_size=page_size
        )
    
    def search_restaurants(self, city: str, page_size: int = 20) -> Dict:
        """搜索餐厅（排除快餐）
        
        Args:
            city: 城市名称
            page_size: 返回结果数量（1-25）
            
        Returns:
            餐厅搜索结果
        """
        # 使用类型编码050100（中餐厅）、050200（外国餐厅）
        return self.search_poi(
            keywords="餐厅",
            city=city,
            types="050100|050200",  # 中餐厅 | 外国餐厅
            page_size=page_size
        )
    
    def format_poi_result(self, result: Dict, simple: bool = True) -> str:
        """格式化POI搜索结果
        
        Args:
            result: POI搜索结果
            simple: 是否使用简洁模式
            
        Returns:
            格式化后的文本
        """
        if result.get('status') != '1':
            return f"搜索失败: {result.get('info', '未知错误')}"
        
        pois = result.get('pois', [])
        if not pois:
            return "未找到相关地点"
        
        output = []
        output.append(f"找到 {len(pois)} 个地点:\n")
        
        for idx, poi in enumerate(pois, 1):
            name = poi.get('name', '')
            address = poi.get('address', '')
            type_name = poi.get('type', '')
            
            if simple:
                output.append(f"{idx}. {name}")
                if address:
                    output.append(f"   {address}")
            else:
                output.append(f"{idx}. {name}")
                output.append(f"   类型: {type_name}")
                output.append(f"   地址: {address}")
                
                # 显示距离（如果有）
                if 'distance' in poi:
                    distance = float(poi['distance'])
                    output.append(f"   距离: {distance/1000:.1f}公里")
                
                output.append("")
        
        return "\n".join(output)


def load_config(config_path: str = None) -> Dict:
    """加载配置文件"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请复制 config.json.example 为 config.json 并填写您的高德地图API Key"
        )
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: Dict, config_path: str = None):
    """保存配置文件"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

