# Python 环境变量读写

## 1、os.getenv —— 读取环境变量

```python
import os

# 读取环境变量 HOST，如果不存在则返回默认值 "127.0.0.1"
host = os.getenv("HOST", "127.0.0.1")

# 不提供默认值时，找不到则返回 None
value = os.getenv("SOME_VAR")  # 可能是 None
```

## 2、os.environ —— 读写环境变量

```python
import os

# 写入环境变量
os.environ["HOST"] = "0.0.0.0"

# 读取环境变量（如果不存在会抛出 KeyError）
host = os.environ["HOST"]

# 安全读取（等价于 os.getenv）
host = os.environ.get("HOST", "127.0.0.1")
```

### （1）os.getenv vs os.environ 的区别

| 操作 | os.getenv(key, default) | os.environ[key] | os.environ.get(key, default) |
|------|------------------------|-----------------|------------------------------|
| 读取 | 有值返回值，无值返回 default | 有值返回值，无值抛 KeyError | 同 os.getenv |
| 写入 | 不支持 | 支持 | 不支持 |

## 3、"读取 → 回写"模式

本项目中的用法：

```python
host = os.getenv("HOST", "127.0.0.1")  # 读取，没有就用默认值
os.environ["HOST"] = host               # 回写，确保环境变量一定有值
```

这样做的目的是：即使用户没有设置环境变量，后续代码通过 `os.getenv("HOST")` 也一定能拿到值，不会得到 `None`。

## 4、环境变量从哪里来

环境变量可以通过以下方式设置：

### （1）命令行启动时设置

```bash
HOST=0.0.0.0 PORT=9000 python start_app.py
```

### （2）在 shell 中 export

```bash
export HOST=0.0.0.0
export PORT=9000
python start_app.py
```

### （3）写在 .env 文件中（需配合 python-dotenv 库）

`.env` 文件本身只是一个普通的文本文件，Python 不会自动读取它。需要借助 `python-dotenv` 库来加载。

**第一步：安装库**

```bash
pip install python-dotenv
```

**第二步：在项目根目录创建 `.env` 文件**

```
# .env 文件
HOST=0.0.0.0
PORT=9000
SECRET_KEY=my-secret-key
```

**第三步：在代码中加载**

```python
from dotenv import load_dotenv
import os

# 读取 .env 文件，把里面的变量加载到环境变量中
load_dotenv()

# 之后就可以正常用 os.getenv 读取了
host = os.getenv("HOST")       # "0.0.0.0"
port = os.getenv("PORT")       # "9000"
```

`load_dotenv()` 的作用就是读取 `.env` 文件，把每一行的 `KEY=VALUE` 注入到 `os.environ` 中。调用之后，和手动 `export` 效果一样。

**常用参数：**

```python
# 指定 .env 文件路径（默认查找当前目录下的 .env）
load_dotenv("/path/to/my/.env")

# override=True 会覆盖已有的环境变量（默认不覆盖）
load_dotenv(override=True)
```

**注意事项：**
- `.env` 文件通常加入 `.gitignore`，不提交到代码仓库，因为里面可能包含密钥等敏感信息
- `load_dotenv()` 默认**不会覆盖**已存在的环境变量，命令行设置的值优先级更高
- `.env` 文件中不需要加 `export`，也不需要给值加引号（加了也行）

### （4）写在 shell 配置文件中（~/.bashrc、~/.zshrc）

```bash
export HOST=0.0.0.0
```

### （5）Docker / Docker Compose 中设置

```yaml
environment:
  - HOST=0.0.0.0
  - PORT=8000
```

## 5、注意事项

- 环境变量的值都是**字符串类型**，如果需要整数要自己转换：`int(os.getenv("PORT", "8000"))`
- 环境变量只在**当前进程及其子进程**中生效，不会影响其他进程
- `os.environ` 的修改是实时的，修改后同一进程内立即可读
