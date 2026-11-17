"""远程安全入口横幅（setup_notice）单元测试。

覆盖三点：
1. 监听地址不同（0.0.0.0 / 回环）时入口 URL 的解析结果；
2. 横幅文案包含访客必须看到的提示，并带上下分隔线；
3. 带颜色标记输出时不会抛异常、也不会把内容吞掉。
"""

import io
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.modules.auth import setup_notice


def _patch_bind(monkeypatch, host, port, ips=None):
    monkeypatch.setenv("COUNTBOT_HOST", host)
    monkeypatch.setenv("COUNTBOT_PORT", str(port))
    monkeypatch.setattr(setup_notice, "get_local_ips", lambda: list(ips or []))


def test_public_bind_uses_each_local_ip(monkeypatch):
    _patch_bind(monkeypatch, "0.0.0.0", 8000, ips=["192.168.1.10", "10.0.0.5"])

    urls = setup_notice.build_setup_entry_urls("AbCdEfGh")

    assert urls == [
        "http://192.168.1.10:8000/setup/AbCdEfGh",
        "http://10.0.0.5:8000/setup/AbCdEfGh",
    ]


def test_public_bind_without_detected_ip_uses_placeholder(monkeypatch):
    _patch_bind(monkeypatch, "0.0.0.0", 9000, ips=[])

    urls = setup_notice.build_setup_entry_urls("AbCdEfGh")

    assert urls == ["http://YOUR_SERVER_IP:9000/setup/AbCdEfGh"]


def test_loopback_bind_uses_localhost_and_hints_public_host(monkeypatch):
    _patch_bind(monkeypatch, "127.0.0.1", 8000, ips=["192.168.1.10"])

    urls = setup_notice.build_setup_entry_urls("AbCdEfGh")
    notice = setup_notice.build_setup_entry_notice("AbCdEfGh", 30, urls=urls)

    assert urls == ["http://localhost:8000/setup/AbCdEfGh"]
    assert "COUNTBOT_HOST=0.0.0.0" in notice


def test_notice_frames_secret_and_warning(monkeypatch):
    _patch_bind(monkeypatch, "0.0.0.0", 8000, ips=["192.168.1.10"])

    notice = setup_notice.build_setup_entry_notice("AbCdEfGh", 30)
    lines = notice.splitlines()

    assert lines[0] == setup_notice.FRAME_CHAR * setup_notice.FRAME_WIDTH
    assert lines[1] == setup_notice.SEPARATOR_CHAR * setup_notice.FRAME_WIDTH
    assert lines[-1] == setup_notice.FRAME_CHAR * setup_notice.FRAME_WIDTH
    assert "防止未授权访问" in notice
    assert "http://192.168.1.10:8000/setup/AbCdEfGh" in notice
    assert "有效期 30 分钟" in notice
    # 入口 URL 独占一行，方便直接复制
    assert any(line.strip() == "http://192.168.1.10:8000/setup/AbCdEfGh" for line in lines)


def test_refreshed_notice_marks_previous_expired(monkeypatch):
    _patch_bind(monkeypatch, "0.0.0.0", 8000, ips=["192.168.1.10"])

    notice = setup_notice.build_setup_entry_notice(
        "ZzYyXxWw",
        30,
        urls=["http://192.168.1.10:8000/setup/ZzYyXxWw"],
        refreshed=True,
    )

    assert "已刷新" in notice
    assert "上一个入口已过期" in notice


def test_log_setup_entry_notice_survives_colorize(monkeypatch):
    _patch_bind(monkeypatch, "0.0.0.0", 8000, ips=["192.168.1.10"])
    buffer = io.StringIO()
    sink_id = logger.add(buffer, format="{message}", colorize=True, level="INFO")
    try:
        setup_notice.log_setup_entry_notice("AbCdEfGh", 30)
    finally:
        logger.remove(sink_id)

    output = buffer.getvalue()
    assert "http://192.168.1.10:8000/setup/AbCdEfGh" in output
    assert "<yellow>" not in output
