#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ModelScope 文生图工具 - 支持异步生成、LoRA 风格叠加"""
import argparse
import sys
import json
import os
import time
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
BASE_URL = "https://api-inference.modelscope.cn/"
DEFAULT_MODEL = "Tongyi-MAI/Z-Image-Turbo"
POLL_INTERVAL = 5
MAX_POLL_TIME = 300


def load_config():
    """加载配置，只需 api_token"""
    if not os.path.exists(CONFIG_PATH):
        print(f"配置文件不存在: {CONFIG_PATH}", file=sys.stderr)
        print("请复制 config.json.example 为 config.json 并填写 api_token", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    token = config.get('api_token', '')
    if not token:
        print("配置缺少 api_token", file=sys.stderr)
        sys.exit(1)
    return token


def api_request(method, path, token, data=None, headers_extra=None):
    """发送 ModelScope API 请求"""
    import urllib.request
    import urllib.error

    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if headers_extra:
        headers.update(headers_extra)

    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            return json.loads(err_body)
        except Exception:
            print(f"API 错误: HTTP {e.code} - {err_body}", file=sys.stderr)
            sys.exit(1)


def download_image(url, output_path):
    """下载图片到本地"""
    import urllib.request
    urllib.request.urlretrieve(url, output_path)


def submit_task(token, prompt, model=None, lora=None, size=None):
    """提交异步图片生成任务"""
    payload = {
        "model": model or DEFAULT_MODEL,
        "prompt": prompt,
    }

    # 处理 LoRA
    if lora:
        try:
            lora_parsed = json.loads(lora)
            payload["loras"] = lora_parsed
        except (json.JSONDecodeError, TypeError):
            payload["loras"] = lora

    # 处理尺寸
    if size:
        parts = size.lower().split('x')
        if len(parts) == 2:
            payload["width"] = int(parts[0])
            payload["height"] = int(parts[1])

    result = api_request(
        'POST', 'v1/images/generations', token,
        data=payload,
        headers_extra={"X-ModelScope-Async-Mode": "true"}
    )

    task_id = result.get('task_id')
    if not task_id:
        print(f"❌ 提交任务失败: {result}", file=sys.stderr)
        sys.exit(1)
    return task_id


def poll_task(token, task_id):
    """轮询任务状态直到完成"""
    start = time.time()
    while time.time() - start < MAX_POLL_TIME:
        result = api_request(
            'GET', f'v1/tasks/{task_id}', token,
            headers_extra={"X-ModelScope-Task-Type": "image_generation"}
        )
        status = result.get('task_status', '')
        if status == 'SUCCEED':
            return result
        elif status == 'FAILED':
            print(f"❌ 生成失败: {result.get('message', '未知错误')}", file=sys.stderr)
            sys.exit(1)
        elapsed = int(time.time() - start)
        print(f"⏳ 生成中... ({elapsed}s)", end='\r')
        time.sleep(POLL_INTERVAL)

    print(f"\n❌ 超时（{MAX_POLL_TIME}s），任务 ID: {task_id}", file=sys.stderr)
    sys.exit(1)


def cmd_generate(args):
    """生成图片"""
    token = load_config()
    prompt = args.prompt
    output = args.output or "generated_image.jpg"

    print(f"🎨 提交生成任务...")
    print(f"   Prompt: {prompt}")
    if args.model:
        print(f"   模型: {args.model}")
    if args.lora:
        print(f"   LoRA: {args.lora}")
    if args.size:
        print(f"   尺寸: {args.size}")
    print()

    task_id = submit_task(token, prompt, model=args.model, lora=args.lora, size=args.size)
    print(f"📋 任务 ID: {task_id}")

    result = poll_task(token, task_id)
    images = result.get('output_images', [])
    if not images:
        print("❌ 未返回图片", file=sys.stderr)
        sys.exit(1)

    # 确保输出目录存在
    out_dir = os.path.dirname(os.path.abspath(output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    download_image(images[0], output)
    abs_path = os.path.abspath(output)
    print(f"\n✅ 图片已保存: {abs_path}")

    if args.json:
        print(json.dumps({
            "status": "success",
            "task_id": task_id,
            "image_url": images[0],
            "output_path": abs_path,
        }, ensure_ascii=False, indent=2))


def cmd_status(args):
    """查询任务状态"""
    token = load_config()
    result = api_request(
        'GET', f'v1/tasks/{args.task_id}', token,
        headers_extra={"X-ModelScope-Task-Type": "image_generation"}
    )
    status = result.get('task_status', '未知')
    print(f"任务 {args.task_id}: {status}")
    if status == 'SUCCEED':
        images = result.get('output_images', [])
        for i, url in enumerate(images):
            print(f"  图片 {i+1}: {url}")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='ModelScope 文生图工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s generate --prompt "一只金色的猫"
  %(prog)s generate --prompt "赛博朋克城市" --output city.jpg
  %(prog)s generate --prompt "水墨画" --lora "repo/lora-model"
  %(prog)s generate --prompt "壁纸" --size 1920x1080
  %(prog)s status --task-id TASK_ID
""")
    subparsers = parser.add_subparsers(dest='command', help='命令')

    gp = subparsers.add_parser('generate', help='生成图片')
    gp.add_argument('--prompt', required=True, help='图片描述（建议英文）')
    gp.add_argument('--output', '-o', help='输出文件路径（默认 generated_image.jpg）')
    gp.add_argument('--model', help=f'模型 ID（默认 {DEFAULT_MODEL}）')
    gp.add_argument('--lora', help='LoRA 模型（单个 repo-id 或 JSON 格式多 LoRA）')
    gp.add_argument('--size', help='图片尺寸，如 1024x1024')
    gp.add_argument('--json', action='store_true', help='JSON 格式输出')

    sp = subparsers.add_parser('status', help='查询任务状态')
    sp.add_argument('--task-id', required=True, help='任务 ID')
    sp.add_argument('--json', action='store_true', help='JSON 格式输出')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {'generate': cmd_generate, 'status': cmd_status}[args.command](args)


if __name__ == '__main__':
    main()
