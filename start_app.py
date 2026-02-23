#!/usr/bin/env python3
"""
CountBot 应用启动脚本
生产模式启动，自动打开浏览器
支持本地网络 IP 监控，类似 Vue3 启动模式
"""

import os
import sys
import webbrowser
import threading
import socket
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 跨平台 SSL 兼容性处理（macOS 需要额外配置证书）
from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()


def get_local_ips():
    """
    获取所有本地网络接口的 IPv4 地址
    类似 Vue3 开发服务器的 IP 检测功能
    
    Returns:
        list: 包含 IP 地址字符串的列表
    """
    local_ips = []
    
    # 方法1: 使用 netifaces（如果可用）
    try:
        import netifaces
        
        for interface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info['addr']
                        # 排除本地回环和链路本地地址
                        if ip != '127.0.0.1' and not ip.startswith('169.254.'):
                            local_ips.append(ip)
            except ValueError:
                continue
    except ImportError:
        # netifaces 不可用，使用备用方法
        pass
    
    # 方法2: 如果没有找到地址，使用 socket 方法
    if not local_ips:
        try:
            # 通过连接外部服务器获取本地 IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip and local_ip != '127.0.0.1':
                local_ips.append(local_ip)
        except Exception:
            pass
    
    # 方法3: 尝试获取主机名对应的 IP
    if not local_ips:
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip != '127.0.0.1' and ip not in local_ips:
                    local_ips.append(ip)
        except Exception:
            pass
    
    # 去重并返回
    return list(dict.fromkeys(local_ips))


def open_browser_delayed(url: str, delay: float = 2.0) -> None:
    """
    延迟打开浏览器
    
    Args:
        url: 要打开的 URL
        delay: 延迟时间（秒）
    """
    def _open():
        import time
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 静默失败，不影响服务器启动
    
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    """启动应用"""
    import uvicorn
    from backend.utils.logger import setup_logger
    from backend.utils.process_manager import setup_graceful_shutdown
    from loguru import logger
    
    # 初始化日志系统
    setup_logger()
    
    # 设置优雅关闭机制（包括清理孤儿进程、写入 PID、注册信号处理器）
    process_manager = setup_graceful_shutdown(logger=logger)
    
    # 配置
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8002"))
    
    # 确保环境变量与实际绑定地址一致（供 app.py 读取）
    os.environ["HOST"] = host
    
    # 获取本地 IP 地址
    local_ips = get_local_ips()
    
    # 打印启动信息
    logger.info("=" * 60)
    logger.info("CountBot 启动中...")
    logger.info("=" * 60)
    
    try:
        # 启动服务器前显示"服务器启动完成"消息和访问地址
        # 这样地址会在视觉上显示在启动完成之后
        logger.info("服务器启动完成！")
        logger.info("=" * 60)
        
        # 显示本地访问地址
        logger.info(f"Local:   http://localhost:{port}")
        
        # 显示网络访问地址（如果监听了所有接口）
        if host in ["0.0.0.0", "::"]:
            if local_ips:
                for ip in local_ips:
                    logger.info(f"Network: http://{ip}:{port}")
            else:
                logger.info("Network: (无法检测到本地 IP 地址)")
                logger.info(f"提示: 请检查网络连接或手动访问 http://<your-ip>:{port}")
        else:
            logger.info(f"Network: http://{host}:{port}")
            logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
        
        logger.info("-" * 60)
        logger.info("按下 Ctrl+C 停止服务器")
        logger.info("=" * 60)
        
        # 延迟打开浏览器
        open_browser_delayed(f"http://localhost:{port}")
        
        # 启动服务器
        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=False,  # 生产模式不启用热重载
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        # 确保清理 PID 文件
        process_manager.remove_pid_file()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    main()
