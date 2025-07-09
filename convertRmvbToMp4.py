import os
import subprocess
import sys
import threading
import time
import re
from pathlib import Path
from typing import Optional, List, Callable
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_converter.log'),
        logging.StreamHandler()
    ]
)

class VideoConverter:
    """视频转换工具类"""
    
    def __init__(self, ffmpeg_path: Optional[str] = None):
        """
        初始化视频转换器
        
        Args:
            ffmpeg_path: FFmpeg可执行文件的路径，如果为None则使用系统PATH中的ffmpeg
        """
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.logger = logging.getLogger(__name__)
        
        # 检查FFmpeg是否可用
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg未找到，请确保FFmpeg已安装并添加到系统PATH中")
    
    def _check_ffmpeg(self) -> bool:
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _get_video_duration(self, video_file: str) -> Optional[float]:
        """获取视频文件的总时长（秒）"""
        try:
            cmd = [
                self.ffmpeg_path.replace('ffmpeg', 'ffprobe'),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                video_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                if 'format' in data and 'duration' in data['format']:
                    return float(data['format']['duration'])
            return None
            
        except Exception:
            return None
    
    def _parse_ffmpeg_progress(self, line: str) -> Optional[float]:
        """
        解析FFmpeg输出中的时间信息
        
        FFmpeg在使用-progress参数时会输出形如 time=00:01:23.45 的进度信息
        这个方法将时间字符串转换为总秒数，用于计算转换进度
        
        Args:
            line: FFmpeg输出的一行文本
            
        Returns:
            float: 当前转换到的时间点（秒），如果无法解析则返回None
        """
        # 使用正则表达式匹配时间格式 time=00:01:23.45
        # 分组1: 小时, 分组2: 分钟, 分组3: 秒（可能包含小数）
        time_match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
        if time_match:
            hours = int(time_match.group(1))
            minutes = int(time_match.group(2))
            seconds = float(time_match.group(3))
            # 将时:分:秒转换为总秒数
            return hours * 3600 + minutes * 60 + seconds
        return None
    
    def _run_ffmpeg_with_progress(
        self, 
        cmd: List[str], 
        total_duration: float, 
        progress_callback: Optional[Callable[[float, str], None]]
    ) -> subprocess.CompletedProcess:
        """
        运行FFmpeg并监控进度
        
        这是异步进度监控的核心方法：
        1. 使用-progress pipe:1参数让FFmpeg输出进度信息到stdout
        2. 创建子进程，分别处理stdout（进度）和stderr（错误信息）
        3. 使用多线程实时读取输出，避免阻塞
        4. 解析时间信息计算百分比进度
        
        Args:
            cmd: FFmpeg命令列表
            total_duration: 视频总时长（秒）
            progress_callback: 进度回调函数
            
        Returns:
            subprocess.CompletedProcess: 模拟的进程结果对象
        """
        
        # 在输出文件前插入进度参数：-progress pipe:1
        # 这样FFmpeg会将进度信息输出到stdout，而不是stderr
        cmd_with_progress = cmd[:-1] + ['-progress', 'pipe:1'] + [cmd[-1]]
        
        # 创建子进程，分别捕获stdout和stderr
        process = subprocess.Popen(
            cmd_with_progress,
            stdout=subprocess.PIPE,  # 用于读取进度信息
            stderr=subprocess.PIPE,  # 用于读取错误信息
            text=True,
            universal_newlines=True
        )
        
        # 用于收集stderr输出（错误信息）
        stderr_output = []
        
        def read_stderr():
            """
            在单独线程中读取stderr输出
            避免stderr缓冲区满导致进程阻塞
            """
            for line in iter(process.stderr.readline, ''):
                stderr_output.append(line)
        
        # 启动stderr读取线程，设置为守护线程
        stderr_thread = threading.Thread(target=read_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()
        
        # 从stdout读取进度信息
        last_progress = 0.0
        while True:
            line = process.stdout.readline()
            if not line:  # 没有更多输出时跳出循环
                break
                
            # 解析当前转换到的时间点
            current_time = self._parse_ffmpeg_progress(line)
            if current_time is not None and total_duration > 0:
                # 计算转换百分比，确保不超过100%
                progress = min((current_time / total_duration) * 100, 100.0)
                
                # 只有进度变化超过1%时才更新，避免过于频繁的回调
                # 这样可以减少UI更新频率，提高性能
                if progress - last_progress >= 1.0:
                    if progress_callback:
                        progress_callback(progress, f"转换中... {progress:.1f}%")
                    last_progress = progress
            
            # 检查是否包含结束标志
            if 'progress=' in line:
                if 'end' in line:
                    break
        
        # 等待进程结束
        process.wait()
        # 等待stderr线程结束（最多1秒）
        stderr_thread.join(timeout=1)
        
        # 构造返回对象，模拟subprocess.CompletedProcess
        class Result:
            def __init__(self, returncode, stderr):
                self.returncode = returncode
                self.stderr = stderr
        
        return Result(process.returncode, ''.join(stderr_output))
    
    def convert_rmvb_to_mp4(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        quality: str = "medium",
        overwrite: bool = False,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """
        将RMVB文件转换为MP4文件
        
        Args:
            input_file: 输入的RMVB文件路径
            output_file: 输出的MP4文件路径，如果为None则自动生成
            quality: 转换质量 ('low', 'medium', 'high')
            overwrite: 是否覆盖已存在的输出文件
            progress_callback: 进度回调函数，接收(progress, status)参数
            
        Returns:
            bool: 转换成功返回True，否则返回False
        """
        # 检查输入文件
        input_path = Path(input_file)
        if not input_path.exists():
            self.logger.error(f"输入文件不存在: {input_file}")
            return False
        
        if not input_path.suffix.lower() == '.rmvb':
            self.logger.warning(f"输入文件不是RMVB格式: {input_file}")
        
        # 生成输出文件路径
        if output_file is None:
            output_file = str(input_path.with_suffix('.mp4'))
        
        output_path = Path(output_file)
        
        # 检查输出文件是否已存在
        if output_path.exists() and not overwrite:
            self.logger.error(f"输出文件已存在: {output_file}，使用overwrite=True来覆盖")
            return False
        
        # 创建输出目录
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 获取视频总时长用于进度计算
        # 这是实现进度监控的关键步骤：必须知道视频总时长才能计算百分比
        total_duration = self._get_video_duration(str(input_path))
        if total_duration is None:
            self.logger.warning("无法获取视频时长，进度显示可能不准确")
            total_duration = 0
        
        # 根据质量设置编码参数
        quality_settings = {
            'low': ['-crf', '28', '-preset', 'fast'],
            'medium': ['-crf', '23', '-preset', 'medium'],
            'high': ['-crf', '18', '-preset', 'slow']
        }
        
        if quality not in quality_settings:
            self.logger.warning(f"未知的质量设置: {quality}，使用默认设置")
            quality = 'medium'
        
        # 构建FFmpeg命令
        # 使用H.264编码器和AAC音频编码器，这是最兼容的组合
        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),        # 输入文件
            '-c:v', 'libx264',            # 视频编码器：H.264
            '-c:a', 'aac',                # 音频编码器：AAC
            *quality_settings[quality],   # 质量设置（CRF值和preset）
            '-movflags', '+faststart',    # 优化网络播放：将metadata移到文件开头
        ]
        
        # 如果允许覆盖，添加-y参数
        if overwrite:
            cmd.append('-y')
        
        # 添加输出文件路径
        cmd.append(str(output_path))
        
        try:
            self.logger.info(f"开始转换: {input_file} -> {output_file}")
            self.logger.info(f"使用质量设置: {quality}")
            
            if progress_callback:
                progress_callback(0.0, "开始转换...")
            
            # 执行转换，带进度监控
            result = self._run_ffmpeg_with_progress(
                cmd, 
                total_duration, 
                progress_callback
            )
            
            if result.returncode == 0:
                self.logger.info(f"转换成功: {output_file}")
                if progress_callback:
                    progress_callback(100.0, "转换完成!")
                return True
            else:
                self.logger.error(f"转换失败: {result.stderr}")
                if progress_callback:
                    progress_callback(-1, f"转换失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("转换超时")
            if progress_callback:
                progress_callback(-1, "转换超时")
            return False
        except Exception as e:
            self.logger.error(f"转换过程中发生错误: {str(e)}")
            if progress_callback:
                progress_callback(-1, f"转换错误: {str(e)}")
            return False
    
    def batch_convert_rmvb_to_mp4(
        self,
        input_dir: str,
        output_dir: Optional[str] = None,
        quality: str = "medium",
        overwrite: bool = False,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[str]:
        """
        批量转换目录中的RMVB文件为MP4文件
        
        Args:
            input_dir: 输入目录路径
            output_dir: 输出目录路径，如果为None则与输入目录相同
            quality: 转换质量
            overwrite: 是否覆盖已存在的文件
            progress_callback: 进度回调函数，接收(progress, status)参数
            
        Returns:
            List[str]: 成功转换的文件列表
        """
        input_path = Path(input_dir)
        if not input_path.exists() or not input_path.is_dir():
            self.logger.error(f"输入目录不存在或不是目录: {input_dir}")
            return []
        
        if output_dir is None:
            output_dir = input_dir
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 查找所有RMVB文件
        rmvb_files = list(input_path.glob("*.rmvb")) + list(input_path.glob("*.RMVB"))
        
        if not rmvb_files:
            self.logger.info(f"在目录 {input_dir} 中未找到RMVB文件")
            return []
        
        self.logger.info(f"找到 {len(rmvb_files)} 个RMVB文件")
        
        successful_conversions = []
        
        for rmvb_file in rmvb_files:
            output_file = output_path / f"{rmvb_file.stem}.mp4"
            
            if self.convert_rmvb_to_mp4(
                str(rmvb_file),
                str(output_file),
                quality=quality,
                overwrite=overwrite
            ):
                successful_conversions.append(str(output_file))
        
        self.logger.info(f"批量转换完成，成功转换 {len(successful_conversions)} 个文件")
        return successful_conversions
    
    def get_video_info(self, video_file: str) -> Optional[dict]:
        """
        获取视频文件信息
        
        Args:
            video_file: 视频文件路径
            
        Returns:
            dict: 视频信息字典，如果失败则返回None
        """
        try:
            cmd = [
                self.ffmpeg_path.replace('ffmpeg', 'ffprobe'),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            else:
                self.logger.error(f"获取视频信息失败: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取视频信息时发生错误: {str(e)}")
            return None
def convert_video(
    input_path: str, 
    output_path: Optional[str] = None, 
    batch_mode: bool = False,
    quality: str = "high",
    overwrite: bool = False,
    ffmpeg_path: Optional[str] = None,
    show_progress: bool = True
) -> bool:
    """
    便捷函数：无需命令行参数直接转换视频
    
    Args:
        input_path: 输入文件或目录路径
        output_path: 输出文件或目录路径，None时自动生成
        batch_mode: 是否批量转换模式
        quality: 转换质量 ('low', 'medium', 'high')
        overwrite: 是否覆盖已存在的文件
        ffmpeg_path: FFmpeg可执行文件路径
        show_progress: 是否在控制台显示进度
        
    Returns:
        bool: 转换成功返回True，否则返回False
    """
    try:
        converter = VideoConverter(ffmpeg_path=ffmpeg_path)
        
        # 进度回调函数
        def progress_handler(progress: float, status: str):
            if show_progress:
                if progress < 0:  # 错误状态
                    print(f"\r{status}", end="", flush=True)
                else:
                    print(f"\r{status}", end="", flush=True)
                if progress >= 100:
                    print()  # 完成后换行
        
        if batch_mode:
            # 批量转换模式
            successful = converter.batch_convert_rmvb_to_mp4(
                input_path,
                output_path,
                quality=quality,
                overwrite=overwrite,
                progress_callback=progress_handler if show_progress else None
            )
            return len(successful) > 0
        else:
            # 单文件转换模式
            return converter.convert_rmvb_to_mp4(
                input_path,
                output_path,
                quality=quality,
                overwrite=overwrite,
                progress_callback=progress_handler if show_progress else None
            )
                
    except Exception as e:
        print(f"错误: {str(e)}")
        return False

def main():
    """主函数，提供命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="RMVB to MP4 视频转换工具")
    parser.add_argument("input", help="输入文件或目录路径")
    parser.add_argument("-o", "--output", help="输出文件或目录路径")
    parser.add_argument("-q", "--quality", choices=['low', 'medium', 'high'], 
                       default='high', help="转换质量")
    parser.add_argument("-f", "--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--batch", action="store_true", help="批量转换模式")
    parser.add_argument("--ffmpeg", help="FFmpeg可执行文件路径")
    
    args = parser.parse_args()
    
    try:
        # 创建命令行进度条显示函数
        def cli_progress_callback(progress, status):
            # 进度小于0表示错误状态
            if progress < 0:
                print(f"\r{status}", flush=True)
                return
                
            # 创建一个简单的进度条 [=====>    ] 50.5%
            bar_length = 30
            filled_length = int(bar_length * progress / 100)
            bar = '=' * filled_length + '>' + ' ' * (bar_length - filled_length - 1)
            
            # 显示进度条和状态消息
            print(f"\r[{bar}] {progress:.1f}% {status}", end='', flush=True)
            
            # 如果进度达到100%，添加换行符
            if progress >= 100:
                print()
        
        converter = VideoConverter(ffmpeg_path=args.ffmpeg)
        
        if args.batch:
            # 批量转换模式
            successful = converter.batch_convert_rmvb_to_mp4(
                args.input,
                args.output,
                quality=args.quality,
                overwrite=args.force,
                progress_callback=cli_progress_callback
            )
            print(f"批量转换完成，成功转换 {len(successful)} 个文件")
        else:
            # 单文件转换模式
            success = converter.convert_rmvb_to_mp4(
                args.input,
                args.output,
                quality=args.quality,
                overwrite=args.force,
                progress_callback=cli_progress_callback
            )
            if success:
                print("转换成功!")
            else:
                print("转换失败!")
                sys.exit(1)
                
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    '''
    python convertRmvbToMp4.py D:\Projects\kks-tools\data\t1.rmvb -o D:\Projects\kks-tools\data\output.mp4 -q high -f
    '''
    main()

