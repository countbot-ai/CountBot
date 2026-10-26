# resources

桌面端打包使用的应用图标，三个平台各一份。

| 文件 | 平台 | 引用方 |
| --- | --- | --- |
| `countbot.ico` | Windows | `start_desktop.py`、`.github/workflows/build-desktop.yml` |
| `countbot.icns` | macOS | 同上 |
| `countbot.png` | Linux | 同上 |

`start_desktop.py` 按 `platform.system()` 选择对应文件；CI 打包流程由 workflow
的 icon 步骤解析路径后传给 PyInstaller 的 `--icon`。请勿删除或重命名。
