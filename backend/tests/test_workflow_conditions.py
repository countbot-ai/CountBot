"""测试工作流条件逻辑"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.workflow import WorkflowEngine


class MockSubagentManager:
    """模拟SubagentManager"""
    
    def __init__(self, mock_outputs: dict[str, str] = None):
        self.tasks = {}
        self.mock_outputs = mock_outputs or {}
    
    def create_task(self, label, message, system_prompt=None, event_callback=None, enable_skills=False):
        task_id = f"task_{len(self.tasks)}"
        self.tasks[task_id] = {"label": label}
        return task_id
    
    async def execute_task(self, task_id):
        pass
    
    def get_task(self, task_id):
        class MockTask:
            def __init__(self, label, output):
                self.status = type('Status', (), {'value': 'completed'})()
                self.result = output
        
        label = self.tasks[task_id]["label"]
        output = self.mock_outputs.get(label, f"Mock output from {label}")
        return MockTask(label, output)
    
    @property
    def running_tasks(self):
        return {}


async def test_condition_output_contains():
    """测试条件：输出包含指定文本"""
    print("=" * 60)
    print("测试：条件逻辑 - output_contains")
    print("=" * 60)
    
    # 模拟测试节点输出"测试通过"
    mock_manager = MockSubagentManager({
        "测试工程师": "所有测试通过，代码质量良好"
    })
    engine = WorkflowEngine(mock_manager)
    
    slots = [
        {
            "id": "test",
            "role": "测试工程师",
            "task": "运行测试",
            "depends_on": [],
        },
        {
            "id": "deploy",
            "role": "部署工程师",
            "task": "部署到生产环境",
            "depends_on": ["test"],
            "condition": {
                "type": "output_contains",
                "node": "test",
                "text": "测试通过"
            }
        },
    ]
    
    result = await engine.run_graph("测试并部署", slots)
    
    if "部署工程师" in result and "⏭️" not in result:
        print("✅ 条件满足，部署节点已执行")
        return True
    else:
        print("❌ 测试失败")
        return False


async def test_condition_not_met():
    """测试条件不满足时跳过节点"""
    print("\n" + "=" * 60)
    print("测试：条件不满足时跳过")
    print("=" * 60)
    
    # 模拟测试节点输出"测试失败"
    mock_manager = MockSubagentManager({
        "测试工程师": "测试失败，发现3个bug"
    })
    engine = WorkflowEngine(mock_manager)
    
    slots = [
        {
            "id": "test",
            "role": "测试工程师",
            "task": "运行测试",
            "depends_on": [],
        },
        {
            "id": "deploy",
            "role": "部署工程师",
            "task": "部署到生产环境",
            "depends_on": ["test"],
            "condition": {
                "type": "output_contains",
                "node": "test",
                "text": "测试通过"
            }
        },
    ]
    
    result = await engine.run_graph("测试并部署", slots)
    
    if "⏭️" in result and "Skipped" in result:
        print("✅ 条件不满足，部署节点已跳过")
        return True
    else:
        print("❌ 测试失败")
        return False


async def test_condition_output_not_contains():
    """测试条件：输出不包含指定文本"""
    print("\n" + "=" * 60)
    print("测试：条件逻辑 - output_not_contains")
    print("=" * 60)
    
    # 模拟代码审查输出（不包含"严重问题"）
    mock_manager = MockSubagentManager({
        "代码审查": "代码质量良好，建议合并"
    })
    engine = WorkflowEngine(mock_manager)
    
    slots = [
        {
            "id": "review",
            "role": "代码审查",
            "task": "审查代码",
            "depends_on": [],
        },
        {
            "id": "merge",
            "role": "合并工程师",
            "task": "合并到主分支",
            "depends_on": ["review"],
            "condition": {
                "type": "output_not_contains",
                "node": "review",
                "text": "严重问题"
            }
        },
    ]
    
    result = await engine.run_graph("审查并合并", slots)
    
    if "合并工程师" in result and "⏭️" not in result:
        print("✅ 条件满足（不包含严重问题），合并节点已执行")
        return True
    else:
        print("❌ 测试失败")
        return False


async def test_downstream_after_skip():
    """测试跳过节点后，下游节点仍能执行"""
    print("\n" + "=" * 60)
    print("测试：跳过节点后下游继续执行")
    print("=" * 60)
    
    mock_manager = MockSubagentManager({
        "测试": "测试失败",
        "通知": "已发送通知"
    })
    engine = WorkflowEngine(mock_manager)
    
    slots = [
        {
            "id": "test",
            "role": "测试",
            "task": "运行测试",
            "depends_on": [],
        },
        {
            "id": "deploy",
            "role": "部署",
            "task": "部署",
            "depends_on": ["test"],
            "condition": {
                "type": "output_contains",
                "node": "test",
                "text": "通过"
            }
        },
        {
            "id": "notify",
            "role": "通知",
            "task": "发送通知",
            "depends_on": ["test", "deploy"],  # 依赖测试和部署
        },
    ]
    
    result = await engine.run_graph("测试流程", slots)
    
    # 部署应该被跳过，但通知应该执行
    if "⏭️" in result and "通知" in result:
        print("✅ 部署被跳过，但通知节点仍然执行")
        return True
    else:
        print("❌ 测试失败")
        return False


async def main():
    """运行所有条件逻辑测试"""
    print("\n" + "🔀 " * 20)
    print("工作流条件逻辑测试")
    print("🔀 " * 20 + "\n")
    
    tests = [
        ("条件满足时执行", test_condition_output_contains),
        ("条件不满足时跳过", test_condition_not_met),
        ("output_not_contains条件", test_condition_output_not_contains),
        ("跳过后下游继续", test_downstream_after_skip),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ 测试 '{name}' 异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 条件逻辑功能正常！")
        print("\n支持的条件类型:")
        print("  1. output_contains - 输出包含指定文本")
        print("  2. output_not_contains - 输出不包含指定文本")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
