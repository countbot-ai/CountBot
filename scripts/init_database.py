#!/usr/bin/env python3
"""数据库初始化脚本"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def init_database():
    """初始化数据库表"""
    print("正在初始化数据库...")
    
    try:
        from backend.database import init_db
        
        # 调用异步初始化函数
        await init_db()
        
        print("✓ 数据库初始化成功")
        return True
        
    except Exception as e:
        print(f"✗ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    success = asyncio.run(init_database())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
