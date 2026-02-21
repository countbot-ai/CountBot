"""流量控制器 - 基于令牌桶算法的速率限制

实现标准的令牌桶（Token Bucket）算法，用于：
- 防止用户频繁请求
- 平滑流量峰值
- 保护下游服务

算法特点：
- 恒定速率补充令牌
- 支持突发流量（桶容量）
- 独立的用户级别限流
"""

import time
from typing import Dict, Tuple

from loguru import logger


class RateLimiter:
    """令牌桶算法流量控制器
    
    实现标准的令牌桶算法，为每个用户维护独立的令牌桶。
    令牌以恒定速率补充，请求消耗令牌，无令牌时拒绝请求。
    
    Attributes:
        rate: 令牌补充速率（令牌数/时间窗口）
        per: 时间窗口（秒）
        _buckets: 用户令牌桶映射 {user_id: (tokens, last_update)}
    """
    
    def __init__(self, rate: int = 10, per: int = 60):
        """
        初始化限流器
        
        Args:
            rate: 允许的请求数
            per: 时间窗口（秒）
        """
        self.rate = rate
        self.per = per
        self._buckets: Dict[str, Tuple[float, float]] = {}  # {user_id: (tokens, last_update)}
        
        logger.debug(f"RateLimiter initialized: {rate} requests per {per} seconds")
    
    async def check(self, user_id: str) -> Tuple[bool, str]:
        """
        检查是否允许请求
        
        Args:
            user_id: 用户标识
        
        Returns:
            (是否允许, 错误消息)
        """
        now = time.time()
        
        # 首次请求
        if user_id not in self._buckets:
            self._buckets[user_id] = (self.rate - 1, now)
            return True, ""
        
        tokens, last_update = self._buckets[user_id]
        
        # 补充令牌
        elapsed = now - last_update
        tokens = min(self.rate, tokens + elapsed * (self.rate / self.per))
        
        # 检查是否有足够令牌
        if tokens >= 1:
            self._buckets[user_id] = (tokens - 1, now)
            return True, ""
        else:
            # 计算需要等待的时间
            wait_time = int((1 - tokens) * (self.per / self.rate))
            error_msg = f"发送太频繁，请等待 {wait_time} 秒后再试"
            logger.warning(f"Rate limit exceeded for user {user_id}, wait {wait_time}s")
            return False, error_msg
    
    def reset(self, user_id: str):
        """重置用户的限流状态"""
        if user_id in self._buckets:
            del self._buckets[user_id]
            logger.info(f"Rate limit reset for user {user_id}")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'active_users': len(self._buckets),
            'rate': self.rate,
            'per': self.per,
        }
