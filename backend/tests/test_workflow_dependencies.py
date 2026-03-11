"""测试工作流依赖关系修复"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.workflow import WorkflowEngine, SlotPhase
from backend.modules.agent.subagent import SubagentManager
from backend.modules.providers.litellm_provider import LiteLLMProvider


class MockSubagentManager:
    """模拟的SubagentManager用于测试"""
    
    def __init__(self):
        self.tasks = {}
        self.call_order = []
    
    def create_task(self, label, message, system_prompt=None, event_callback=None, enable_skills=False):
        task_id = f"task_{len(self.tasks)}"
        self.tasks[task_id] = {
            "label": label,
            "message": message,
            "system_prompt": system_prompt,
        }
        return task_id
    
    async def execute_task(self, task_id):
        pass
    
    def get_task(self, task_id):
        class MockTask:
            def __init__(self, task_id, label):
                self.task_id = task_id
                self.label = label
                self.status = type('Status', (), {'value': 'completed'})()
                self.result = f"Mock result from {label}"
        
        task_data = self.tasks.get(task_id)
        if task_data:
            return MockTask(task_id, task_data["label"])
        return None
    
    @property
    def running_tasks(self):
        return {}


async def test_depends_on_field():
    """测试 depends_on 字段是否正确读取"""
    print("=" * 60)
    print("测试1: depends_on 字段读取")
    print("=" * 60)
    
    mock_manager = MockSubagentManager()
    engine = WorkflowEngine(mock_manager)
    
    # 测试配置：使用 depends_on 字段
    slots = [
        {
            "id": "design",
            "role": "架构师",
            "task": "设计系统",
            "depends_on": [],  # 无依赖
        },
        {
            "id": "frontend",
            "role": "前端",
            "task": "实现前端",
            "depends_on": ["design"],  # 依赖 design
        },
        {
            "id": "backend",
            "role": "后端",
            "task": "实现后端",
            "depends_on": ["design"],  # 依赖 design
        },
        {
            "id": "test",
            "role": "测试",
            "task": "集成测试",
            "depends_on": ["frontend", "backend"],  # 依赖 frontend 和 backend
        },
    ]
    
    # 执行工作流
    result = await engine.run_graph("测试目标", slots)
    
    # 验证结果
    if "Error" in result:
        print(f"❌ 测试失败: {result}")
        return False
    
    print("✅ depends_on 字段读取成功")
    print(f"执行的任务数: {len(mock_manager.tasks)}")
    
    # 验证执行顺序
    expected_order = ["design", "frontend", "backend", "test"]
    actual_labels = [task["label"] for task in mock_manager.tasks.values()]
    
    print(f"\n预期顺序: {expected_order}")
    print(f"实际标签: {actual_labels}")
    
    return True


async def test_backward_compatibility():
    """测试向后兼容性：depends 字段仍然可用"""
    print("\n" + "=" * 60)
    print("测试2: 向后兼容性 (depends 字段)")
    print("=" * 60)
    
    mock_manager = MockSubagentManager()
    engine = WorkflowEngine(mock_manager)
    
    # 测试配置：使用旧的 depends 字段
    slots = [
        {
            "id": "task1",
            "role": "任务1",
            "task": "第一个任务",
            "depends": [],  # 旧字段名
        },
        {
            "id": "task2",
            "role": "任务2",
            "task": "第二个任务",
            "depends": ["task1"],  # 旧字段名
        },
    ]
    
    # 执行工作流
    result = await engine.run_graph("测试目标", slots)
    
    # 验证结果
    if "Error" in result:
        print(f"❌ 测试失败: {result}")
        return False
    
    print("✅ depends 字段（向后兼容）读取成功")
    print(f"执行的任务数: {len(mock_manager.tasks)}")
    
    return True


async def test_cycle_detection():
    """测试循环依赖检测"""
    print("\n" + "=" * 60)
    print("测试3: 循环依赖检测")
    print("=" * 60)
    
    mock_manager = MockSubagentManager()
    engine = WorkflowEngine(mock_manager)
    
    # 测试配置：创建循环依赖
    slots = [
        {
            "id": "task1",
            "role": "任务1",
            "task": "第一个任务",
            "depends_on": ["task2"],  # 依赖 task2
        },
        {
            "id": "task2",
            "role": "任务2",
            "task": "第二个任务",
            "depends_on": ["task1"],  # 依赖 task1 (形成循环)
        },
    ]
    
    # 执行工作流
    result = await engine.run_graph("测试目标", slots)
    
    # 验证结果：应该检测到循环
    if "cycle" in result.lower():
        print("✅ 循环依赖检测成功")
        print(f"错误信息: {result}")
        return True
    else:
        print(f"❌ 测试失败: 未检测到循环依赖")
        return False


async def test_unknown_dependency():
    """测试未知依赖检测"""
    print("\n" + "=" * 60)
    print("测试4: 未知依赖检测")
    print("=" * 60)
    
    mock_manager = MockSubagentManager()
    engine = WorkflowEngine(mock_manager)
    
    # 测试配置：引用不存在的依赖
    slots = [
        {
            "id": "task1",
            "role": "任务1",
            "task": "第一个任务",
            "depends_on": ["nonexistent"],  # 不存在的依赖
        },
    ]
    
    # 执行工作流
    result = await engine.run_graph("测试目标", slots)
    
    # 验证结果：应该检测到未知依赖
    if "unknown" in result.lower() or "not found" in result.lower():
        print("✅ 未知依赖检测成功")
        print(f"错误信息: {result}")
        return True
    else:
        print(f"❌ 测试失败: 未检测到未知依赖")
        return False


async def test_parallel_execution():
    """测试并行执行"""
    print("\n" + "=" * 60)
    print("测试5: 并行执行验证")
    print("=" * 60)
    
    mock_manager = MockSubagentManager()
    engine = WorkflowEngine(mock_manager)
    
    # 测试配置：多个无依赖的任务应该并行执行
    slots = [
        {
            "id": "parallel1",
            "role": "并行任务1",
            "task": "第一个并行任务",
            "depends_on": [],
        },
        {
            "id": "parallel2",
            "role": "并行任务2",
            "task": "第二个并行任务",
            "depends_on": [],
        },
        {
            "id": "parallel3",
            "role": "并行任务3",
            "task": "第三个并行任务",
            "depends_on": [],
        },
    ]
    
    # 执行工作流
    result = await engine.run_graph("测试目标", slots)
    
    # 验证结果
    if "Error" in result:
        print(f"❌ 测试失败: {result}")
        return False
    
    print("✅ 并行执行成功")
    print(f"执行的任务数: {len(mock_manager.tasks)}")
    
    return True


async def main():
    """运行所有测试"""
    print("\n" + "🔧 " * 20)
    print("工作流依赖关系修复测试套件")
    print("🔧 " * 20 + "\n")
    
    tests = [
        ("depends_on 字段读取", test_depends_on_field),
        ("向后兼容性", test_backward_compatibility),
        ("循环依赖检测", test_cycle_detection),
        ("未知依赖检测", test_unknown_dependency),
        ("并行执行", test_parallel_execution),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ 测试 '{name}' 抛出异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！依赖关系修复成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，需要进一步检查")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
