"""安全管理器 - cryptography 可选依赖"""

from pathlib import Path

from loguru import logger

# 尝试导入 cryptography，如果不可用则优雅降级
try:
    from cryptography.fernet import Fernet
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    logger.warning("cryptography 未安装，加密功能将被禁用")
    CRYPTOGRAPHY_AVAILABLE = False
    Fernet = None


class SecurityManager:
    """安全管理器"""

    def __init__(self, key_file: Path) -> None:
        self.key_file = key_file
        self.cipher = self._load_or_create_cipher() if CRYPTOGRAPHY_AVAILABLE else None

    def _load_or_create_cipher(self):
        """加载或创建加密密钥"""
        if not CRYPTOGRAPHY_AVAILABLE:
            return None
            
        if self.key_file.exists():
            key = self.key_file.read_bytes()
            logger.info(f"加载加密密钥: {self.key_file}")
        else:
            key = Fernet.generate_key()
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            self.key_file.write_bytes(key)
            logger.info(f"生成新加密密钥: {self.key_file}")
        return Fernet(key)

    def encrypt(self, data: str) -> str:
        """加密数据"""
        if not data:
            return ""
        if not CRYPTOGRAPHY_AVAILABLE or not self.cipher:
            logger.debug("cryptography 不可用，返回原始数据")
            return data
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, data: str) -> str:
        """解密数据"""
        if not data:
            return ""
        if not CRYPTOGRAPHY_AVAILABLE or not self.cipher:
            logger.debug("cryptography 不可用，返回原始数据")
            return data
        try:
            return self.cipher.decrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"解密失败: {e}")
            return ""


# 延迟初始化 security_manager，避免模块导入时就触发依赖检查
_security_manager = None


def get_security_manager():
    """获取 SecurityManager 单例"""
    global _security_manager
    if _security_manager is None:
        from backend.utils.paths import DATA_DIR
        _security_manager = SecurityManager(DATA_DIR / ".secret_key")
    return _security_manager
