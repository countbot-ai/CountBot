"""
网络管理模块 - 负责 IP 地址查询
"""

import socket
import platform


def get_local_ips():
    """
    获取所有本地网络接口的 IPv4 地址
    使用Python 标准库实现，跨平台兼容
    
    Returns:
        list: 包含 IP 地址字符串的列表
    """
    local_ips = []
    
    # 方法1: 通过连接外部地址获取本地 IP（最可靠）
    try:
        # 创建 UDP socket（不会真正发送数据）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # 连接到公共 DNS 服务器（不会真正发送数据包）
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        if local_ip and local_ip != '127.0.0.1':
            local_ips.append(local_ip)
    except Exception:
        pass
    
    # 方法2: 通过主机名获取 IP（备用方法）
    if not local_ips:
        try:
            hostname = socket.gethostname()
            # 获取主机名对应的所有 IPv4 地址
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                # 排除回环地址和链路本地地址
                if ip != '127.0.0.1' and not ip.startswith('169.254.'):
                    if ip not in local_ips:
                        local_ips.append(ip)
        except Exception:
            pass
    
    return local_ips
