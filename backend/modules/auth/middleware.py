"""远程访问认证中间件

核心逻辑：
- 本地直连（127.0.0.1/::1，无代理）→ 放行
- 反向代理后面 → 要求认证（即使 socket IP 是 127.0.0.1）
- 远程访问 → 要求认证

安全机制：
1. TCP 层面判断：读取 socket.client.host（操作系统提供，无法伪造）
2. 代理检测：识别是否在反向代理后面
   - 有代理头 → 在代理后面 → socket IP 不可信 → 要求认证
   - 无代理头 → 直接连接 → socket IP 可信 → 检查是否本地
3. 攻击者无法绕过：
   - 直接连接：socket IP 由 OS 提供，无法伪造
   - 通过代理：会被检测到代理头，要求认证
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from loguru import logger

from backend.modules.auth.utils import validate_session

# 不需要认证的路径前缀
AUTH_WHITELIST = [
    "/api/auth/",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/login",          # 登录页面
    "/assets/",        # 前端静态资源（JS/CSS/图片）
]

# 本地 IP 地址（仅匹配 TCP socket 层的对端 IP）
LOCAL_IPS = {"127.0.0.1", "::1"}

# 代理相关的 HTTP 头（如果存在这些头，说明请求经过了代理）
PROXY_HEADERS = {
    "x-forwarded-for",
    "x-real-ip",
    "x-forwarded-host",
    "x-forwarded-proto",
    "forwarded",
    "via",
    "x-forwarded-server",
    "x-cluster-client-ip",
    "cf-connecting-ip",  # Cloudflare
    "true-client-ip",    # Cloudflare
}


def _get_real_client_ip(request: Request) -> str | None:
    """获取真实的客户端 IP（仅从 TCP socket 层获取，不信任任何 HTTP 头）
    
    返回:
        str: 客户端 IP 地址
        None: 无法获取（异常情况）
    """
    if request.client is None:
        logger.warning("Unable to get client IP: request.client is None")
        return None
    
    # 直接从 TCP socket 获取对端 IP
    client_ip = request.client.host
    
    if not client_ip:
        logger.warning("Unable to get client IP: client.host is empty")
        return None
    
    return client_ip


def _has_proxy_headers(request: Request) -> bool:
    """检测请求是否包含代理相关的 HTTP 头
    
    用途：判断应用是否在反向代理后面
    - 有代理头 → 在反向代理后面 → socket IP 是代理 IP，不是真实客户端 IP
    - 无代理头 → 直接连接 → socket IP 是真实客户端 IP
    
    注意：这不是为了防止伪造（攻击者可以添加这些头），
         而是为了识别部署架构，决定是否信任 socket IP
    """
    request_headers = {k.lower() for k in request.headers.keys()}
    return bool(PROXY_HEADERS & request_headers)


def _is_local_request(request: Request) -> bool:
    """判断是否为本地请求（TCP 层面判断）
    
    安全策略：
    1. 直接部署：socket IP 是真实 IP，127.0.0.1/::1 = 本地
    2. 反向代理：socket IP 是代理 IP（通常是 127.0.0.1），但有代理头
       - 此时不能信任 socket IP，必须要求认证
    
    核心逻辑：
    - 如果有代理头 → 说明在反向代理后面 → 不能信任 socket IP → 拒绝本地判断
    - 如果无代理头 → 直接部署 → socket IP 可信 → 检查是否为 127.0.0.1/::1
    
    返回:
        True: 确认是本地请求（直接访问 127.0.0.1，无代理）
        False: 远程请求或在反向代理后面
    """
    # 1. 获取 TCP socket 层的 IP
    client_ip = _get_real_client_ip(request)
    if client_ip is None:
        logger.warning("Cannot determine client IP, denying local access")
        return False
    
    # 2. 检测是否在反向代理后面
    if _has_proxy_headers(request):
        # 在反向代理后面，即使 socket IP 是 127.0.0.1 也不能信任
        # 因为这是代理服务器的 IP，不是真实客户端 IP
        logger.debug(f"Proxy detected (socket IP: {client_ip}), treating as remote")
        return False
    
    # 3. 直接部署，socket IP 可信，检查是否为本地 IP
    is_local = client_ip in LOCAL_IPS
    
    if is_local:
        logger.debug(f"Local request confirmed: {client_ip} (direct connection)")
    else:
        logger.debug(f"Remote request: {client_ip} (direct connection)")
    
    return is_local


def _is_whitelisted(path: str) -> bool:
    """判断路径是否在白名单中"""
    for prefix in AUTH_WHITELIST:
        if path.startswith(prefix):
            return True
    return False


def _get_token_from_request(request: Request) -> str | None:
    """从请求中提取 session token（Cookie 或 Header）"""
    # 1. 从 Cookie 获取
    token = request.cookies.get("CountBot_token")
    if token:
        return token
    # 2. 从 Authorization header 获取
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """远程访问认证中间件"""

    def __init__(self, app, get_password_hash_fn=None):
        super().__init__(app)
        self._get_password_hash = get_password_hash_fn

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = _get_real_client_ip(request)

        # 1. 只拦截 API 和 WebSocket 路径，静态资源全部放行
        if not path.startswith("/api/") and not path.startswith("/ws/"):
            return await call_next(request)

        # 2. 白名单路径放行
        if _is_whitelisted(path):
            return await call_next(request)

        # 3. TCP 层面判断本地请求 - 直接放行
        is_local = _is_local_request(request)
        if is_local:
            logger.debug(f"Local access granted: {client_ip} -> {path}")
            return await call_next(request)

        # 4. 远程请求 - 检查是否设置了密码
        password_hash = await self._get_password_hash_safe()

        if not password_hash:
            # 未设置密码 → 放行（前端会显示安全警告提示用户设置密码）
            logger.warning(f"Remote access without password: {client_ip} -> {path}")
            return await call_next(request)

        # 5. 检查 session token
        token = _get_token_from_request(request)
        username = validate_session(token) if token else None

        if username:
            logger.debug(f"Authenticated remote access: {client_ip} ({username}) -> {path}")
            return await call_next(request)

        # 6. 未认证 → 401
        logger.warning(f"Unauthorized remote access attempt: {client_ip} -> {path}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
        )

    async def _get_password_hash_safe(self) -> str:
        """安全获取密码哈希"""
        try:
            if self._get_password_hash:
                return await self._get_password_hash()
            return ""
        except Exception:
            return ""
