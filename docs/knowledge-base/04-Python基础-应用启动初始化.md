# Python 应用启动初始化

本项目 `start_app.py` 在启动 Web 服务之前，做了几项初始化工作。

## 1、Windows UTF-8 编码兼容

```python
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
```

### （1）为什么需要

Windows 终端默认编码不是 UTF-8（中文 Windows 默认是 GBK/CP936），直接输出中文会乱码。

### （2）做了什么

| 代码 | 作用 |
|------|------|
| `PYTHONIOENCODING=utf-8` | 让 Python 标准输入输出使用 UTF-8 编码 |
| `SetConsoleCP(65001)` | 设置控制台**输入**编码为 UTF-8（65001 是 UTF-8 的代码页编号） |
| `SetConsoleOutputCP(65001)` | 设置控制台**输出**编码为 UTF-8 |

### （3）ctypes 是什么

`ctypes` 是 Python 标准库，可以直接调用 C 语言编写的动态链接库（DLL）。这里用它调用了 Windows 系统的 `kernel32.dll` 来设置控制台编码。

### （4）为什么只在 Windows 上执行

Mac 和 Linux 默认就是 UTF-8，不需要额外设置。`sys.platform == "win32"` 判断当前是否为 Windows 系统。

## 2、添加项目根目录到 Python 路径

```python
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
```

### （1）为什么需要

Python 导入模块时，会在 `sys.path` 列表中的目录里查找。如果不把项目根目录加入 `sys.path`，从其他目录运行脚本时可能找不到 `backend` 模块。

### （2）做了什么

- `Path(__file__).parent`：获取当前脚本所在的目录（即项目根目录）
- `sys.path.insert(0, ...)`：插入到搜索路径的**最前面**，确保优先找到本项目的模块

### （3）__file__ 是什么

`__file__` 是 Python 的内置变量，表示**当前脚本文件的路径**。

```
假设项目结构：
/home/user/CountBot/
├── start_app.py          ← __file__ = "/home/user/CountBot/start_app.py"
├── backend/
│   ├── app.py
│   └── utils/
```

`Path(__file__).parent` = `/home/user/CountBot/`

## 3、SSL 证书配置

```python
from backend.utils.ssl_compat import ensure_ssl_certificates
ensure_ssl_certificates()
```

### （1）为什么需要

应用需要发送 HTTPS 请求（比如调用外部 AI API），HTTPS 需要 SSL/TLS 证书来验证服务器身份。

在以下环境中可能找不到系统 CA 证书：
- 打包后的桌面应用（PyInstaller 等）
- 部分 Windows 系统
- 精简的 Docker 镜像

### （2）做了什么

提前检查并配置好 SSL 证书路径，确保后续所有 HTTPS 请求不会报 `SSLCertVerificationError`。

## 4、webbrowser 打开浏览器

```python
import webbrowser

def open_browser_delayed(url, delay=2.0):
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()
```

### （1）做了什么

启动后延迟 2 秒，用系统默认浏览器打开应用页面。

### （2）注意事项

- `webbrowser` 是 Python 标准库，不需要安装
- 在无图形界面的环境（如云服务器）中会静默失败，不影响服务运行
- 用 `daemon=True` 创建守护线程，确保主程序退出时这个线程也会自动结束
