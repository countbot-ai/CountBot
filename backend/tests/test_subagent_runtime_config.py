"""回归测试：SubagentManager 在执行时动态读取最新模型参数。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.subagent import SubagentManager, TaskStatus
from backend.modules.providers.base import StreamChunk


class RecordingProvider:
    def __init__(self):
        self.calls = []

    async def chat_stream(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7, **kwargs):
        self.calls.append(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        yield StreamChunk(content="runtime config ok")


async def test_runtime_model_settings():
    print("=" * 60)
    print("测试: Subagent 运行时模型参数读取")
    print("=" * 60)

    provider = RecordingProvider()
    config_loader = SimpleNamespace(
        config=SimpleNamespace(
            model=SimpleNamespace(
                model="runtime-model",
                temperature=0.15,
                max_tokens=1234,
                max_iterations=3,
            ),
            security=SimpleNamespace(command_timeout=5, subagent_timeout=5),
        )
    )

    manager = SubagentManager(
        provider=provider,
        workspace=Path("."),
        model="stale-model",
        temperature=0.9,
        max_tokens=9999,
        config_loader=config_loader,
    )

    task_id = manager.create_task(
        label="runtime-config-test",
        message="say hi",
        system_prompt="You are a test agent.",
    )
    task = manager.get_task(task_id)
    await manager._run_task_impl(task, handler=None)

    if not provider.calls:
        print("❌ provider.chat_stream 未被调用")
        return False

    call = provider.calls[0]
    if call["model"] != "runtime-model":
        print(f"❌ model 未动态更新: {call['model']}")
        return False
    if call["temperature"] != 0.15:
        print(f"❌ temperature 未动态更新: {call['temperature']}")
        return False
    if call["max_tokens"] != 1234:
        print(f"❌ max_tokens 未动态更新: {call['max_tokens']}")
        return False
    if task.status != TaskStatus.COMPLETED:
        print(f"❌ 任务未完成: {task.status}")
        return False

    print("✅ Subagent 在执行时读取了最新模型参数")
    print(f"   model: {call['model']}")
    print(f"   temperature: {call['temperature']}")
    print(f"   max_tokens: {call['max_tokens']}")
    return True


async def main():
    result = await test_runtime_model_settings()
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))