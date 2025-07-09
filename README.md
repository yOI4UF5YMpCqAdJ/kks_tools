# RMVB to MP4 视频转换工具

这是一个Python工具类，用于将RMVB文件转换为MP4文件。

## 功能特性

- 单文件转换：将单个RMVB文件转换为MP4
- 批量转换：批量转换目录中的所有RMVB文件
- 多种质量设置：支持低、中、高三种转换质量
- 日志记录：详细的转换过程日志
- 错误处理：完善的错误处理机制
- 命令行界面：支持命令行操作

## 系统要求

- Python 3.6+
- FFmpeg（需要单独安装）

## 安装FFmpeg

### Windows
1. 下载FFmpeg：https://ffmpeg.org/download.html
2. 解压到任意目录
3. 将FFmpeg的bin目录添加到系统PATH环境变量中

### macOS
```bash
brew install ffmpeg
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install ffmpeg
```

## 使用方法

### 1. 作为Python模块使用

```python
from convertRmvbToMp4 import VideoConverter

# 创建转换器实例
converter = VideoConverter()

# 单文件转换
success = converter.convert_rmvb_to_mp4(
    input_file="input.rmvb",
    output_file="output.mp4",
    quality="medium",
    overwrite=True
)

if success:
    print("转换成功!")
else:
    print("转换失败!")

# 批量转换
successful_files = converter.batch_convert_rmvb_to_mp4(
    input_dir="./videos",
    output_dir="./converted",
    quality="high",
    overwrite=True
)

print(f"成功转换了 {len(successful_files)} 个文件")
```

### 2. 命令行使用

```bash
# 单文件转换
python convertRmvbToMp4.py input.rmvb -o output.mp4 -q medium -f

# 批量转换
python convertRmvbToMp4.py ./videos --batch -o ./converted -q high -f

# 查看帮助
python convertRmvbToMp4.py --help
```

## 命令行参数

- `input`: 输入文件或目录路径
- `-o, --output`: 输出文件或目录路径
- `-q, --quality`: 转换质量 (low, medium, high)
- `-f, --force`: 覆盖已存在的文件
- `--batch`: 批量转换模式
- `--ffmpeg`: 指定FFmpeg可执行文件路径

## 质量设置

- **low**: 快速转换，文件较小，质量较低
- **medium**: 平衡质量和文件大小（默认）
- **high**: 高质量，文件较大，转换较慢

## 日志

转换过程中的日志会同时输出到控制台和 `video_converter.log` 文件中。

## 错误处理

- 自动检查FFmpeg是否可用
- 验证输入文件是否存在
- 检查输出文件是否已存在
- 处理转换过程中的各种异常

## 示例

### 基本使用
```python
from convertRmvbToMp4 import VideoConverter

converter = VideoConverter()
converter.convert_rmvb_to_mp4("movie.rmvb", "movie.mp4")
```

### 高质量转换
```python
converter.convert_rmvb_to_mp4(
    "movie.rmvb", 
    "movie_hq.mp4", 
    quality="high"
)
```

### 批量转换
```python
converter.batch_convert_rmvb_to_mp4(
    input_dir="./old_videos",
    output_dir="./new_videos",
    quality="medium"
)
```

### 获取视频信息
```python
info = converter.get_video_info("movie.rmvb")
if info:
    print(f"视频时长: {info['format']['duration']} 秒")
```

## 注意事项

1. 转换过程可能需要较长时间，特别是大文件或高质量设置
2. 确保有足够的磁盘空间存储输出文件
3. 转换质量越高，文件越大，转换时间越长
4. 建议在转换前备份原始文件
