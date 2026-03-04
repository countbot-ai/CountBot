#!/usr/bin/env python3
"""
图像识别与理解命令行工具
"""
import sys
import json
import argparse

# 设置 stdout 编码为 UTF-8（Windows 兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from vision_manager import VisionManager, load_config


def main():
    parser = argparse.ArgumentParser(description='图像识别与理解')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析图片/视频/文件')
    analyze_parser.add_argument('--image', action='append', help='图片 URL 或本地路径（可多次指定）')
    analyze_parser.add_argument('--video', action='append', help='视频 URL（可多次指定）')
    analyze_parser.add_argument('--file', action='append', help='文件 URL（可多次指定）')
    analyze_parser.add_argument('--prompt', required=True, help='提示词')
    analyze_parser.add_argument('--model', choices=['zhipu', 'qwen'], help='指定模型')
    analyze_parser.add_argument('--thinking', action='store_true', help='开启思考模式（仅智谱支持）')
    analyze_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    analyze_parser.add_argument('--show-usage', action='store_true', help='显示 token 使用情况')
    analyze_parser.add_argument('--config', help='配置文件路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        # 加载配置
        config = load_config(args.config)
        manager = VisionManager(config)
        
        if args.command == 'analyze':
            # 检查是否至少提供了一种输入
            if not any([args.image, args.video, args.file]):
                print("错误：请至少提供一个图片、视频或文件")
                sys.exit(1)
            
            # 调用分析
            result = manager.analyze(
                prompt=args.prompt,
                images=args.image,
                videos=args.video,
                files=args.file,
                model=args.model,
                thinking=args.thinking
            )
            
            # 输出结果
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(manager.format_result(result, show_usage=args.show_usage))
    
    except FileNotFoundError as e:
        print(f"错误：{e}")
        print("\n请先创建配置文件 config.json，参考 config.json.example")
        sys.exit(1)
    except ValueError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"发生错误：{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
