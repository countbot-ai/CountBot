#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cloudflare Pages 部署工具 - 纯 REST API，只需一个 api_token"""
import argparse
import sys
import json
import os
import hashlib
import mimetypes
import base64
import io
import urllib.request
import urllib.error

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
CF_API = "https://api.cloudflare.com/client/v4"
_account_id_cache = None


def load_config():
    """加载配置，只需 api_token 一个字段"""
    if not os.path.exists(CONFIG_PATH):
        print(f"配置文件不存在: {CONFIG_PATH}", file=sys.stderr)
        print(f"请复制 config.json.example 为 config.json 并填写 api_token", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    if not config.get('api_token'):
        print("配置缺少 api_token", file=sys.stderr)
        sys.exit(1)
    return config['api_token']


def get_account_id(token):
    """通过 API 自动获取 account_id"""
    global _account_id_cache
    if _account_id_cache:
        return _account_id_cache
    result = api_request('GET', '/accounts', token)
    if not result.get('success') or not result.get('result'):
        print("❌ 无法获取账户信息，请检查 api_token 是否有效", file=sys.stderr)
        sys.exit(1)
    _account_id_cache = result['result'][0]['id']
    return _account_id_cache


def api_request(method, path, token, data=None):
    """发送 Cloudflare API 请求"""
    url = f"{CF_API}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
        body = json.dumps(data).encode('utf-8')
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


def multipart_request(url, token, fields):
    """发送 multipart/form-data 请求"""
    boundary = '----CloudflarePagesDeployBoundary'
    body_parts = []
    for name, value in fields.items():
        body_parts.append(f'--{boundary}\r\n'.encode())
        body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body_parts.append(value.encode('utf-8') if isinstance(value, str) else value)
        body_parts.append(b'\r\n')
    body_parts.append(f'--{boundary}--\r\n'.encode())
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(url, data=b''.join(body_parts), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            return json.loads(err_body)
        except Exception:
            print(f"API 错误: HTTP {e.code} - {err_body}", file=sys.stderr)
            sys.exit(1)


def collect_files(source_path):
    """收集要部署的文件"""
    source_path = os.path.abspath(source_path)
    files = {}
    if os.path.isfile(source_path):
        with open(source_path, 'rb') as f:
            content = f.read()
        b64 = base64.b64encode(content).decode('ascii')
        ct = mimetypes.guess_type(source_path)[0] or 'text/html'
        files["/index.html"] = {
            "hash": hashlib.md5((b64 + "/index.html").encode()).hexdigest(),
            "content_type": ct, "content_b64": b64, "size": len(content),
        }
        basename = os.path.basename(source_path)
        if basename != "index.html":
            files[f"/{basename}"] = {
                "hash": hashlib.md5((b64 + f"/{basename}").encode()).hexdigest(),
                "content_type": ct, "content_b64": b64, "size": len(content),
            }
    elif os.path.isdir(source_path):
        for root, dirs, filenames in os.walk(source_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in filenames:
                if fname.startswith('.'):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = "/" + os.path.relpath(full_path, source_path).replace("\\", "/")
                with open(full_path, 'rb') as f:
                    content = f.read()
                b64 = base64.b64encode(content).decode('ascii')
                files[rel_path] = {
                    "hash": hashlib.md5((b64 + rel_path).encode()).hexdigest(),
                    "content_type": mimetypes.guess_type(full_path)[0] or 'application/octet-stream',
                    "content_b64": b64, "size": len(content),
                }
    else:
        print(f"路径不存在: {source_path}", file=sys.stderr)
        sys.exit(1)
    return files


def ensure_project(token, account_id, project_name):
    """确保项目存在，不存在则创建"""
    result = api_request('GET', f'/accounts/{account_id}/pages/projects/{project_name}', token)
    if result.get('success'):
        return True
    print(f"项目 {project_name} 不存在，正在创建...")
    result = api_request('POST', f'/accounts/{account_id}/pages/projects', token,
                         data={"name": project_name, "production_branch": "main"})
    if result.get('success'):
        print(f"✅ 项目 {project_name} 创建成功")
        return True
    print(f"❌ 创建项目失败: {result.get('errors', [])}", file=sys.stderr)
    sys.exit(1)


def _upload_bucket(bucket, jwt):
    """上传一批文件"""
    body = json.dumps(bucket).encode('utf-8')
    headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{CF_API}/pages/assets/upload", data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if not result.get('success', True):
                print(f"⚠️  上传警告: {result}", file=sys.stderr)
    except urllib.error.HTTPError as e:
        print(f"❌ 上传失败: HTTP {e.code} - {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)


def deploy_files(token, account_id, project_name, files, branch=None):
    """通过 API 部署文件到 Cloudflare Pages"""
    # 获取上传凭证
    print("📤 获取上传凭证...")
    upload_result = api_request('GET', f'/accounts/{account_id}/pages/projects/{project_name}/upload-token', token)
    if not upload_result.get('success'):
        print(f"❌ 获取上传凭证失败: {upload_result.get('errors', [])}", file=sys.stderr)
        sys.exit(1)
    upload_jwt = upload_result['result']['jwt']

    # 上传文件（分批，每批不超过 50MB）
    print(f"📦 上传 {len(files)} 个文件...")
    bucket, bucket_size, all_hashes = [], 0, []
    for path_key, info in files.items():
        item = {"key": info['hash'], "value": info['content_b64'],
                "metadata": {"contentType": info['content_type']}, "base64": True}
        all_hashes.append(info['hash'])
        if bucket_size + info['size'] > 50 * 1024 * 1024 and bucket:
            _upload_bucket(bucket, upload_jwt)
            bucket, bucket_size = [], 0
        bucket.append(item)
        bucket_size += info['size']
    if bucket:
        _upload_bucket(bucket, upload_jwt)

    # 确认上传
    print("🔄 确认文件上传...")
    api_request('POST', '/pages/assets/upsert-hashes', upload_jwt, data={"hashes": all_hashes})

    # 创建部署
    print("🚀 创建部署...")
    manifest = {k: v['hash'] for k, v in files.items()}
    fields = {"manifest": json.dumps(manifest)}
    if branch:
        fields["branch"] = branch
    result = multipart_request(
        f"{CF_API}/accounts/{account_id}/pages/projects/{project_name}/deployments", token, fields)

    if result.get('success') or result.get('id'):
        url = result.get('url', '') or result.get('result', {}).get('url', '')
        print(f"\n✅ 部署成功!")
        print(f"🌐 访问: https://{project_name}.pages.dev")
        if url:
            print(f"🔗 部署预览: {url}")
    else:
        print(f"\n❌ 部署失败: {result.get('errors', [])}", file=sys.stderr)
        sys.exit(1)


def cmd_deploy(args):
    """部署命令"""
    token = load_config()
    account_id = get_account_id(token)
    source = os.path.abspath(args.source)
    if not os.path.exists(source):
        print(f"路径不存在: {source}", file=sys.stderr)
        sys.exit(1)

    print(f"正在部署到 Cloudflare Pages...")
    print(f"项目: {args.project}")
    print(f"源: {source}")
    if args.branch:
        print(f"分支: {args.branch}")
    print()

    ensure_project(token, account_id, args.project)
    files = collect_files(source)
    print(f"共 {len(files)} 个文件待部署")
    for path_key in files:
        print(f"  📄 {path_key} ({files[path_key]['size']} bytes)")
    print()
    deploy_files(token, account_id, args.project, files, branch=args.branch)


def cmd_list(args):
    """列出所有项目"""
    token = load_config()
    account_id = get_account_id(token)
    result = api_request('GET', f'/accounts/{account_id}/pages/projects', token)
    if not result.get('success'):
        print(f"API 错误: {result.get('errors', [])}", file=sys.stderr)
        sys.exit(1)

    projects = result.get('result', [])
    if args.json:
        print(json.dumps(projects, ensure_ascii=False, indent=2))
        return
    if not projects:
        print("暂无项目")
        return

    print(f"共 {len(projects)} 个项目:\n")
    for p in projects:
        print(f"  📦 {p.get('name', '?')}")
        print(f"     🌐 https://{p.get('subdomain', '?')}")
        print(f"     📅 创建于 {p.get('created_on', '?')[:10]}")
        domains = p.get('domains', [])
        if domains:
            print(f"     🔗 域名: {', '.join(domains)}")
        print()


def cmd_deployments(args):
    """查看部署历史"""
    token = load_config()
    account_id = get_account_id(token)
    result = api_request('GET', f'/accounts/{account_id}/pages/projects/{args.project}/deployments', token)
    if not result.get('success'):
        print(f"API 错误: {result.get('errors', [])}", file=sys.stderr)
        sys.exit(1)

    deployments = result.get('result', [])
    if args.json:
        print(json.dumps(deployments, ensure_ascii=False, indent=2))
        return
    if not deployments:
        print(f"项目 {args.project} 暂无部署记录")
        return

    print(f"项目 {args.project} 的部署记录 (共 {len(deployments)} 条):\n")
    for d in deployments[:10]:
        status = d.get('latest_stage', {}).get('status', '?')
        emoji = '✅' if status == 'success' else '❌' if status == 'failure' else '⏳'
        print(f"  {emoji} {d.get('id', '?')[:12]}...")
        print(f"     🌐 {d.get('url', '?')}")
        print(f"     📅 {d.get('created_on', '?')[:19].replace('T', ' ')}  |  🏷️ {d.get('environment', '?')}  |  状态: {status}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Cloudflare Pages 部署工具（纯 API，无需 wrangler）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s deploy index.html --project my-site
  %(prog)s deploy ./dist --project my-site
  %(prog)s deploy ./dist --project my-site --branch preview
  %(prog)s list
  %(prog)s deployments --project my-site
""")
    subparsers = parser.add_subparsers(dest='command', help='命令')

    dp = subparsers.add_parser('deploy', help='部署网页到 Cloudflare Pages')
    dp.add_argument('source', help='HTML 文件或目录路径')
    dp.add_argument('--project', required=True, help='Cloudflare Pages 项目名')
    dp.add_argument('--branch', help='部署分支（用于预览环境）')

    lp = subparsers.add_parser('list', help='列出所有项目')
    lp.add_argument('--json', action='store_true', help='JSON 格式输出')

    hp = subparsers.add_parser('deployments', help='查看部署历史')
    hp.add_argument('--project', required=True, help='项目名')
    hp.add_argument('--json', action='store_true', help='JSON 格式输出')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {'deploy': cmd_deploy, 'list': cmd_list, 'deployments': cmd_deployments}[args.command](args)


if __name__ == '__main__':
    main()
