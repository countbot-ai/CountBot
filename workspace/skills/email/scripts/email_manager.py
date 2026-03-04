"""邮箱管理核心模块"""
import imaplib
import poplib
import smtplib
import email
from email.header import decode_header, Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Optional


class EmailManager:
    """邮箱管理器基类"""
    
    def __init__(self, email_address: str, password: str, 
                 imap_server: str, imap_port: int,
                 smtp_server: str, smtp_port: int):
        self.email_address = email_address
        self.password = password
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
    
    def decode_str(self, s):
        """解码邮件头部字符串"""
        if s is None:
            return ""
        
        value, charset = decode_header(s)[0]
        if charset:
            try:
                value = value.decode(charset)
            except:
                try:
                    value = value.decode('utf-8', errors='ignore')
                except:
                    value = str(value)
        elif isinstance(value, bytes):
            try:
                value = value.decode('utf-8', errors='ignore')
            except:
                value = str(value)
        return value
    
    def get_email_content(self, msg):
        """获取邮件正文内容（仅纯文本，HTML 转纯文本）"""
        import re
        from html import unescape
        
        content = ""
        
        if msg.is_multipart():
            # 优先查找 text/plain 部分
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        content = payload.decode(charset, errors='ignore')
                        break
                    except:
                        pass
            
            # 如果没有纯文本，尝试从 HTML 提取
            if not content:
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/html':
                        try:
                            payload = part.get_payload(decode=True)
                            charset = part.get_content_charset() or 'utf-8'
                            html_content = payload.decode(charset, errors='ignore')
                            content = self._html_to_text(html_content)
                            break
                        except:
                            pass
        else:
            # 单部分邮件
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                raw_content = payload.decode(charset, errors='ignore')
                
                # 根据 Content-Type 处理
                if msg.get_content_type() == 'text/html':
                    content = self._html_to_text(raw_content)
                else:
                    content = raw_content
            except:
                pass
        
        return content.strip()
    
    def _html_to_text(self, html_content: str) -> str:
        """将 HTML 转换为纯文本"""
        import re
        from html import unescape
        
        # 移除 script 和 style 标签及其内容
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # 移除所有 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # 解码 HTML 实体
        text = unescape(text)
        
        # 清理多余空白
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        
        return text.strip()
    
    def receive_emails(self, mailbox: str = 'INBOX', limit: int = 10) -> List[Dict]:
        """接收邮件"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.password)
            mail.select(mailbox)
            
            status, messages = mail.search(None, 'ALL')
            email_ids = messages[0].split()
            
            emails = []
            for email_id in email_ids[-limit:]:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = self.decode_str(msg.get('Subject', ''))
                        from_ = self.decode_str(msg.get('From', ''))
                        date = msg.get('Date', '')
                        content = self.get_email_content(msg)
                        
                        emails.append({
                            'id': email_id.decode(),
                            'subject': subject,
                            'from': from_,
                            'date': date,
                            'content': content[:200] + '...' if len(content) > 200 else content
                        })
            
            mail.close()
            mail.logout()
            
            return emails
        
        except Exception as e:
            raise Exception(f"接收邮件失败: {str(e)}")
    
    def receive_emails_since(self, since_date: datetime, mailbox: str = 'INBOX') -> List[Dict]:
        """接收指定日期之后的邮件"""
        try:
            from email.utils import parsedate_to_datetime

            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.password)
            mail.select(mailbox)
            
            # IMAP SINCE 精度只到天，需要客户端二次过滤
            date_str = since_date.strftime('%d-%b-%Y')
            status, messages = mail.search(None, f'(SINCE {date_str})')
            email_ids = messages[0].split()
            
            emails = []
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # 客户端精确过滤：解析邮件日期，跳过早于 since_date 的
                        raw_date = msg.get('Date', '')
                        try:
                            email_dt = parsedate_to_datetime(raw_date)
                            # 统一为 naive datetime 比较（去掉时区信息）
                            if email_dt.tzinfo:
                                email_dt = email_dt.replace(tzinfo=None)
                            if email_dt < since_date:
                                continue
                        except Exception:
                            pass  # 无法解析日期的邮件仍然保留
                        
                        subject = self.decode_str(msg.get('Subject', ''))
                        from_ = self.decode_str(msg.get('From', ''))
                        content = self.get_email_content(msg)
                        
                        emails.append({
                            'id': email_id.decode(),
                            'subject': subject,
                            'from': from_,
                            'date': raw_date,
                            'content': content[:200] + '...' if len(content) > 200 else content
                        })
            
            mail.close()
            mail.logout()
            
            return emails
        
        except Exception as e:
            raise Exception(f"接收邮件失败: {str(e)}")
    
    def send_email(self, to_addr: str, subject: str, content: str, 
                   content_type: str = 'plain', attachments: List[str] = None) -> str:
        """发送邮件
        
        Args:
            to_addr: 收件人邮箱
            subject: 邮件主题
            content: 邮件内容
            content_type: 内容类型 ('plain' 或 'html')
            attachments: 附件文件路径列表
        
        Returns:
            发送结果消息
        """
        try:
            from email.mime.application import MIMEApplication
            import os
            
            message = MIMEMultipart()
            message['From'] = Header(self.email_address)
            message['To'] = Header(to_addr)
            message['Subject'] = Header(subject, 'utf-8')
            
            # 添加邮件正文
            message.attach(MIMEText(content, content_type, 'utf-8'))
            
            # 添加附件
            if attachments:
                for file_path in attachments:
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(f"附件文件不存在: {file_path}")
                    
                    with open(file_path, 'rb') as f:
                        attachment = MIMEApplication(f.read())
                        filename = os.path.basename(file_path)
                        attachment.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename=('utf-8', '', filename)
                        )
                        message.attach(attachment)
            
            server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            server.login(self.email_address, self.password)
            server.sendmail(self.email_address, [to_addr], message.as_string())
            server.quit()
            
            result = "邮件发送成功！"
            if attachments:
                result += f" (包含 {len(attachments)} 个附件)"
            return result
        
        except Exception as e:
            raise Exception(f"发送邮件失败: {str(e)}")

    def delete_email(self, email_id: str, mailbox: str = 'INBOX', permanent: bool = False) -> str:
        """删除邮件（IMAP）
        
        默认移到「已删除」文件夹（可在30天内恢复），permanent=True 则彻底删除（不可恢复）。
        
        Args:
            email_id: 邮件 ID（receive_emails 返回的 id 字段）
            mailbox: 邮箱文件夹，默认 INBOX
            permanent: 是否彻底删除（expunge）
                - False: 移到"已删除"文件夹（可恢复）
                - True: 彻底删除（不可恢复）
        
        Returns:
            操作结果消息
        
        注意:
            - QQ邮箱: permanent=False 时邮件移到"已删除"文件夹，可在30天内恢复
            - 163邮箱: 使用POP3协议，删除操作始终是永久的
        """
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.password)
            mail.select(mailbox)
            
            # 标记为删除
            mail.store(email_id.encode(), '+FLAGS', '\\Deleted')
            
            if permanent:
                mail.expunge()
                result = f"✓ 邮件 {email_id} 已彻底删除（不可恢复）"
            else:
                result = f"✓ 邮件 {email_id} 已移到已删除文件夹（可在30天内从已删除文件夹恢复）"
            
            mail.close()
            mail.logout()
            return result
        
        except Exception as e:
            raise Exception(f"删除邮件失败: {str(e)}")

    def delete_emails_batch(self, email_ids: List[str], mailbox: str = 'INBOX', permanent: bool = False) -> str:
        """批量删除邮件（IMAP）
        
        Args:
            email_ids: 邮件 ID 列表
            mailbox: 邮箱文件夹，默认 INBOX
            permanent: 是否彻底删除
                - False: 标记为删除，移到"已删除"文件夹（可恢复）
                - True: 彻底删除，立即从服务器移除（不可恢复）
        
        Returns:
            操作结果消息
        
        注意:
            - QQ邮箱: permanent=False 时邮件移到"已删除"文件夹，可在30天内恢复
            - 163邮箱: 使用POP3协议，删除操作始终是永久的
        """
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.password)
            mail.select(mailbox)
            
            # 批量标记为删除
            for eid in email_ids:
                mail.store(eid.encode(), '+FLAGS', '\\Deleted')
            
            if permanent:
                mail.expunge()
                action = "彻底删除（不可恢复）"
            else:
                action = "移到已删除文件夹（可在30天内恢复）"
            
            mail.close()
            mail.logout()
            
            return f"✓ 已{action} {len(email_ids)} 封邮件"
        
        except Exception as e:
            raise Exception(f"批量删除邮件失败: {str(e)}")


class QQEmailManager(EmailManager):
    """QQ 邮箱管理器 - 使用 IMAP"""
    
    def __init__(self, email_address: str, auth_code: str):
        super().__init__(
            email_address=email_address,
            password=auth_code,
            imap_server='imap.qq.com',
            imap_port=993,
            smtp_server='smtp.qq.com',
            smtp_port=465
        )


class Email163Manager(EmailManager):
    """163 邮箱管理器 - 使用 POP3（因为 IMAP 有安全限制）"""
    
    def __init__(self, email_address: str, auth_password: str):
        super().__init__(
            email_address=email_address,
            password=auth_password,
            imap_server='pop.163.com',  # 使用 POP3
            imap_port=995,
            smtp_server='smtp.163.com',
            smtp_port=465
        )
        self.pop_server = 'pop.163.com'
        self.pop_port = 995
    
    def receive_emails(self, mailbox: str = 'INBOX', limit: int = 10) -> List[Dict]:
        """接收邮件 - 使用 POP3"""
        try:
            # 连接 POP3
            pop = poplib.POP3_SSL(self.pop_server, self.pop_port)
            pop.user(self.email_address)
            pop.pass_(self.password)
            
            # 获取邮件数量
            num_messages = len(pop.list()[1])
            
            emails = []
            # 获取最新的 limit 封邮件
            start = max(1, num_messages - limit + 1)
            for i in range(start, num_messages + 1):
                try:
                    response, lines, octets = pop.retr(i)
                    
                    # 解析邮件
                    msg_content = b'\r\n'.join(lines)
                    msg = email.message_from_bytes(msg_content)
                    
                    subject = self.decode_str(msg.get('Subject', ''))
                    from_ = self.decode_str(msg.get('From', ''))
                    date = msg.get('Date', '')
                    content = self.get_email_content(msg)
                    
                    emails.append({
                        'id': str(i),
                        'subject': subject,
                        'from': from_,
                        'date': date,
                        'content': content
                    })
                except Exception as e:
                    # 跳过无法解析的邮件
                    continue
            
            pop.quit()
            return emails
        
        except Exception as e:
            raise Exception(f"接收邮件失败: {str(e)}")
    
    def receive_emails_since(self, since_date: datetime, mailbox: str = 'INBOX') -> List[Dict]:
        """接收指定日期之后的邮件 - 使用 POP3"""
        try:
            # 连接 POP3
            pop = poplib.POP3_SSL(self.pop_server, self.pop_port)
            pop.user(self.email_address)
            pop.pass_(self.password)
            
            # 获取邮件数量
            num_messages = len(pop.list()[1])
            
            emails = []
            # 从最新的邮件开始检查
            for i in range(num_messages, 0, -1):
                try:
                    response, lines, octets = pop.retr(i)
                    
                    # 解析邮件
                    msg_content = b'\r\n'.join(lines)
                    msg = email.message_from_bytes(msg_content)
                    
                    # 解析日期
                    date_str = msg.get('Date', '')
                    try:
                        from email.utils import parsedate_to_datetime
                        email_date = parsedate_to_datetime(date_str)
                        
                        # 如果邮件日期早于指定日期，停止检查
                        if email_date < since_date:
                            break
                    except:
                        # 如果无法解析日期，跳过
                        continue
                    
                    subject = self.decode_str(msg.get('Subject', ''))
                    from_ = self.decode_str(msg.get('From', ''))
                    content = self.get_email_content(msg)
                    
                    emails.append({
                        'id': str(i),
                        'subject': subject,
                        'from': from_,
                        'date': date_str,
                        'content': content
                    })
                except Exception as e:
                    # 跳过无法解析的邮件
                    continue
            
            pop.quit()
            # 反转列表，使最新的邮件在最后
            return list(reversed(emails))
        
        except Exception as e:
            raise Exception(f"接收邮件失败: {str(e)}")

    def delete_email(self, email_id: str, mailbox: str = 'INBOX', permanent: bool = False) -> str:
        """删除邮件（POP3）
        
        注意：POP3 协议的删除始终是永久的，不可恢复。
        permanent 参数对 POP3 无效，仅为保持接口一致性。
        """
        try:
            pop = poplib.POP3_SSL(self.pop_server, self.pop_port)
            pop.user(self.email_address)
            pop.pass_(self.password)
            
            pop.dele(int(email_id))
            pop.quit()
            
            return f"✓ 邮件 {email_id} 已永久删除（POP3协议不支持恢复，已从服务器移除）"
        
        except Exception as e:
            raise Exception(f"删除邮件失败: {str(e)}")

    def delete_emails_batch(self, email_ids: List[str], mailbox: str = 'INBOX', permanent: bool = False) -> str:
        """批量删除邮件（POP3）
        
        注意：POP3 协议的删除始终是永久的，不可恢复。
        permanent 参数对 POP3 无效，仅为保持接口一致性。
        """
        try:
            pop = poplib.POP3_SSL(self.pop_server, self.pop_port)
            pop.user(self.email_address)
            pop.pass_(self.password)
            
            for eid in email_ids:
                pop.dele(int(eid))
            
            pop.quit()
            return f"✓ 已永久删除 {len(email_ids)} 封邮件（POP3协议不支持恢复，已从服务器移除）"
        
        except Exception as e:
            raise Exception(f"批量删除邮件失败: {str(e)}")


def load_config(config_path: str = None) -> Dict:
    """加载配置文件"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请复制 config.json.example 为 config.json 并填写您的邮箱信息"
        )
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: Dict, config_path: str = None):
    """保存配置文件"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_email_manager(email_type: str, config: Dict) -> EmailManager:
    """根据邮箱类型获取管理器"""
    if email_type == 'qq':
        email_config = config['qq_email']
        return QQEmailManager(
            email_address=email_config['email'],
            auth_code=email_config['auth_code']
        )
    elif email_type == '163':
        email_config = config['163_email']
        return Email163Manager(
            email_address=email_config['email'],
            auth_password=email_config['auth_password']
        )
    else:
        raise ValueError(f"不支持的邮箱类型: {email_type}，请使用 'qq' 或 '163'")
