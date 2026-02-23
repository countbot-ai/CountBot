"""安全管理器"""

from pathlib import Path

from cryptography.fernet import Fernet
from loguru import logger


class SecurityManager:
    """安全管理器"""

    def __init__(self, key_file: Path) -> None:
        self.key_file = key_file
        self.cipher = self._load_or_create_cipher()

    def _load_or_create_cipher(self) -> Fernet:
        """加载或创建加密密钥"""
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
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, data: str) -> str:
        """解密数据"""
        if not data:
            return ""
        try:
            return self.cipher.decrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"解密失败: {e}")
            return ""


from backend.modules.config.security import SecurityManager
from backend.utils.paths import DATA_DIR


DATA_DIR_OLD = Path(__file__).parent.parent.parent.parent / "data"  # 保留用于向后兼容
security_manager = SecurityManager(DATA_DIR / ".secret_key")
