"""
GIF粒子批量切片工具 — 核心逻辑模块

提供遮罩定义、批量裁剪、遮罩持久化等功能，零GUI依赖。
"""

import os
import json
import threading
from dataclasses import dataclass, asdict
from typing import List, Optional, Callable
from PIL import Image


@dataclass
class MaskDef:
    """单个矩形遮罩的定义，所有坐标使用原始图像坐标系"""
    id: int          # 遮罩编号，自增
    label: str       # 显示标签，如 "mask_01"
    x: int           # 左上角X（原始图像像素坐标）
    y: int           # 左上角Y
    width: int       # 宽度（像素）
    height: int      # 高度（像素）
    inverse: bool = False  # True=剔除遮罩区域, False=提取遮罩区域


class ParticleExtractor:
    """粒子提取器 — 使用遮罩从帧序列中批量裁剪粒子图片"""

    # 支持的图片扩展名
    SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        """
        初始化粒子提取器

        参数:
            log_callback: 日志回调函数，用于将日志消息传递到GUI层
        """
        self.log_callback = log_callback
        self.is_running = False
        self.stop_flag = False

    # ---------- 日志 ----------
    def log(self, message: str):
        """输出日志（通过回调传递到GUI）"""
        if self.log_callback:
            self.log_callback(message)

    # ---------- 图片扫描 ----------
    def scan_frame_files(self, frames_dir: str) -> List[str]:
        """
        扫描帧目录下的所有图片文件，按文件名排序

        参数:
            frames_dir: 帧序列图片所在目录

        返回:
            排序后的图片文件路径列表

        异常:
            FileNotFoundError: 目录不存在
            ValueError: 目录中没有支持的图片文件
        """
        if not os.path.isdir(frames_dir):
            raise FileNotFoundError(f"帧目录不存在: {frames_dir}")

        files = []
        for f in os.listdir(frames_dir):
            if f.lower().endswith(self.SUPPORTED_EXTENSIONS):
                files.append(os.path.join(frames_dir, f))

        files.sort()
        if not files:
            raise ValueError(f"目录中没有找到支持的图片文件: {frames_dir}")

        return files

    # ---------- 批量提取 ----------
    def extract_particles(
        self,
        masks: List[MaskDef],
        frames_dir: str,
        output_dir: str,
        output_format: str = 'png',
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> dict:
        """
        对帧目录下所有图片应用遮罩，裁剪出粒子图片

        参数:
            masks: 遮罩定义列表
            frames_dir: 帧序列图片所在目录
            output_dir: 输出根目录（每个遮罩会创建子目录）
            output_format: 输出图片格式 (png/jpg/bmp)
            progress_callback: 进度回调 (current_frame_index, total_frames)

        返回:
            {'success': bool, 'frame_count': int, 'mask_count': int, 'output_dir': str}

        异常:
            ValueError: 遮罩为空或帧目录无图片
        """
        if not masks:
            raise ValueError("遮罩列表为空，请先创建遮罩")

        # 扫描帧文件
        frame_files = self.scan_frame_files(frames_dir)
        total = len(frame_files)

        self.log(f"开始批量提取粒子")
        self.log(f"帧目录: {frames_dir}")
        self.log(f"找到 {total} 帧图片，{len(masks)} 个遮罩区域")
        self.log(f"输出目录: {output_dir}")

        # 为每个遮罩创建输出子目录
        for mask in masks:
            mask_dir = os.path.join(output_dir, mask.label)
            os.makedirs(mask_dir, exist_ok=True)
            self.log(f"  创建输出子目录: {mask.label}/")

        # 逐帧处理
        for idx, frame_path in enumerate(frame_files):
            if self.stop_flag:
                self.log("批量提取已被用户停止")
                break

            filename = os.path.basename(frame_path)
            name_without_ext = os.path.splitext(filename)[0]
            ext = os.path.splitext(filename)[1].lower()

            # 确定保存格式
            save_ext = ext
            if output_format.lower() == 'jpg' or output_format.lower() == 'jpeg':
                save_ext = '.jpg'
            elif output_format.lower() == 'png':
                save_ext = '.png'
            elif output_format.lower() == 'bmp':
                save_ext = '.bmp'

            try:
                with Image.open(frame_path) as img:
                    # 确保图片模式适合裁剪
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    elif img.mode not in ('RGB', 'RGBA', 'L', 'LA'):
                        img = img.convert('RGB')

                    for mask in masks:
                        # 裁剪遮罩区域（带边界钳制）
                        left = max(0, mask.x)
                        top = max(0, mask.y)
                        right = min(img.width, mask.x + mask.width)
                        bottom = min(img.height, mask.y + mask.height)

                        # 跳过无效区域
                        if right <= left or bottom <= top:
                            self.log(f"  警告: 遮罩 '{mask.label}' 在帧 {filename} 中裁剪区域无效，已跳过")
                            continue

                        cropped = img.crop((left, top, right, bottom))

                        # 保存裁剪结果
                        out_path = os.path.join(
                            output_dir, mask.label,
                            f"{name_without_ext}{save_ext}"
                        )
                        cropped.save(out_path)

            except Exception as e:
                self.log(f"处理帧 {filename} 时出错: {str(e)}")
                continue

            # 更新进度
            if progress_callback:
                progress_callback(idx + 1, total)

        self.log(f"批量提取完成! 共处理 {total} 帧 × {len(masks)} 个遮罩")
        return {
            'success': True,
            'frame_count': total,
            'mask_count': len(masks),
            'output_dir': output_dir
        }

    # ---------- 异步提取 ----------
    def extract_async(
        self,
        masks: List[MaskDef],
        frames_dir: str,
        output_dir: str,
        output_format: str = 'png',
        callback: Optional[Callable[[dict], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> threading.Thread:
        """
        异步批量提取粒子

        参数:
            masks: 遮罩定义列表
            frames_dir: 帧序列图片目录
            output_dir: 输出根目录
            output_format: 输出图片格式
            callback: 完成回调，接收结果dict
            progress_callback: 进度回调 (current, total)

        返回:
            后台线程对象
        """
        def _extract_thread():
            self.is_running = True
            self.stop_flag = False
            try:
                result = self.extract_particles(
                    masks, frames_dir, output_dir,
                    output_format, progress_callback
                )
                if callback:
                    callback(result)
            except Exception as e:
                self.log(f"提取过程出错: {str(e)}")
                if callback:
                    callback({'success': False, 'error': str(e)})
            finally:
                self.is_running = False

        thread = threading.Thread(target=_extract_thread, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """停止正在进行的提取操作"""
        self.stop_flag = True
        self.log("正在停止...")

    # ---------- 遮罩序列化 ----------
    @staticmethod
    def save_masks_to_file(
        masks: List[MaskDef],
        filepath: str,
        reference_image_path: str = "",
        image_size: Optional[tuple] = None
    ):
        """
        将遮罩定义保存到JSON文件

        参数:
            masks: 遮罩列表
            filepath: 保存路径
            reference_image_path: 参考帧路径（用于加载时提示）
            image_size: 原始图像尺寸 (width, height)
        """
        data = {
            'version': 1,
            'reference_image_path': reference_image_path,
            'image_size': list(image_size) if image_size else [],
            'masks': [asdict(m) for m in masks]
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_masks_from_file(filepath: str) -> tuple:
        """
        从JSON文件加载遮罩定义

        参数:
            filepath: JSON文件路径

        返回:
            (masks: List[MaskDef], metadata: dict) 元组

        异常:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON格式错误
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        masks = []
        for m in data.get('masks', []):
            masks.append(MaskDef(
                id=m['id'],
                label=m.get('label', f"mask_{m['id']:02d}"),
                x=m['x'],
                y=m['y'],
                width=m['width'],
                height=m['height']
            ))

        metadata = {
            'version': data.get('version', 1),
            'reference_image_path': data.get('reference_image_path', ''),
            'image_size': tuple(data.get('image_size', [])) if data.get('image_size') else None
        }

        return masks, metadata
