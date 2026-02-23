#!/usr/bin/env python3
"""
CountBot 应用启动脚本
开发模式启动，支持热重载
支持本地网络 IP 监控，类似 Vue3 启动模式
"""

import os
import sys
import socket
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


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


def main():
    """启动应用（开发模式）"""
    import uvicorn
    from loguru import logger
    
    # 配置
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    # 获取本地 IP 地址
    local_ips = get_local_ips()
    
    # 打印启动信息
    logger.info("=" * 60)
    logger.info("CountBot 开发模式启动中...")
    logger.info("=" * 60)
    
    try:
        # 启动服务器前显示"服务器启动完成"消息和访问地址
        logger.info("服务器启动完成！")
        logger.info("=" * 60)
        
        # 显示本地访问地址
        logger.info(f"Local:   http://localhost:{port}")
        
        # 显示网络访问地址（如果监听了所有接口或用户明确设置了 0.0.0.0）
        if host in ["0.0.0.0", "::"]:
            if local_ips:
                for ip in local_ips:
                    logger.info(f"Network: http://{ip}:{port}")
            else:
                logger.info("Network: (无法检测到本地 IP 地址)")
                logger.info(f"提示: 请检查网络连接或手动访问 http://<your-ip>:{port}")
        else:
            # 即使监听 127.0.0.1，也显示可用的网络 IP 供参考
            if local_ips:
                logger.info(f"Network: http://{host}:{port}")
                logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
                logger.info(f"可用网络 IP: {', '.join(local_ips)}")
            else:
                logger.info(f"Network: http://{host}:{port}")
                logger.info("提示: 如需从其他设备访问，请设置 HOST=0.0.0.0")
        
        logger.info("-" * 60)
        logger.info("热重载已启用 - 文件更改将自动重启")
        logger.info("按下 Ctrl+C 停止服务器")
        logger.info("=" * 60)
        
        # 启动服务器（开发模式）
        uvicorn.run(
            "backend.app:app",
            host=host,
            port=port,
            reload=True,  # 开发模式启用热重载
            reload_dirs=["backend"],  # 监控 backend 目录
            log_level="debug"
        )


if __name__ == "__main__":
    main()
