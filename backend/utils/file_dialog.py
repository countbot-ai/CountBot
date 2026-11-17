"""文件对话框工具"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def select_directory(title: str = "选择工作空间目录") -> Optional[str]:
    """
    打开目录选择对话框
    
    Args:
        title: 对话框标题
        
    Returns:
        选择的目录路径，如果取消则返回 None
    """
    try:
        # 尝试使用 tkinter（跨平台）
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # 创建隐藏的根窗口
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            # 打开目录选择对话框
            directory = filedialog.askdirectory(
                title=title,
                mustexist=True
            )
            
            root.destroy()
            
            if directory:
                logger.info(f"用户选择目录: {directory}")
                return directory
            else:
                logger.info("用户取消选择目录")
                return None
                
        except ImportError:
            logger.warning("tkinter 不可用，尝试其他方法")
        
        # Windows: 使用 win32gui
        if sys.platform == "win32":
            try:
                import win32gui
                import win32con
                from win32com.shell import shell, shellcon
                
                # 使用 Windows Shell API
                pidl, display_name, image_list = shell.SHBrowseForFolder(
                    0,  # hwndOwner
                    None,  # pidlRoot
                    title,  # pszDisplayName
                    shellcon.BIF_RETURNONLYFSDIRS | shellcon.BIF_NEWDIALOGSTYLE,  # ulFlags
                    None,  # lpfn
                    None   # lParam
                )
                
                if pidl:
                    directory = shell.SHGetPathFromIDList(pidl)
                    if directory:
                        logger.info(f"用户选择目录 (Windows): {directory}")
                        return directory
                        
            except ImportError:
                logger.warning("win32gui 不可用")
        
        # macOS: 使用 osascript
        elif sys.platform == "darwin":
            try:
                import subprocess
                
                script = f'''
                tell application "System Events"
                    activate
                    set chosenFolder to choose folder with prompt "{title}"
                    return POSIX path of chosenFolder
                end tell
                '''
                
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    directory = result.stdout.strip()
                    if directory:
                        logger.info(f"用户选择目录 (macOS): {directory}")
                        return directory
                        
            except Exception as e:
                logger.warning(f"macOS 目录选择失败: {e}")
        
        # Linux: 尝试使用 zenity 或 kdialog
        elif sys.platform.startswith("linux"):
            try:
                import subprocess
                
                # 尝试 zenity
                try:
                    result = subprocess.run(
                        ['zenity', '--file-selection', '--directory', '--title', title],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        directory = result.stdout.strip()
                        if directory:
                            logger.info(f"用户选择目录 (zenity): {directory}")
                            return directory
                            
                except FileNotFoundError:
                    pass
                
                # 尝试 kdialog
                try:
                    result = subprocess.run(
                        ['kdialog', '--getexistingdirectory', '.', '--title', title],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if result.returncode == 0:
                        directory = result.stdout.strip()
                        if directory:
                            logger.info(f"用户选择目录 (kdialog): {directory}")
                            return directory
                            
                except FileNotFoundError:
                    pass
                    
            except Exception as e:
                logger.warning(f"Linux 目录选择失败: {e}")
        
        logger.warning("无可用的目录选择对话框")
        return None
        
    except Exception as e:
        logger.error(f"目录选择对话框出错: {e}")
        return None


def is_desktop_environment() -> bool:
    """
    检查是否在桌面环境中运行
    
    Returns:
        True 如果在桌面环境中
    """
    try:
        # 检查是否有显示环境
        if sys.platform == "win32":
            return True
        elif sys.platform == "darwin":
            return True
        elif sys.platform.startswith("linux"):
            import os
            return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
        else:
            return False
    except Exception:
        return False