"""桌面应用系统托盘集成"""

from loguru import logger
from typing import Callable, Optional
import threading


class SystemTray:
    """系统托盘管理器"""
    
    def __init__(self, window, app_name: str = "CountBot"):
        """初始化系统托盘
        
        Args:
            window: pywebview 窗口实例
            app_name: 应用名称
        """
        self.window = window
        self.app_name = app_name
        self.tray_icon = None
        self.on_show_callback: Optional[Callable] = None
        self.on_quit_callback: Optional[Callable] = None
    
    def create_menu(self):
        """创建托盘菜单项"""
        menu_items = [
            {
                "title": "Show Window",
                "action": self._on_show
            },
            {
                "title": "Hide Window",
                "action": self._on_hide
            },
            {
                "title": "-"  # 分隔符
            },
            {
                "title": "Quit",
                "action": self._on_quit
            }
        ]
        return menu_items
    
    def _on_show(self):
        """显示窗口回调"""
        try:
            self.window.show()
            if self.on_show_callback:
                self.on_show_callback()
        except Exception as e:
            logger.error(f"Failed to show window: {e}")
    
    def _on_hide(self):
        """隐藏窗口回调"""
        try:
            self.window.hide()
        except Exception as e:
            logger.error(f"Failed to hide window: {e}")
    
    def _on_quit(self):
        """退出应用回调"""
        try:
            if self.on_quit_callback:
                self.on_quit_callback()
            self.window.destroy()
        except Exception as e:
            logger.error(f"Failed to quit application: {e}")
    
    def set_callbacks(self, on_show: Optional[Callable] = None, on_quit: Optional[Callable] = None):
        """设置回调函数"""
        self.on_show_callback = on_show
        self.on_quit_callback = on_quit
    
    def minimize_to_tray(self):
        """最小化到系统托盘"""
        self._on_hide()
    
    def restore_from_tray(self):
        """从系统托盘恢复"""
        self._on_show()


class HotkeyManager:
    """全局快捷键管理器"""
    
    def __init__(self):
        """初始化快捷键管理器"""
        self.hotkeys = {}
        self.enabled = False
    
    def register(self, hotkey: str, callback: Callable):
        """注册全局快捷键
        
        Args:
            hotkey: 快捷键组合 (如 'Ctrl+Shift+Space')
            callback: 快捷键触发时调用的函数
        """
        try:
            self.hotkeys[hotkey] = callback
            logger.info(f"Registered hotkey: {hotkey}")
        except Exception as e:
            logger.error(f"Failed to register hotkey {hotkey}: {e}")
    
    def unregister(self, hotkey: str):
        """注销全局快捷键"""
        if hotkey in self.hotkeys:
            del self.hotkeys[hotkey]
            logger.info(f"Unregistered hotkey: {hotkey}")
    
    def enable(self):
        """启用快捷键监听"""
        self.enabled = True
        logger.info("Hotkeys enabled")
    
    def disable(self):
        """禁用快捷键监听"""
        self.enabled = False
        logger.info("Hotkeys disabled")


class AutoStartManager:
    """开机自启动管理器"""
    
    def __init__(self, app_name: str, app_path: str):
        """初始化自启动管理器
        
        Args:
            app_name: 应用名称
            app_path: 应用可执行文件路径
        """
        self.app_name = app_name
        self.app_path = app_path
    
    def is_enabled(self) -> bool:
        """检查是否已启用开机自启动"""
        import sys
        import os
        
        try:
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_READ
                )
                try:
                    winreg.QueryValueEx(key, self.app_name)
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            
            elif sys.platform == "darwin":
                # macOS: Check LaunchAgents
                plist_path = os.path.expanduser(
                    f"~/Library/LaunchAgents/com.{self.app_name}.plist"
                )
                return os.path.exists(plist_path)
            
            elif sys.platform.startswith("linux"):
                # Linux: Check autostart desktop file
                desktop_path = os.path.expanduser(
                    f"~/.config/autostart/{self.app_name}.desktop"
                )
                return os.path.exists(desktop_path)
        
        except Exception as e:
            logger.error(f"Failed to check auto-start status: {e}")
            return False
    
    def enable(self) -> bool:
        """启用开机自启动"""
        import sys
        import os
        
        try:
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_WRITE
                )
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, self.app_path)
                winreg.CloseKey(key)
                logger.info("Auto-start enabled (Windows)")
                return True
            
            elif sys.platform == "darwin":
                # macOS: Create LaunchAgent plist
                plist_dir = os.path.expanduser("~/Library/LaunchAgents")
                os.makedirs(plist_dir, exist_ok=True)
                
                plist_path = os.path.join(plist_dir, f"com.{self.app_name}.plist")
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{self.app_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{self.app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                with open(plist_path, "w", encoding="utf-8") as f:
                    f.write(plist_content)
                logger.info("Auto-start enabled (macOS)")
                return True
            
            elif sys.platform.startswith("linux"):
                # Linux: Create autostart desktop file
                autostart_dir = os.path.expanduser("~/.config/autostart")
                os.makedirs(autostart_dir, exist_ok=True)
                
                desktop_path = os.path.join(autostart_dir, f"{self.app_name}.desktop")
                desktop_content = f"""[Desktop Entry]
Type=Application
Name={self.app_name}
Exec={self.app_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true"""
                with open(desktop_path, "w", encoding="utf-8") as f:
                    f.write(desktop_content)
                logger.info("Auto-start enabled (Linux)")
                return True
        
        except Exception as e:
            logger.error(f"Failed to enable auto-start: {e}")
            return False
    
    def disable(self) -> bool:
        """禁用开机自启动"""
        import sys
        import os
        
        try:
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_WRITE
                )
                try:
                    winreg.DeleteValue(key, self.app_name)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
                logger.info("Auto-start disabled (Windows)")
                return True
            
            elif sys.platform == "darwin":
                plist_path = os.path.expanduser(
                    f"~/Library/LaunchAgents/com.{self.app_name}.plist"
                )
                if os.path.exists(plist_path):
                    os.remove(plist_path)
                logger.info("Auto-start disabled (macOS)")
                return True
            
            elif sys.platform.startswith("linux"):
                desktop_path = os.path.expanduser(
                    f"~/.config/autostart/{self.app_name}.desktop"
                )
                if os.path.exists(desktop_path):
                    os.remove(desktop_path)
                logger.info("Auto-start disabled (Linux)")
                return True
        
        except Exception as e:
            logger.error(f"Failed to disable auto-start: {e}")
            return False
