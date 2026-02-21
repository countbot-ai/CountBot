"""跨平台 SSL 证书兼容性处理

- macOS: Python 默认不使用系统 SSL 证书，通过 certifi 指定证书路径
- Windows: 将系统证书库注入 Python SSL 上下文，支持企业自签名证书
- Linux: 通常无需额外处理
"""

import os
import ssl
import sys

from loguru import logger


def ensure_ssl_certificates() -> None:
    """根据当前平台配置 SSL 证书"""
    if sys.platform == "darwin":
        _configure_macos()
    elif sys.platform == "win32":
        _configure_windows()


def _configure_macos() -> None:
    """macOS: 通过 certifi 注入 CA 证书"""
    try:
        import certifi
    except ImportError:
        logger.warning(
            "certifi 未安装，macOS 上可能出现 SSL 证书验证失败。"
            "请运行: pip install certifi"
        )
        return

    cert_path = certifi.where()
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ.setdefault(var, cert_path)
    logger.debug(f"macOS SSL 证书已配置: {cert_path}")


def _configure_windows() -> None:
    """Windows: 从系统证书库加载证书到 SSL 上下文

    使企业环境中安装的自签名证书能被 Python ssl 模块信任。
    """
    try:
        ctx = ssl.create_default_context()

        count = 0
        for store_name in ("CA", "ROOT", "MY"):
            try:
                certs = ssl.enum_certificates(store_name)
                for cert, _encoding, trust in certs:
                    if trust is True or ssl.Purpose.SERVER_AUTH.oid in (trust or ()):
                        try:
                            ctx.load_verify_locations(
                                cadata=ssl.DER_cert_to_PEM_cert(cert)
                            )
                            count += 1
                        except ssl.SSLError:
                            pass
            except PermissionError:
                logger.debug(f"无权读取 Windows 证书库 '{store_name}'")

        if count:
            logger.debug(f"Windows SSL: 从系统证书库加载了 {count} 个证书")
        else:
            logger.debug("Windows SSL: 未加载额外的系统证书")
    except Exception as e:
        logger.debug(f"Windows SSL 证书注入跳过: {e}")
