#!/usr/bin/env python3
"""非交互式邮件管理脚本"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from email_manager import load_config, get_email_manager


def cmd_send(args):
    """发送邮件"""
    try:
        config = load_config()
        manager = get_email_manager(args.mailbox, config)
        
        attachments = args.attach if args.attach else None
        
        manager.send_email(
            to_addr=args.to,
            subject=args.subject,
            content=args.content,
            attachments=attachments
        )
        
        print(f"邮件已发送到 {args.to}")
        if attachments:
            print(f"  附件: {', '.join(attachments)}")
        
    except Exception as e:
        print(f"发送失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_receive(args):
    """接收邮件"""
    try:
        config = load_config()
        manager = get_email_manager(args.mailbox, config)
        
        emails = manager.receive_emails(limit=args.limit)
        
        if not emails:
            if args.json:
                print(json.dumps({"count": 0, "emails": []}, ensure_ascii=False))
            else:
                print("收件箱为空")
            return
        
        if args.json:
            print(json.dumps({
                "count": len(emails),
                "emails": emails
            }, ensure_ascii=False, indent=2))
            return
        
        print(f"收到 {len(emails)} 封邮件:\n")
        for i, e in enumerate(emails, 1):
            print(f"[{i}] {e['subject']}")
            print(f"    发件人: {e['from']}")
            print(f"    日期: {e['date']}")
            print(f"    内容: {e['content'][:100]}...")
            print()
        
    except Exception as e:
        print(f"接收失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_check_new(args):
    """检查新邮件"""
    try:
        config = load_config()
        manager = get_email_manager(args.mailbox, config)
        
        since_date = datetime.now() - timedelta(days=args.since)
        new_emails = manager.receive_emails_since(since_date)
        
        if not new_emails:
            if args.json:
                print(json.dumps({"count": 0, "since_days": args.since, "emails": []}, ensure_ascii=False))
            else:
                print(f"没有新邮件（最近 {args.since} 天）")
            return
        
        if args.json:
            print(json.dumps({
                "count": len(new_emails),
                "since_days": args.since,
                "emails": [
                    {"subject": e['subject'], "from": e['from'], "date": e['date']}
                    for e in new_emails
                ]
            }, ensure_ascii=False, indent=2))
            return
        
        print(f"找到 {len(new_emails)} 封新邮件（最近 {args.since} 天）:\n")
        for i, e in enumerate(new_emails, 1):
            print(f"[{i}] {e['subject']}")
            print(f"    发件人: {e['from']}")
            print(f"    日期: {e['date']}")
            print()
        
    except Exception as e:
        print(f"检查失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_delete(args):
    """删除邮件"""
    try:
        config = load_config()
        manager = get_email_manager(args.mailbox, config)
        
        email_ids = args.ids
        
        if len(email_ids) == 1:
            result = manager.delete_email(email_ids[0], permanent=args.permanent)
        else:
            result = manager.delete_emails_batch(email_ids, permanent=args.permanent)
        
        print(result)
        
    except Exception as e:
        print(f"删除失败: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # 加载配置以获取默认邮箱
    try:
        config = load_config()
        default_mailbox = config.get('default_mailbox', 'qq')
    except:
        default_mailbox = 'qq'
    
    parser = argparse.ArgumentParser(
        description='邮件管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 发送邮件（使用默认邮箱）
  %(prog)s send --to user@example.com --subject "Hello" --content "Test"
  
  # 发送带附件
  %(prog)s send --to user@example.com --subject "Report" --content "See file" --attach report.pdf
  
  # 接收最新 5 封邮件
  %(prog)s receive --limit 5
  
  # 检查最近 2 天的新邮件
  %(prog)s check-new --since 2
  
  # 删除邮件（移到已删除文件夹，可在30天内恢复）
  %(prog)s delete --ids 123
  
  # 批量删除（移到已删除文件夹）
  %(prog)s delete --ids 123 124 125
  
  # 彻底删除（不可恢复，立即从服务器移除）
  %(prog)s delete --ids 123 --permanent
  
  # 批量彻底删除
  %(prog)s delete --ids 123 124 125 --permanent
  
  # 使用 163 邮箱
  %(prog)s send --mailbox 163 --to user@example.com --subject "Test"
"""
    )
    
    parser.add_argument(
        '--mailbox',
        choices=['qq', '163'],
        default=default_mailbox,
        help=f'邮箱类型 (默认: {default_mailbox}，可在 config.json 中修改 default_mailbox)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # send 命令
    send_parser = subparsers.add_parser('send', help='发送邮件')
    send_parser.add_argument('--to', required=True, help='收件人邮箱')
    send_parser.add_argument('--subject', required=True, help='邮件主题')
    send_parser.add_argument('--content', required=True, help='邮件内容')
    send_parser.add_argument('--attach', nargs='+', help='附件文件路径')
    
    # receive 命令
    receive_parser = subparsers.add_parser('receive', help='接收邮件')
    receive_parser.add_argument('--limit', type=int, default=10, help='接收数量 (默认: 10)')
    receive_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    
    # check-new 命令
    check_parser = subparsers.add_parser('check-new', help='检查新邮件')
    check_parser.add_argument('--since', type=int, default=1, help='检查最近 N 天 (默认: 1)')
    check_parser.add_argument('--json', action='store_true', help='JSON 格式输出')
    
    # delete 命令
    delete_parser = subparsers.add_parser('delete', help='删除邮件')
    delete_parser.add_argument('--ids', nargs='+', required=True, 
                               help='要删除的邮件 ID（可指定多个，用空格分隔）')
    delete_parser.add_argument('--permanent', action='store_true', 
                               help='彻底删除（不可恢复）。不指定此参数时，邮件将移到已删除文件夹，可在30天内恢复。注意：163邮箱使用POP3协议，删除始终是永久的')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 执行命令
    if args.command == 'send':
        cmd_send(args)
    elif args.command == 'receive':
        cmd_receive(args)
    elif args.command == 'check-new':
        cmd_check_new(args)
    elif args.command == 'delete':
        cmd_delete(args)


if __name__ == '__main__':
    main()
