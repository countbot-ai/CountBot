import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.context import ContextBuilder


class StubContextBuilder(ContextBuilder):
    def _get_personality_from_db(self, personality_id: str, custom_text: str = "") -> str:
        return "默认风格: 专业、友好、简洁。"


def main() -> int:
    builder = StubContextBuilder(
        workspace=Path('.'),
        persona_config=SimpleNamespace(
            ai_name="小C",
            user_name="主人",
            user_address="上海",
            output_language="英文",
            personality="grumpy",
            custom_personality="",
        ),
    )

    prompt = builder.build_system_prompt()
    checks = [
        ("- 默认输出语言: 英文" in prompt, "missing output language field"),
        ("所有回复优先使用英文" in prompt, "missing reply language instruction"),
    ]
    failed = [detail for ok, detail in checks if not ok]
    if failed:
        print("❌ output_language 未正确拼接到提示词:", "; ".join(failed))
        return 1

    print("✅ output_language 已正确拼接到提示词")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())