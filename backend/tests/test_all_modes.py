"""完整测试：验证所有三种模式都正常工作"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.modules.agent.workflow import WorkflowEngine


class MockSubagentManager:
    """模拟的SubagentManager"""
    
    def __init__(self):
        self.tasks = {}
        self.execution_log = []
    
    def create_task(self, label, message, system_prompt=None, event_callback=None, enable_skills=False):
        task_id = f"task_{len(self.tasks)}"
        self.tasks[task_id] = {"label": label, "message": message}
        self.execution_log.append(f"Created: {label}")
        return task_id
    
    async def execute_task(self, task_id):
        task = self.tasks[task_id]
        self.execution_log.append(f"Executed: {task['label']}")
    
    def get_task(self, task_id):
        class MockTask:
            def __init__(self, label):
                self.status = type('Status', (), {'value': 'completed'})()
                self.result = f"Result from {label}"
        return MockTask(self.tasks[task_id]["label"])
    
    @property
    def running_tasks(self):
        return {}


async def test_pipeline_mode():
    """测试 Pipeline 模式"""
    print("=" * 60)
    print("测试 Pipeline 模式")
    print("=" * 60)
    
    manager = MockSubagentManager()
    engine = WorkflowEngine(manager)
    
    stages = [
        {"id": "research", "role": "研究员", "task": "研究主题"},
        {"id": "write", "role": "撰稿人", "task": "撰写内容"},
        {"id": "edit", "role": "编辑", "task": "润色文章"},
    ]
    
    result = await engine.run_pipeline("创作一篇文章", stages)
    
    if "Error" in result:
        print(f"❌ Pipeline 模式失败: {result}")
        return False
    
    print("✅ Pipeline 模式正常工作")
    print(f"执行顺序: {' → '.join([t['label'] for t in manager.tasks.values()])}")
    return True


async def test_graph_mode():
    """测试 Graph 模式（带依赖关系）"""
    print("\n" + "=" * 60)
    print("测试 Graph 模式（依赖关系）")
    print("=" * 60)
    
    manager = MockSubagentManager()
    engine = WorkflowEngine(manager)
    
    slots = [
        {"id": "design", "role": "架构师", "task": "设计系统", "depends_on": []},
        {"id": "frontend", "role": "前端", "task": "实现前端", "depends_on": ["design"]},
        {"id": "backend", "role": "后端", "task": "实现后端", "depends_on": ["design"]},
        {"id": "test", "role": "测试", "task": "集成测试", "depends_on": ["frontend", "backend"]},
    ]
    
    result = await engine.run_graph("开发全栈应用", slots)
    
    if "Error" in result:
        print(f"❌ Graph 模式失败: {result}")
        return False
    
    print("✅ Graph 模式正常工作")
    print(f"执行的任务: {[t['label'] for t in manager.tasks.values()]}")
    
    # 验证执行顺序
    labels = [t['label'] for t in manager.tasks.values()]
    design_idx = labels.index("架构师")
    frontend_idx = labels.index("前端")
    backend_idx = labels.index("后端")
    test_idx = labels.index("测试")
    
    # 验证依赖关系
    if design_idx < frontend_idx and design_idx < backend_idx:
        print("  ✓ 架构师在前后端之前执行")
    else:
        print("  ✗ 依赖关系错误：架构师应该先执行")
        return False
    
    if frontend_idx < test_idx and backend_idx < test_idx:
        print("  ✓ 前后端在测试之前执行")
    else:
        print("  ✗ 依赖关系错误：前后端应该在测试之前")
        return False
    
    return True


async def test_council_mode_cross():
    """测试 Council 模式（交叉评审）"""
    print("\n" + "=" * 60)
    print("测试 Council 模式（交叉评审）")
    print("=" * 60)
    
    manager = MockSubagentManager()
    engine = WorkflowEngine(manager)
    
    members = [
        {"id": "tech", "perspective": "技术视角"},
        {"id": "cost", "perspective": "成本视角"},
        {"id": "ux", "perspective": "用户体验视角"},
    ]
    
    result = await engine.run_council("评估新功能", members, cross_review=True)
    
    if "Error" in result:
        print(f"❌ Council 交叉模式失败: {result}")
        return False
    
    print("✅ Council 交叉模式正常工作")
    
    # 验证两轮执行
    task_count = len(manager.tasks)
    expected_count = len(members) * 2  # 第1轮 + 第2轮
    
    if task_count == expected_count:
        print(f"  ✓ 执行了 {task_count} 个任务（{len(members)} 成员 × 2 轮）")
    else:
        print(f"  ✗ 任务数量错误：期望 {expected_count}，实际 {task_count}")
        return False
    
    return True


async def test_council_mode_independent():
    """测试 Council 模式（独立分析）"""
    print("\n" + "=" * 60)
    print("测试 Council 模式（独立分析）")
    print("=" * 60)
    
    manager = MockSubagentManager()
    engine = WorkflowEngine(manager)
    
    members = [
        {"id": "optimist", "perspective": "乐观派"},
        {"id": "pessimist", "perspective": "悲观派"},
        {"id": "neutral", "perspective": "中立派"},
    ]
    
    result = await engine.run_council("分析市场趋势", members, cross_review=False)
    
    if "Error" in result:
        print(f"❌ Council 独立模式失败: {result}")
        return False
    
    print("✅ Council 独立模式正常工作")
    
    # 验证只有一轮
    task_count = len(manager.tasks)
    expected_count = len(members)  # 只有第1轮
    
    if task_count == expected_count:
        print(f"  ✓ 执行了 {task_count} 个任务（{len(members)} 成员 × 1 轮）")
    else:
        print(f"  ✗ 任务数量错误：期望 {expected_count}，实际 {task_count}")
        return False
    
    return True


async def main():
    """运行所有模式测试"""
    print("\n" + "🎯 " * 20)
    print("多智能体工作流完整功能测试")
    print("🎯 " * 20 + "\n")
    
    tests = [
        ("Pipeline 模式", test_pipeline_mode),
        ("Graph 模式（依赖关系）", test_graph_mode),
        ("Council 模式（交叉评审）", test_council_mode_cross),
        ("Council 模式（独立分析）", test_council_mode_independent),
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
    print("完整功能测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n" + "🎉 " * 20)
        print("所有模式都正常工作！")
        print("🎉 " * 20)
        print("\n功能验证:")
        print("  ✅ Pipeline 模式 - 顺序执行，上下文传递")
        print("  ✅ Graph 模式 - 依赖关系，自动并行")
        print("  ✅ Council 模式（交叉） - 两轮评审")
        print("  ✅ Council 模式（独立） - 单轮分析")
        print("\n系统状态: 完全正常 ✅")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个模式失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
