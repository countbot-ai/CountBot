"""文件审计日志模块

将工具调用记录到文件系统，支持：
- 按日期自动分割日志文件
- 随机文件名（防止冲突）
- JSON 格式存储
- 自动清理旧日志
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger


class FileAuditLogger:
    """文件审计日志记录器"""
    
    def __init__(self, log_dir: str = "data/audit_logs", max_days: int = 30):
        """初始化文件审计日志记录器
        
        Args:
            log_dir: 日志目录
            max_days: 保留日志的最大天数
        """
        self.log_dir = Path(log_dir)
        self.max_days = max_days
        self.enabled = False
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前日志文件
        self._current_log_file: Optional[Path] = None
        self._current_date: Optional[str] = None
        
        logger.debug(f"FileAuditLogger initialized: {self.log_dir}")
    
    def set_enabled(self, enabled: bool) -> None:
        """设置是否启用审计日志"""
        self.enabled = enabled
        logger.debug(f"File audit logging {'enabled' if enabled else 'disabled'}")
    
    def _get_log_file(self) -> Path:
        """获取当前日志文件路径
        
        日志文件命名格式：audit_YYYY-MM-DD_<random>.log
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 如果日期变化，创建新文件
        if self._current_date != today or self._current_log_file is None:
            self._current_date = today
            random_id = uuid.uuid4().hex[:8]
            self._current_log_file = self.log_dir / f"audit_{today}_{random_id}.log"
            logger.info(f"Created new audit log file: {self._current_log_file}")
        
        return self._current_log_file
    
    def record_call(
        self,
        call_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> None:
        """记录工具调用
        
        Args:
            call_id: 调用 ID
            tool_name: 工具名称
            arguments: 工具参数
            session_id: 会话 ID
        """
        if not self.enabled:
            return
        
        try:
            log_file = self._get_log_file()
            
            record = {
                "id": call_id,
                "timestamp": datetime.now().isoformat(),
                "tool_name": tool_name,
                "arguments": arguments,
                "session_id": session_id,
                "status": "pending"
            }
            
            # 追加到日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        except Exception as e:
            logger.error(f"Failed to record audit log: {e}")
    
    def update_result(
        self,
        call_id: str,
        result: str,
        status: str,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> None:
        """更新工具调用结果
        
        Args:
            call_id: 调用 ID
            result: 执行结果
            status: 状态 (success, error)
            error: 错误信息
            duration_ms: 执行耗时（毫秒）
        """
        if not self.enabled:
            return
        
        try:
            log_file = self._get_log_file()
            
            update_record = {
                "id": call_id,
                "timestamp": datetime.now().isoformat(),
                "type": "result",
                "result": result[:1000] if result else None,  # 限制结果长度
                "status": status,
                "error": error,
                "duration_ms": duration_ms
            }
            
            # 追加结果记录
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(update_record, ensure_ascii=False) + "\n")
        
        except Exception as e:
            logger.error(f"Failed to update audit log: {e}")
    
    def record_ai_response(
        self,
        session_id: str,
        user_message: str,
        ai_response: str,
        duration_ms: Optional[int] = None
    ) -> None:
        """记录AI完整响应
        
        Args:
            session_id: 会话 ID
            user_message: 用户消息
            ai_response: AI响应
            duration_ms: 响应耗时（毫秒）
        """
        if not self.enabled:
            return
        
        try:
            log_file = self._get_log_file()
            
            record = {
                "type": "ai_response",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "user_message": user_message[:500] if user_message else None,  # 限制长度
                "ai_response": ai_response[:2000] if ai_response else None,  # 限制长度
                "response_length": len(ai_response) if ai_response else 0,
                "duration_ms": duration_ms
            }
            
            # 追加到日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        except Exception as e:
            logger.error(f"Failed to record AI response: {e}")
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的审计日志
        
        Args:
            limit: 返回的记录数量
            
        Returns:
            日志记录列表
        """
        if not self.enabled:
            return []
        
        try:
            # 获取所有日志文件，按修改时间排序
            log_files = sorted(
                self.log_dir.glob("audit_*.log"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            records = []
            
            # 读取日志文件
            for log_file in log_files:
                if len(records) >= limit:
                    break
                
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if len(records) >= limit:
                                break
                            
                            try:
                                record = json.loads(line.strip())
                                records.append(record)
                            except json.JSONDecodeError:
                                continue
                
                except Exception as e:
                    logger.warning(f"Failed to read log file {log_file}: {e}")
                    continue
            
            # 按时间戳倒序排序
            records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            
            return records[:limit]
        
        except Exception as e:
            logger.error(f"Failed to get recent logs: {e}")
            return []
    
    def get_logs_by_session(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取指定会话的审计日志
        
        Args:
            session_id: 会话 ID
            limit: 返回的记录数量
            
        Returns:
            日志记录列表
        """
        all_logs = self.get_recent_logs(limit * 2)  # 获取更多记录以便过滤
        
        session_logs = [
            log for log in all_logs
            if log.get("session_id") == session_id
        ]
        
        return session_logs[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取审计日志统计信息
        
        Returns:
            统计信息字典
        """
        if not self.enabled:
            return {
                "enabled": False,
                "total_files": 0,
                "total_records": 0,
                "success_rate": 0
            }
        
        try:
            log_files = list(self.log_dir.glob("audit_*.log"))
            total_records = 0
            success_count = 0
            error_count = 0
            
            for log_file in log_files:
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                record = json.loads(line.strip())
                                if record.get("type") != "result":
                                    total_records += 1
                                
                                if record.get("status") == "success":
                                    success_count += 1
                                elif record.get("status") == "error":
                                    error_count += 1
                            
                            except json.JSONDecodeError:
                                continue
                
                except Exception:
                    continue
            
            success_rate = (success_count / total_records * 100) if total_records > 0 else 0
            
            return {
                "enabled": True,
                "total_files": len(log_files),
                "total_records": total_records,
                "success_count": success_count,
                "error_count": error_count,
                "success_rate": round(success_rate, 2)
            }
        
        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {
                "enabled": True,
                "total_files": 0,
                "total_records": 0,
                "success_rate": 0
            }
    
    def cleanup_old_logs(self) -> int:
        """清理旧的审计日志
        
        Returns:
            删除的文件数量
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_days)
            deleted_count = 0
            
            for log_file in self.log_dir.glob("audit_*.log"):
                try:
                    # 从文件名提取日期
                    parts = log_file.stem.split("_")
                    if len(parts) >= 2:
                        file_date_str = parts[1]  # YYYY-MM-DD
                        file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                        
                        if file_date < cutoff_date:
                            log_file.unlink()
                            deleted_count += 1
                            logger.info(f"Deleted old audit log: {log_file}")
                
                except Exception as e:
                    logger.warning(f"Failed to process log file {log_file}: {e}")
                    continue
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old audit log files")
            
            return deleted_count
        
        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")
            return 0
    
    def clear_all_logs(self) -> int:
        """清空所有审计日志
        
        Returns:
            删除的文件数量
        """
        try:
            deleted_count = 0
            
            for log_file in self.log_dir.glob("audit_*.log"):
                try:
                    log_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete log file {log_file}: {e}")
            
            logger.info(f"Cleared {deleted_count} audit log files")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Failed to clear logs: {e}")
            return 0


# 全局实例
file_audit_logger = FileAuditLogger()
