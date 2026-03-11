"""回归测试：飞书 worker 会为无害事件注册空处理器，避免 processor not found 日志。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.channels.feishu_websocket_worker import _build_event_handler


class _FakeBuilder:
    def __init__(self):
        self.calls = []

    def register_p2_im_message_receive_v1(self, func):
        self.calls.append(("message_receive", func))
        return self

    def register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(self, func):
        self.calls.append(("bot_p2p_chat_entered", func))
        return self

    def register_p2_im_message_reaction_created_v1(self, func):
        self.calls.append(("reaction_created", func))
        return self

    def register_p2_im_message_reaction_deleted_v1(self, func):
        self.calls.append(("reaction_deleted", func))
        return self

    def build(self):
        return self.calls


class _PartialBuilder:
    def __init__(self):
        self.calls = []

    def register_p2_im_message_receive_v1(self, func):
        self.calls.append(("message_receive", func))
        return self

    def build(self):
        return self.calls


def test_build_event_handler_registers_ignored_events() -> None:
    fake_builder = _FakeBuilder()
    on_message = lambda data: None
    on_ignored = lambda data: None

    built = _build_event_handler(on_message, on_ignored, builder=fake_builder)
    registered_names = [name for name, _ in built]

    expected = [
        "message_receive",
        "bot_p2p_chat_entered",
        "reaction_created",
        "reaction_deleted",
    ]
    if registered_names != expected:
        raise AssertionError(f"注册事件不符合预期: {registered_names}")


def test_build_event_handler_tolerates_missing_optional_register_methods() -> None:
    partial_builder = _PartialBuilder()
    built = _build_event_handler(lambda data: None, lambda data: None, builder=partial_builder)

    registered_names = [name for name, _ in built]
    if registered_names != ["message_receive"]:
        raise AssertionError(f"应仅注册消息事件，实际为: {registered_names}")


def main() -> int:
    tests = [
        ("register ignored events", test_build_event_handler_registers_ignored_events),
        ("missing optional methods tolerated", test_build_event_handler_tolerates_missing_optional_register_methods),
    ]

    failed = []
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
        except Exception as exc:
            failed.append((name, exc))
            print(f"❌ {name}: {exc}")

    if failed:
        return 1

    print("\nfeishu websocket worker tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())