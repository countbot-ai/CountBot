#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百度 AI 搜索管理器"""
import requests
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any


class BaiduSearchManager:
    """百度 AI 搜索管理器，支持网页搜索、百科、秒懂百科、AI 智能生成"""
    
    API_ENDPOINTS = {
        "web_search": "https://qianfan.baidubce.com/v2/ai_search/web_search",
        "baike": "https://appbuilder.baidu.com/v2/baike/lemma/get_content",
        "miaodong_baike": "https://appbuilder.baidu.com/v2/baike/second_know/search_video",
        "ai_chat": "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    }
    
    DEFAULT_API_TYPE = "web_search"
    
    def __init__(self, api_key: Optional[str] = None, config_file: Optional[str] = None):
        """初始化搜索管理器"""
        self.api_key = api_key
        
        # 未提供 api_key 时从配置文件加载
        if not self.api_key:
            # 默认配置文件路径
            if config_file is None:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                config_file = os.path.join(script_dir, 'config.json')
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.api_key = config.get('api_key')
            except FileNotFoundError:
                raise ValueError(f"Config file not found: {config_file}. Please create it with your API key.")
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON in config file: {config_file}")
        
        if not self.api_key:
            raise ValueError("API key is required. Set it in config.json or pass as parameter.")
        
        self.headers = {
            "X-Appbuilder-Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def get_current_date_context(self) -> Dict[str, Any]:
        """获取当前日期上下文"""
        now = datetime.now()
        return {
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M:%S'),
            'weekday': now.strftime('%A'),
            'year': now.year,
            'month': now.month,
            'day': now.day,
        }
    
    def search(
        self,
        query: str,
        api_type: str = "web_search",
        max_results: int = 10,
        resource_types: Optional[List[Dict[str, Any]]] = None,
        sites: Optional[List[str]] = None,
        recency_filter: Optional[str] = None,
        safe_search: bool = False,
        include_date: bool = True
    ) -> Dict[str, Any]:
        """执行搜索"""
        # 校验 API 类型
        if api_type not in self.API_ENDPOINTS:
            raise ValueError(f"Invalid api_type: {api_type}. Must be one of {list(self.API_ENDPOINTS.keys())}")
        
        # 路由到对应搜索方法
        if api_type == "web_search":
            return self._search_web(query, max_results, resource_types, sites, recency_filter, safe_search, include_date)
        elif api_type == "baike":
            return self._search_baike(query, include_date)
        elif api_type == "miaodong_baike":
            return self._search_miaodong_baike(query, include_date)
        elif api_type == "ai_chat":
            return self._search_ai_chat(query, max_results, include_date)
    
    def _search_web(
        self,
        query: str,
        max_results: int,
        resource_types: Optional[List[Dict[str, Any]]],
        sites: Optional[List[str]],
        recency_filter: Optional[str],
        safe_search: bool,
        include_date: bool
    ) -> Dict[str, Any]:
        """网页搜索"""
        # 默认资源类型
        if resource_types is None:
            resource_types = [{"type": "web", "top_k": min(max_results, 50)}]
        
        # 构建请求
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": query[:72]  # 最长 72 字符
                }
            ],
            "search_source": "baidu_search_v2",
            "resource_type_filter": resource_types,
            "safe_search": safe_search
        }
        
        # 搜索过滤
        search_filter = {}
        if sites:
            search_filter["match"] = {"site": sites[:100]}  # 最多 100 个站点
        
        if recency_filter:
            payload["search_recency_filter"] = recency_filter
        
        if search_filter:
            payload["search_filter"] = search_filter
        
        try:
            # 发送请求
            response = requests.post(
                self.API_ENDPOINTS["web_search"],
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            # 解析响应
            data = response.json()
            
            # 检查错误
            if "code" in data:
                raise Exception(f"API Error {data['code']}: {data.get('message', 'Unknown error')}")
            
            # 提取结果
            references = data.get("references", [])
            results = []
            
            for ref in references[:max_results]:
                result = {
                    "id": ref.get("id"),
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "snippet": ref.get("content", ""),
                    "date": ref.get("date"),
                    "type": ref.get("type", "web"),
                    "website": ref.get("website"),
                    "icon": ref.get("icon"),
                    "web_anchor": ref.get("web_anchor")
                }
                
                # 附加类型特定数据
                if ref.get("image"):
                    result["image"] = ref["image"]
                if ref.get("video"):
                    result["video"] = ref["video"]
                if ref.get("is_aladdin"):
                    result["is_aladdin"] = True
                    result["aladdin"] = ref.get("aladdin")
                
                results.append(result)
            
            # 构建返回
            if include_date:
                return {
                    "api_type": "web_search",
                    "query": query,
                    "date_context": self.get_current_date_context(),
                    "results": results,
                    "count": len(results),
                    "request_id": data.get("request_id")
                }
            
            return results
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def _search_baike(self, query: str, include_date: bool) -> Dict[str, Any]:
        """百度百科搜索"""
        params = {
            "search_type": "lemmaTitle",
            "search_key": query
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(
                self.API_ENDPOINTS["baike"],
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查错误
            if "code" in data and data["code"] != 0:
                raise Exception(f"API Error {data.get('code')}: {data.get('message', 'Unknown error')}")
            
            # 提取百科内容
            result_data = data.get("result", {})
            result = {
                "lemma_id": result_data.get("lemma_id"),
                "title": result_data.get("lemma_title", ""),
                "description": result_data.get("lemma_desc", ""),
                "url": result_data.get("url", ""),
                "summary": result_data.get("summary", ""),
                "abstract_plain": result_data.get("abstract_plain", ""),
                "abstract_html": result_data.get("abstract_html", "")
            }
            
            if include_date:
                return {
                    "api_type": "baike",
                    "query": query,
                    "date_context": self.get_current_date_context(),
                    "entry": result,
                    "request_id": data.get("request_id")
                }
            
            return result
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def _search_miaodong_baike(self, query: str, include_date: bool) -> Dict[str, Any]:
        """秒懂百科搜索"""
        params = {
            "search_type": "lemmaTitle",
            "search_key": query
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(
                self.API_ENDPOINTS["miaodong_baike"],
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查错误
            if "code" in data and data["code"] != 0:
                raise Exception(f"API Error {data.get('code')}: {data.get('message', 'Unknown error')}")
            
            # 提取视频数据
            result_list = data.get("result", [])
            if not result_list:
                raise Exception("No video found")
            
            video_data = result_list[0]
            result = {
                "lemma_id": video_data.get("lemma_id"),
                "title": video_data.get("lemma_title", ""),
                "description": video_data.get("lemma_desc", ""),
                "second_title": video_data.get("second_title", ""),
                "url": f"https://baike.baidu.com/item/{video_data.get('lemma_title', '')}",
                "video_url": video_data.get("play_url_mp4", ""),
                "forever_video_url": video_data.get("forever_play_url_mp4", ""),
                "audio_url": video_data.get("play_url_mp3", ""),
                "thumbnail": video_data.get("cover_pic_url", ""),
                "duration": video_data.get("play_time"),
                "is_vertical": video_data.get("is_vertical") == 1
            }
            
            if include_date:
                return {
                    "api_type": "miaodong_baike",
                    "query": query,
                    "date_context": self.get_current_date_context(),
                    "video": result,
                    "request_id": data.get("request_id")
                }
            
            return result
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def _search_ai_chat(self, query: str, max_results: int, include_date: bool) -> Dict[str, Any]:
        """AI 智能搜索生成"""
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": query
                }
            ],
            "search_source": "baidu_search_v1",
            "resource_type_filter": [
                {"type": "web", "top_k": min(max_results, 10)},
                {"type": "image", "top_k": 4},
                {"type": "video", "top_k": 4}
            ],
            "search_recency_filter": "year",
            "stream": False,
            "model": "ernie-4.5-turbo-32k",
            "enable_deep_search": False,
            "enable_followup_query": False,
            "temperature": 0.11,
            "top_p": 0.55,
            "search_mode": "auto",
            "enable_reasoning": True
        }
        
        try:
            response = requests.post(
                self.API_ENDPOINTS["ai_chat"],
                headers=self.headers,
                json=payload,
                timeout=60  # AI 生成需要更长超时
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "code" in data:
                raise Exception(f"API Error {data['code']}: {data.get('message', 'Unknown error')}")
            
            # 提取 AI 生成内容
            choices = data.get("choices", [])
            result = {
                "answer": "",
                "sources": [],
                "model": data.get("model", ""),
                "usage": data.get("usage", {})
            }
            
            if choices:
                message = choices[0].get("message", {})
                result["answer"] = message.get("content", "")
                result["sources"] = message.get("search_results", [])
            
            if include_date:
                return {
                    "api_type": "ai_chat",
                    "query": query,
                    "date_context": self.get_current_date_context(),
                    "result": result,
                    "request_id": data.get("id")
                }
            
            return result
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def search_with_time_range(
        self,
        query: str,
        start_date: str,
        end_date: str,
        max_results: int = 10,
        include_date: bool = True
    ) -> Dict[str, Any]:
        """按时间范围搜索"""
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": query[:72]
                }
            ],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": min(max_results, 50)}],
            "search_filter": {
                "range": {
                    "page_time": {
                        "gte": start_date,
                        "lte": end_date
                    }
                }
            }
        }
        
        try:
            response = requests.post(
                self.API_ENDPOINTS["web_search"],
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "code" in data:
                raise Exception(f"API Error {data['code']}: {data.get('message', 'Unknown error')}")
            
            references = data.get("references", [])
            results = []
            
            for ref in references[:max_results]:
                result = {
                    "id": ref.get("id"),
                    "title": ref.get("title", ""),
                    "url": ref.get("url", ""),
                    "snippet": ref.get("content", ""),
                    "date": ref.get("date"),
                    "type": ref.get("type", "web"),
                    "website": ref.get("website")
                }
                results.append(result)
            
            if include_date:
                return {
                    "query": query,
                    "date_context": self.get_current_date_context(),
                    "time_range": {"start": start_date, "end": end_date},
                    "results": results,
                    "count": len(results),
                    "request_id": data.get("request_id")
                }
            
            return results
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")


if __name__ == "__main__":
    # 简单测试
    try:
        manager = BaiduSearchManager()
        result = manager.search("百度千帆平台", max_results=3)
        
        print(f"Query: {result['query']}")
        print(f"Date: {result['date_context']['date']}")
        print(f"Results: {result['count']}\n")
        
        for item in result['results']:
            print(f"[{item['id']}] {item['title']}")
            print(f"    {item['url']}")
            if item.get('snippet'):
                print(f"    {item['snippet'][:100]}...")
            print()
            
    except Exception as e:
        print(f"Error: {e}")
