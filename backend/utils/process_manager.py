"""
进程管理模块 - 负责 PID 文件管理、孤儿进程清理和信号处理
"""

import os
import sys
import signal
import subprocess
from pathlib import Path
from typing import NoReturn, Optional


class ProcessManager:
    """进程管理器 - 负责 PID 文件管理和孤儿进程清理"""
    
    PID_FILE = Path("data/.CountBot.pid")
    FEISHU_WORKER_PATTERN = "feishu_websocket_worker.py"
    
    def __init__(self, logger=None):
        """
        初始化进程管理器
        
        Args:
            logger: 日志记录器实例，如果为 None 则使用 loguru
        """
        self.logger = logger
        if self.logger is None:
            from loguru import logger as loguru_logger
            self.logger = loguru_logger
    
    def cleanup_orphaned_processes(self) -> None:
        """清理可能存在的孤儿进程"""
        self._cleanup_main_process()
        self._cleanup_feishu_workers()
    
    def _cleanup_main_process(self) -> None:
        """清理主进程的 PID 文件和进程"""
        if not self.PID_FILE.exists():
            return
        
        try:
            old_pid = int(self.PID_FILE.read_text().strip())
            
            # 检查进程是否还在运行
            if not self._is_process_running(old_pid):
                self.logger.debug(
                    f"Cleaning up stale PID file (process {old_pid} not found)"
                )
                self.PID_FILE.unlink()
                return
            
            # 进程存在，尝试停止
            self.logger.warning(f"Found existing CountBot process (PID: {old_pid})")
            self.logger.info("Attempting to stop existing process...")
            
            self._terminate_process(old_pid)
            
        except ValueError as e:
            self.logger.warning(f"Invalid PID in file: {e}")
            self.PID_FILE.unlink()
        except Exception as e:
            self.logger.warning(f"Error checking old process: {e}")
            self.PID_FILE.unlink()
    
    def _cleanup_feishu_workers(self) -> None:
        """清理飞书 WebSocket 孤儿进程"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", self.FEISHU_WORKER_PATTERN],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        self.logger.info(
                            f"Cleaning up orphaned Feishu WebSocket process (PID: {pid})"
                        )
                        os.kill(pid, signal.SIGTERM)
                    except (ValueError, ProcessLookupError, PermissionError) as e:
                        self.logger.debug(f"Could not kill process {pid_str}: {e}")
                        
        except subprocess.TimeoutExpired:
            self.logger.warning("Process check timed out")
        except FileNotFoundError:
            self.logger.debug("pgrep command not available (Windows platform?)")
        except Exception as e:
            self.logger.debug(f"Could not check for orphaned processes: {e}")
    
    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """
        检查进程是否正在运行
        
        Args:
            pid: 进程 ID
            
        Returns:
            bool: 进程是否正在运行
        """
        try:
            os.kill(pid, 0)  # 发送信号 0 只检查进程是否存在
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # 进程存在但无权限访问
            return True
    
    def _terminate_process(self, pid: int, timeout: int = 2) -> None:
        """
        终止指定进程
        
        Args:
            pid: 进程 ID
            timeout: 等待超时时间（秒）
        """
        try:
            # 先尝试优雅关闭
            os.kill(pid, signal.SIGTERM)
            
            # 等待进程结束
            import time
            time.sleep(timeout)
            
            # 检查是否已停止
            if self._is_process_running(pid):
                self.logger.warning(f"Process {pid} still running, forcing kill...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
            
            if not self._is_process_running(pid):
                self.logger.info(f"Process {pid} stopped successfully")
                
        except ProcessLookupError:
            self.logger.debug(f"Process {pid} already stopped")
        except PermissionError as e:
            self.logger.error(f"Permission denied when stopping process {pid}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to stop process {pid}: {e}")
    
    def write_pid_file(self) -> None:
        """写入当前进程 PID"""
        self.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.PID_FILE.write_text(str(os.getpid()))
        self.logger.debug(f"PID file written: {self.PID_FILE} (PID: {os.getpid()})")
    
    def remove_pid_file(self) -> None:
        """删除 PID 文件"""
        if self.PID_FILE.exists():
            try:
                self.PID_FILE.unlink()
                self.logger.debug(f"PID file removed: {self.PID_FILE}")
            except Exception as e:
                self.logger.warning(f"Failed to remove PID file: {e}")


class SignalHandler:
    """信号处理器 - 处理优雅关闭"""
    
    def __init__(self, process_manager: ProcessManager, logger=None):
        """
        初始化信号处理器
        
        Args:
            process_manager: 进程管理器实例
            logger: 日志记录器实例
        """
        self.process_manager = process_manager
        self.logger = logger
        if self.logger is None:
            from loguru import logger as loguru_logger
            self.logger = loguru_logger
    
    def setup(self) -> None:
        """设置信号处理器"""
        # 注册信号处理器
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        
        # macOS/Unix 特定：处理 SIGHUP
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._handle_shutdown_signal)
        
        self.logger.debug("Signal handlers registered")
    
    def _handle_shutdown_signal(self, signum: int, frame) -> NoReturn:
        """
        处理关闭信号
        
        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        sig_name = signal.Signals(signum).name
        self.logger.info(f"Received {sig_name} signal, initiating graceful shutdown...")
        
        # 清理 PID 文件
        self.process_manager.remove_pid_file()
        
        # 退出程序
        sys.exit(0)


def cleanup_all_processes(logger=None) -> None:
    """
    便捷函数：清理所有孤儿进程
    
    Args:
        logger: 日志记录器实例
    """
    manager = ProcessManager(logger=logger)
    manager.cleanup_orphaned_processes()


def setup_graceful_shutdown(logger=None) -> ProcessManager:
    """
    便捷函数：设置优雅关闭机制
    
    Args:
        logger: 日志记录器实例
        
    Returns:
        ProcessManager: 进程管理器实例
    """
    manager = ProcessManager(logger=logger)
    handler = SignalHandler(manager, logger=logger)
    
    # 清理孤儿进程
    manager.cleanup_orphaned_processes()
    
    # 写入当前进程 PID
    manager.write_pid_file()
    
    # 设置信号处理器
    handler.setup()
    
    return manager
