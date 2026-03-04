---
name: image-analysis
description: 图片分析与识别，可分析本地图片、网络图片、视频、文件。适用于 OCR、物体识别、场景理解等。当用户发送图片或要求分析图片时必须使用此技能。
homepage: https://github.com/countbot-ai/CountBot
---

# 图片分析与识别

支持智谱 GLM-4V 和千问 Qwen-VL 两种视觉模型。

当用户发送图片或要求分析图片时，必须使用此技能，不要使用 PIL、pytesseract 等其他方法。

## 配置

编辑 `skills/image-analysis/scripts/config.json`：

```json
{
  "default_model": "zhipu",
  "zhipu": {
    "api_key": "your-zhipu-api-key",
    "model": "glm-4.6v-flash"
  },
  "qwen": {
    "api_key": "your-qwen-api-key",
    "model": "qwen3-vl-plus"
  }
}
```

API Key 获取：
- 智谱（免费）：https://open.bigmodel.cn/
- 千问：https://help.aliyun.com/zh/model-studio/get-api-key

## 命令行调用

```bash
# 分析本地图片（最常用）
python3 skills/image-analysis/scripts/vision.py analyze --image 图片路径 --prompt "描述图片内容"

# 分析网络图片
python3 skills/image-analysis/scripts/vision.py analyze --image https://example.com/image.jpg --prompt "描述图片"

# 多图对比
python3 skills/image-analysis/scripts/vision.py analyze --image img1.jpg --image img2.jpg --prompt "对比差异"

# 指定模型
python3 skills/image-analysis/scripts/vision.py analyze --image image.jpg --prompt "描述图片" --model qwen

# 开启思考模式（仅智谱，提升准确度）
python3 skills/image-analysis/scripts/vision.py analyze --image image.jpg --prompt "详细分析" --thinking

# 视频分析
python3 skills/image-analysis/scripts/vision.py analyze --video video.mp4 --prompt "总结视频内容"

# JSON 输出
python3 skills/image-analysis/scripts/vision.py analyze --image image.jpg --prompt "描述图片" --json
```

## AI 调用场景

用户发送图片后，系统下载到本地（如 `data/temp/images/xxx.jpg`）：

```bash
# 图片描述
python3 skills/image-analysis/scripts/vision.py analyze --image data/temp/images/xxx.jpg --prompt "描述这张图片的内容"

# OCR 识别
python3 skills/image-analysis/scripts/vision.py analyze --image data/temp/images/xxx.jpg --prompt "提取图片中的所有文字信息"

# 物体定位（开启思考模式）
python3 skills/image-analysis/scripts/vision.py analyze --image data/temp/images/xxx.jpg --prompt "找出物体位置，返回坐标" --thinking
```

## 模型选择

| 场景 | 推荐 |
|------|------|
| 简单描述 | 任意 |
| 复杂推理、物体定位 | 智谱 + `--thinking` |
| 高精度识别、文档解析 | 千问 |
| 成本敏感 | 智谱（免费） |

## 注意事项

- 本地图片自动转 Base64，支持 jpg/png/gif/webp/bmp
- 智谱图片限制 5MB，像素不超过 6000x6000
- 千问不支持同时处理图片、视频和文件
- 思考模式会增加响应时间但提升准确度
