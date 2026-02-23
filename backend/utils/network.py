"""
网络管理模块 - 负责ip地址查询
"""

import socket


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

