"""
图片尺寸调整工具（纯逻辑模块）
==============================

## 文件功能
提供单图/批量图片的尺寸缩放处理，支持 4 种模式：
- scale: 按比例缩小原图
- fixed: 固定宽高
- fixed_width: 固定宽度，自动计算高度
- fixed_height: 固定高度，自动计算宽度

## 架构定位
零 GUI 依赖的纯逻辑模块，被 resize_panel.py（PySide6）调用。
也支持直接运行测试脚本。
"""

import os
# PIL.Image：Pillow 库的图片处理核心类（替换原重复导入）
from PIL import Image

# ---- 单图处理 ----


def process_image(image_path: str, mode: str, **kwargs) -> None:
    """
    调整单张图片的尺寸并覆盖保存。

    参数：
        image_path (str): 图片文件路径
        mode (str): 处理模式，可选值为 scale/fixed/fixed_width/fixed_height
        **kwargs: 模式相关参数（scale/width/height）

    说明：
        - scale=0.7 → 缩小到原图的 70%
        - fixed=800x600 → 强制设置为指定分辨率
        - fixed_width=1280 → 宽度固定为 1280，高度按比例
        - fixed_height=900 → 高度固定为 900，宽度按比例
    """
    try:
        with Image.open(image_path) as img:
            if mode == "scale":
                scale = float(kwargs.get('scale', 0.5))
                # scale=0.7 → 新尺寸 = 原尺寸 × 0.7
                new_size = (int(img.width * scale), int(img.height * scale))
            elif mode == "fixed":
                width, height = int(kwargs.get('width')), int(kwargs.get('height'))
                # 强制设置为指定分辨率（宽高都不变）
                new_size = (width, height)
            elif mode == "fixed_width":
                width = int(kwargs.get('width'))
                # 固定宽度，高度按比例：新高度 = 原高度 × (目标宽度 / 原宽度)
                ratio = width / img.width
                height = int(img.height * ratio)
                new_size = (width, height)
            elif mode == "fixed_height":
                # 固定高度，宽度按比例：新宽度 = 原宽度 × (目标高度 / 原高度)
                height = int(kwargs.get('height'))
                ratio = height / img.height
                width = int(img.width * ratio)
                new_size = (width, height)
            else:
                print(f"未知的处理模式: {mode} for {image_path}")
                return # 如果模式未知，则不处理

            # 保持图片模式（针对有透明通道的PNG等格式）
            resized_img = img.resize(new_size, Image.LANCZOS)

            # 获取原始文件的扩展名
            file_extension = os.path.splitext(image_path)[1].lower()

            # 根据扩展名决定保存格式
            save_format = None
            if file_extension in ('.jpg', '.jpeg'):
                save_format = 'jpeg'
                # 如果是RGBA模式，转换为RGB，因为JPEG不支持透明度
                if resized_img.mode == 'RGBA':
                    resized_img = resized_img.convert('RGB')
            elif file_extension == '.png':
                save_format = 'png'
            elif file_extension == '.bmp':
                save_format = 'bmp'
            elif file_extension == '.gif':
                save_format = 'gif'

            if save_format:
                # 覆盖保存原图
                if save_format == 'jpeg':
                    resized_img.save(image_path, format=save_format, quality=95)
                else:
                    resized_img.save(image_path, format=save_format)
            else:
                print(f"不支持的保存格式: {file_extension} for {image_path}")
            print(f"已处理 ({mode}): {image_path}")

    except Exception as e:
        print(f"处理失败 {image_path}: {str(e)}")

# 修改 process_directory 以传递模式和参数
def process_directory(root_dir, mode='scale', **kwargs):
    # 支持的图片格式
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')

    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(valid_extensions):
                file_path = os.path.join(root, file)
                # 将模式和参数传递给 process_image
                process_image(file_path, mode, **kwargs)

if __name__ == "__main__":
    # 测试代码（可选，通常由GUI调用）
    target_dir = r'c:\Users\lmh\Desktop\me\素材'  # 修改为需要处理的目录
    # 测试按比例缩放
    # process_directory(target_dir, mode='scale', scale=0.7)
    # 测试固定分辨率
    # process_directory(target_dir, mode='fixed', width=800, height=600)
    print("脚本可以直接运行进行测试，但主要由 gui.py 调用")