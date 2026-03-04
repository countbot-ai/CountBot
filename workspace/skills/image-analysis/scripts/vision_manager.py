"""图像识别与理解管理器"""
import os
import json
import base64
import requests
from typing import Dict, List, Optional, Union
from pathlib import Path


class VisionManager:
    """图像识别管理器"""
    
    def __init__(self, config: Dict):
        """初始化"""
        self.config = config
        self.default_model = config.get('default_model', 'zhipu')
        
    def _encode_image(self, image_path: str) -> str:
        """将本地图片转换为 base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _is_local_file(self, path: str) -> bool:
        """判断是否为本地文件"""
        return os.path.exists(path) or (not path.startswith('http://') and not path.startswith('https://'))
    
    def _prepare_image_url(self, image_path: str) -> str:
        """准备图片 URL：本地文件转 Base64，网络 URL 直接返回"""
        if self._is_local_file(image_path):
            # 本地文件，转换为 base64 Data URL
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp'
            }.get(ext, 'image/jpeg')
            
            base64_image = self._encode_image(image_path)
            # 格式：data:[MIME_type];base64,{base64_image}
            return f"data:{mime_type};base64,{base64_image}"
        else:
            # 网络 URL，直接返回
            return image_path
    
    def analyze_with_zhipu(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        videos: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        thinking: bool = False,
        stream: bool = False
    ) -> Dict:
        """使用智谱 GLM-4V 分析"""
        zhipu_config = self.config.get('zhipu', {})
        api_key = zhipu_config.get('api_key')
        model = zhipu_config.get('model', 'glm-4.6v-flash')
        base_url = zhipu_config.get('base_url', 'https://open.bigmodel.cn/api/paas/v4/chat/completions')
        
        if not api_key:
            raise ValueError("智谱 API Key 未配置")
        
        # 构建消息内容
        content = []
        
        # 添加图片
        if images:
            for image in images:
                image_url = self._prepare_image_url(image)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
        
        # 添加视频
        if videos:
            for video in videos:
                content.append({
                    "type": "video_url",
                    "video_url": {"url": video}
                })
        
        # 添加文件
        if files:
            for file in files:
                content.append({
                    "type": "file_url",
                    "file_url": {"url": file}
                })
        
        # 添加文本提示
        content.append({
            "type": "text",
            "text": prompt
        })
        
        # 构建请求
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        # 添加思考模式
        if thinking:
            payload["thinking"] = {"type": "enabled"}
        
        # 添加流式输出
        if stream:
            payload["stream"] = True
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def analyze_with_qwen(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        videos: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        stream: bool = False
    ) -> Dict:
        """使用千问 Qwen-VL 分析"""
        qwen_config = self.config.get('qwen', {})
        api_key = qwen_config.get('api_key')
        model = qwen_config.get('model', 'qwen3-vl-plus')
        base_url = qwen_config.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')
        
        if not api_key:
            raise ValueError("千问 API Key 未配置")
        
        # 千问不支持同时处理多种类型
        content_types = sum([bool(images), bool(videos), bool(files)])
        if content_types > 1:
            raise ValueError("千问模型不支持同时处理图片、视频和文件，请只选择一种类型")
        
        # 构建消息内容
        content = []
        
        # 添加图片
        if images:
            for image in images:
                image_url = self._prepare_image_url(image)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
        
        # 添加视频
        if videos:
            for video in videos:
                content.append({
                    "type": "video_url",
                    "video_url": {"url": video}
                })
        
        # 添加文件
        if files:
            for file in files:
                content.append({
                    "type": "file_url",
                    "file_url": {"url": file}
                })
        
        # 添加文本提示
        content.append({
            "type": "text",
            "text": prompt
        })
        
        # 构建请求
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        # 添加流式输出
        if stream:
            payload["stream"] = True
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def analyze(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        videos: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: Optional[str] = None,
        thinking: bool = False,
        stream: bool = False
    ) -> Dict:
        """分析图片/视频/文件，自动路由到对应模型"""
        use_model = model or self.default_model
        
        if use_model == 'zhipu':
            return self.analyze_with_zhipu(prompt, images, videos, files, thinking, stream)
        elif use_model == 'qwen':
            if thinking:
                print("警告：千问模型不支持思考模式，将忽略该参数")
            return self.analyze_with_qwen(prompt, images, videos, files, stream)
        else:
            raise ValueError(f"不支持的模型: {use_model}，请选择 'zhipu' 或 'qwen'")
    
    def format_result(self, result: Dict, show_usage: bool = False) -> str:
        """格式化输出结果"""
        try:
            content = result['choices'][0]['message']['content']
            output = f"分析结果：\n{content}"
            
            if show_usage and 'usage' in result:
                usage = result['usage']
                output += f"\n\nToken 使用：输入 {usage.get('prompt_tokens', 0)} | 输出 {usage.get('completion_tokens', 0)} | 总计 {usage.get('total_tokens', 0)}"
            
            return output
        except (KeyError, IndexError) as e:
            return f"解析结果失败: {str(e)}\n原始结果: {json.dumps(result, ensure_ascii=False, indent=2)}"


def load_config(config_path: str = None) -> Dict:
    """加载配置文件"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)
