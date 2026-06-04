import os
from PIL import Image
import threading
from pathlib import Path

class GifSplitter:
    """GIF拆分工具类"""
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.is_running = False
        self.stop_flag = False
        
    def log(self, message):
        """日志记录"""
        if self.log_callback:
            self.log_callback(message)
    
    def split_gif(self, gif_path, output_dir=None, output_format='png'):
        """
        拆分GIF为一系列图片
        
        参数:
            gif_path: GIF文件路径
            output_dir: 输出目录，如果为None则在GIF所在目录创建新文件夹
            output_format: 输出图片格式 (png, jpg, bmp等)
        """
        if not os.path.exists(gif_path):
            raise FileNotFoundError(f"GIF文件不存在: {gif_path}")
            
        if not output_dir:
            # 在GIF所在目录创建新文件夹
            gif_dir = os.path.dirname(gif_path)
            gif_name = os.path.splitext(os.path.basename(gif_path))[0]
            output_dir = os.path.join(gif_dir, f"{gif_name}_frames")
            
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            with Image.open(gif_path) as img:
                # 获取GIF信息
                frame_count = 0
                gif_info = {
                    'format': img.format,
                    'size': img.size,
                    'mode': img.mode,
                    'is_animated': getattr(img, 'is_animated', False)
                }
                
                self.log(f"开始拆分GIF: {os.path.basename(gif_path)}")
                self.log(f"GIF信息: 格式={gif_info['format']}, 尺寸={gif_info['size']}, "
                        f"动画={gif_info['is_animated']}")
                
                if gif_info['is_animated']:
                    # 处理动画GIF
                    frame_count = 0
                    while True:
                        try:
                            # 保存当前帧
                            frame_path = os.path.join(output_dir, f"frame_{frame_count:04d}.{output_format}")
                            img.save(frame_path, format=output_format.upper())
                            self.log(f"已保存帧 {frame_count}: {os.path.basename(frame_path)}")
                            
                            frame_count += 1
                            img.seek(img.tell() + 1)  # 移动到下一帧
                        except EOFError:
                            break  # 到达文件末尾
                        except Exception as e:
                            self.log(f"处理帧 {frame_count} 时出错: {str(e)}")
                            break
                else:
                    # 处理静态GIF（单帧）
                    frame_path = os.path.join(output_dir, f"frame_0000.{output_format}")
                    img.save(frame_path, format=output_format.upper())
                    frame_count = 1
                    self.log(f"已保存静态帧: {os.path.basename(frame_path)}")
                
                self.log(f"GIF拆分完成! 共拆分为 {frame_count} 帧")
                self.log(f"输出目录: {output_dir}")
                
                return {
                    'success': True,
                    'frame_count': frame_count,
                    'output_dir': output_dir,
                    'gif_info': gif_info
                }
                
        except Exception as e:
            error_msg = f"拆分GIF时出错: {str(e)}"
            self.log(error_msg)
            return {'success': False, 'error': error_msg}
    
    def split_gif_async(self, gif_path, output_dir=None, output_format='png', 
                       callback=None, progress_callback=None):
        """异步拆分GIF"""
        def _split_thread():
            self.is_running = True
            self.stop_flag = False
            
            try:
                result = self.split_gif(gif_path, output_dir, output_format)
                if callback:
                    callback(result)
            except Exception as e:
                if callback:
                    callback({'success': False, 'error': str(e)})
            finally:
                self.is_running = False
                
        thread = threading.Thread(target=_split_thread, daemon=True)
        thread.start()
        return thread