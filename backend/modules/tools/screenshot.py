"""截图工具

提供跨平台截图功能：
- 桌面截图（使用 mss 库）
- 网页截图（使用 playwright 库）
"""

import asyncio
import base64
import os
import platform
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from backend.modules.tools.base import Tool


class ScreenshotTool(Tool):
    """通用截图工具 - 支持桌面截图和网页截图，跨平台兼容"""

    def __init__(
        self,
        workspace: Path,
        default_output_dir: str = "screenshots",
        max_width: int = 1920,
        max_height: int = 1080,
    ):
        """
        初始化截图工具
        
        Args:
            workspace: 工作空间根目录
            default_output_dir: 默认输出目录（相对于工作空间）
            max_width: 网页截图最大宽度
            max_height: 网页截图最大高度
        """
        self.workspace = workspace.resolve()
        self.default_output_dir = default_output_dir
        self.max_width = max_width
        self.max_height = max_height
        
        logger.debug(
            f"ScreenshotTool initialized: workspace={self.workspace}, "
            f"output_dir={default_output_dir}"
        )


    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "Capture desktop or webpage screenshots"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["desktop", "webpage"],
                    "description": "Mode (desktop/webpage)",
                },
                "url": {
                    "type": "string",
                    "description": "URL (webpage mode)",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output path (optional)",
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor number (desktop)",
                    "minimum": 0,
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Full page (webpage)",
                },
                "viewport_width": {
                    "type": "integer",
                    "description": "Viewport width",
                    "minimum": 320,
                    "maximum": 3840,
                },
                "viewport_height": {
                    "type": "integer",
                    "description": "Viewport height",
                    "minimum": 240,
                    "maximum": 2160,
                },
                "wait_time": {
                    "type": "integer",
                    "description": "Wait time (ms)",
                    "minimum": 0,
                    "maximum": 30000,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout (ms)",
                    "minimum": 5000,
                    "maximum": 120000,
                },
            },
            "required": ["mode"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """
        执行截图
        
        Args:
            **kwargs: 截图参数
                - mode (str): 截图模式（desktop 或 webpage）
                - url (str): 网页 URL（webpage 模式必需）
                - output_path (str): 输出文件路径（可选）
                - monitor (int): 显示器编号（desktop 模式，可选）
                - full_page (bool): 是否全页截图（webpage 模式，可选）
                - viewport_width (int): 视口宽度（webpage 模式，可选）
                - viewport_height (int): 视口高度（webpage 模式，可选）
                - wait_time (int): 等待时间（webpage 模式，可选）
            
        Returns:
            str: 截图结果信息或错误信息
        """
        mode = kwargs.get("mode", "")
        
        if not mode:
            return "Error: mode parameter is required (desktop or webpage)"
        
        if mode == "desktop":
            return await self._capture_desktop(**kwargs)
        elif mode == "webpage":
            return await self._capture_webpage(**kwargs)
        else:
            return f"Error: Invalid mode '{mode}'. Must be 'desktop' or 'webpage'"

    async def _capture_desktop(self, **kwargs: Any) -> str:
        """
        捕获桌面截图
        
        使用 mss 库进行跨平台桌面截图。
        
        Args:
            **kwargs: 截图参数
            
        Returns:
            str: 截图结果信息或错误信息
        """
        try:
            import mss
            import mss.tools
        except ImportError:
            return (
                "Error: mss library not installed. "
                "Install it with: pip install mss"
            )
        
        monitor_num = kwargs.get("monitor", 0)
        output_path = kwargs.get("output_path")
        
        try:
            with mss.mss() as sct:
                # 获取显示器信息
                monitors = sct.monitors
                
                if monitor_num < 0 or monitor_num >= len(monitors):
                    return (
                        f"Error: Invalid monitor number {monitor_num}. "
                        f"Available monitors: 0-{len(monitors) - 1}"
                    )
                
                # 选择显示器（0 表示所有显示器）
                monitor = monitors[monitor_num]
                
                logger.info(
                    f"捕获桌面截图: monitor={monitor_num}, "
                    f"size={monitor['width']}x{monitor['height']}"
                )
                
                # 截图
                screenshot = sct.grab(monitor)
                
                # 生成输出路径
                if not output_path:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = f"{self.default_output_dir}/desktop_{timestamp}.png"
                
                # 确保输出路径在工作空间内
                full_path = (self.workspace / output_path).resolve()
                
                # 创建输出目录
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 保存截图
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(full_path))
                
                # 获取文件大小
                file_size = full_path.stat().st_size
                
                logger.info(f"桌面截图已保存: {output_path} ({file_size} bytes)")
                
                return (
                    f"Desktop screenshot captured successfully!\n"
                    f"Path: {output_path}\n"
                    f"Size: {screenshot.width}x{screenshot.height}\n"
                    f"File size: {file_size:,} bytes\n"
                    f"Monitor: {monitor_num}"
                )
                
        except Exception as e:
            logger.error(f"桌面截图失败: {e}")
            return f"Error capturing desktop screenshot: {str(e)}"

    async def _capture_webpage(self, **kwargs: Any) -> str:
        """
        捕获网页截图
        
        使用 playwright 库进行网页截图。
        
        Args:
            **kwargs: 截图参数
            
        Returns:
            str: 截图结果信息或错误信息
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return (
                "Error: playwright library not installed. "
                "Install it with: pip install playwright && playwright install chromium"
            )
        
        url = kwargs.get("url", "")
        output_path = kwargs.get("output_path")
        full_page = kwargs.get("full_page", False)
        viewport_width = kwargs.get("viewport_width", 1280)
        viewport_height = kwargs.get("viewport_height", 720)
        wait_time = kwargs.get("wait_time", 1000)
        timeout = kwargs.get("timeout", 30000)
        
        if not url:
            return "Error: url parameter is required for webpage mode"
        
        # 验证 URL
        if not url.startswith(("http://", "https://")):
            return f"Error: Invalid URL '{url}'. Must start with http:// or https://"
        
        try:
            logger.info(f"捕获网页截图: url={url}, full_page={full_page}")
            
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(headless=True)
                
                # 创建上下文和页面
                context = await browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height}
                )
                page = await context.new_page()
                
                # 访问 URL
                await page.goto(url, wait_until="networkidle", timeout=timeout)
                
                # 等待指定时间
                if wait_time > 0:
                    await asyncio.sleep(wait_time / 1000)
                
                # 生成输出路径
                if not output_path:
                    from datetime import datetime
                    from urllib.parse import urlparse
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    domain = urlparse(url).netloc.replace(".", "_")
                    output_path = f"{self.default_output_dir}/webpage_{domain}_{timestamp}.png"
                
                # 确保输出路径在工作空间内
                full_path = (self.workspace / output_path).resolve()
                
                # 创建输出目录
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 截图
                await page.screenshot(
                    path=str(full_path),
                    full_page=full_page,
                )
                
                # 获取页面信息
                page_title = await page.title()
                
                # 关闭浏览器
                await browser.close()
                
                # 获取文件大小
                file_size = full_path.stat().st_size
                
                logger.info(f"网页截图已保存: {output_path} ({file_size} bytes)")
                
                return (
                    f"Webpage screenshot captured successfully!\n"
                    f"URL: {url}\n"
                    f"Title: {page_title}\n"
                    f"Path: {output_path}\n"
                    f"Viewport: {viewport_width}x{viewport_height}\n"
                    f"Full page: {full_page}\n"
                    f"File size: {file_size:,} bytes"
                )
                
        except Exception as e:
            logger.error(f"网页截图失败: {e}")
            return f"Error capturing webpage screenshot: {str(e)}"
