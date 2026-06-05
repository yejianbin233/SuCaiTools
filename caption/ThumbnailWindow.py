from caption.GifWindow import GifWindow
from caption.RestoreWindow import RestoreWindow
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import glob
from pathlib import Path
import threading
import json
import shutil
from typing import Optional, List, Dict, Tuple
import requests
import re
import time
from tkinter import messagebox
from tkinter import ttk
import random
import string
from datetime import datetime

class ThumbnailWindow(ctk.CTkToplevel):
    """缩略图窗口"""
    def __init__(self, master, caption_editor):
        super().__init__(master)
        self.caption_editor = caption_editor
        self.title("图片缩略图浏览器")
        self.geometry("1000x600")
        # 确保弹窗置顶
        self.transient(master)
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        
        # 存储缩略图和删除状态
        self.thumbnail_buttons = []
        self.delete_vars = {}  # 存储每个缩略图的删除复选框状态
        self.deleted_temp_folder = ""  # 存储临时文件夹路径
        
        # 创建界面
        self.create_widgets()
        
        # 绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        """创建缩略图窗口组件"""
        # 主容器
        main_container = ctk.CTkFrame(self)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 控制面板
        control_frame = ctk.CTkFrame(main_container)
        control_frame.pack(fill="x", pady=(0, 10))
        
        # 刷新按钮
        self.refresh_btn = ctk.CTkButton(
            control_frame,
            text="刷新",
            width=80,
            command=self.refresh_thumbnails
        )
        self.refresh_btn.pack(side="left", padx=5, pady=5)
        
        # 全选/全不选
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_checkbox = ctk.CTkCheckBox(
            control_frame,
            text="全选",
            variable=self.select_all_var,
            command=self.toggle_select_all
        )
        self.select_all_checkbox.pack(side="left", padx=5, pady=5)
        
        # 删除选中按钮
        self.delete_btn = ctk.CTkButton(
            control_frame,
            text="删除选中项",
            width=100,
            command=self.delete_selected,
            fg_color="#D32F2F",  # 红色
            hover_color="#B71C1C"
        )
        self.delete_btn.pack(side="left", padx=5, pady=5)
        
        # 还原删除按钮
        self.restore_btn = ctk.CTkButton(
            control_frame,
            text="从临时文件夹还原",
            width=120,
            command=self.restore_from_temp,
            fg_color="#1976D2",  # 蓝色
            hover_color="#1565C0"
        )
        self.restore_btn.pack(side="left", padx=5, pady=5)
        
        # 打开GIF窗口按钮
        self.open_gif_btn = ctk.CTkButton(
            control_frame,
            text="生成GIF",
            width=100,
            command=self.open_gif_window,
            fg_color="#388E3C",  # 绿色
            hover_color="#2E7D32"
        )
        self.open_gif_btn.pack(side="left", padx=5, pady=5)
        
        # 状态标签
        self.status_label = ctk.CTkLabel(control_frame, text="就绪")
        self.status_label.pack(side="right", padx=10, pady=5)
        
        # 缩略图容器
        self.thumbnail_container = ctk.CTkScrollableFrame(main_container)
        self.thumbnail_container.pack(fill="both", expand=True)
        
        # 初始加载缩略图
        self.after(100, self.refresh_thumbnails)
    
    def refresh_thumbnails(self):
        """刷新缩略图"""
        # 清空现有缩略图
        for widget in self.thumbnail_buttons:
            widget.destroy()
        self.thumbnail_buttons.clear()
        self.delete_vars.clear()
        
        # 获取当前文件夹路径
        folder_path = self.caption_editor.folder_entry.get()
        if not folder_path or not os.path.exists(folder_path):
            self.status_label.configure(text="请先选择文件夹")
            return
        
        # 收集所有图片
        image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif', '*.tiff', '*.webp']
        all_image_paths = []
        for ext in image_extensions:
            pattern = os.path.join(folder_path, ext)
            all_image_paths.extend(glob.glob(pattern, recursive=False))
        
        # 去重并排序
        all_image_paths = sorted(set(all_image_paths))
        
        if not all_image_paths:
            self.status_label.configure(text="未找到图片")
            return
        
        # 创建缩略图网格
        num_columns = 5
        row = 0
        col = 0
        
        for img_path in all_image_paths:
            # 创建缩略图容器
            thumbnail_frame = ctk.CTkFrame(self.thumbnail_container)
            thumbnail_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            self.thumbnail_buttons.append(thumbnail_frame)
            
            # 加载并创建缩略图
            try:
                # 打开图片并创建缩略图
                img = Image.open(img_path)
                thumbnail = self.create_thumbnail(img, 150, 150)
                photo = ImageTk.PhotoImage(thumbnail)
                
                # 创建图片标签
                image_label = ctk.CTkLabel(
                    thumbnail_frame,
                    image=photo,
                    text=""
                )
                image_label.image = photo  # 保持引用
                image_label.pack(pady=(5, 0))
                
                # 显示文件名
                filename = os.path.basename(img_path)
                if len(filename) > 20:
                    filename = filename[:17] + "..."
                
                filename_label = ctk.CTkLabel(
                    thumbnail_frame,
                    text=filename,
                    font=("Arial", 10)
                )
                filename_label.pack()
                
                # 创建删除复选框
                delete_var = ctk.BooleanVar(value=False)
                self.delete_vars[img_path] = delete_var
                
                delete_checkbox = ctk.CTkCheckBox(
                    thumbnail_frame,
                    text="删除",
                    variable=delete_var
                )
                delete_checkbox.pack(pady=(0, 5))
                
                # 双击打开图片
                thumbnail_frame.bind("<Double-Button-1>", lambda e, path=img_path: self.open_image_in_editor(path))
                
            except Exception as e:
                # 如果图片加载失败，显示错误
                error_label = ctk.CTkLabel(
                    thumbnail_frame,
                    text=f"加载失败\n{os.path.basename(img_path)[:10]}...",
                    text_color="red"
                )
                error_label.pack(padx=10, pady=10)
                self.delete_vars[img_path] = ctk.BooleanVar(value=False)
            
            # 更新网格位置
            col += 1
            if col >= num_columns:
                col = 0
                row += 1
        
        # 更新状态
        self.status_label.configure(text=f"已加载 {len(all_image_paths)} 张图片")
    
    def create_thumbnail(self, image, width, height):
        """创建缩略图"""
        # 计算缩略图大小
        img_width, img_height = image.size
        scale = min(width / img_width, height / img_height)
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        # 调整大小
        thumbnail = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 创建画布并居中图片
        canvas = Image.new('RGB', (width, height), (50, 50, 50))
        x = (width - new_width) // 2
        y = (height - new_height) // 2
        canvas.paste(thumbnail, (x, y))
        
        return canvas
    
    def toggle_select_all(self):
        """全选/全不选"""
        select = self.select_all_var.get()
        for var in self.delete_vars.values():
            var.set(select)
    
    def delete_selected(self):
        """删除选中的图片和对应的txt文件"""
        # 获取要删除的文件
        files_to_delete = []
        for img_path, var in self.delete_vars.items():
            if var.get():
                files_to_delete.append(img_path)
        
        if not files_to_delete:
            messagebox.showwarning("警告", "请先选择要删除的图片")
            return
        
        if not messagebox.askyesno("确认删除", f"确定要删除 {len(files_to_delete)} 个文件吗？\n文件将被移动到临时文件夹。"):
            return
        
        # 确保临时文件夹存在
        folder_path = self.caption_editor.folder_entry.get()
        temp_folder = os.path.join(folder_path, "deleted_temp")
        os.makedirs(temp_folder, exist_ok=True)
        
        # 创建带时间戳的子文件夹
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sub_temp_folder = os.path.join(temp_folder, f"deleted_{timestamp}")
        os.makedirs(sub_temp_folder, exist_ok=True)
        
        self.deleted_temp_folder = sub_temp_folder
        
        # 移动文件
        moved_files = []
        for img_path in files_to_delete:
            try:
                # 获取文件名
                filename = os.path.basename(img_path)
                
                # 移动图片文件
                dest_img_path = os.path.join(sub_temp_folder, filename)
                shutil.move(img_path, dest_img_path)
                
                # 查找并移动对应的txt文件
                base_name = os.path.splitext(filename)[0]
                txt_patterns = [
                    os.path.join(folder_path, f"{base_name}.txt"),
                    os.path.join(folder_path, f"{base_name}_en.txt"),
                    os.path.join(folder_path, f"{base_name}_cn.txt")
                ]
                
                for txt_pattern in txt_patterns:
                    if os.path.exists(txt_pattern):
                        txt_filename = os.path.basename(txt_pattern)
                        dest_txt_path = os.path.join(sub_temp_folder, txt_filename)
                        shutil.move(txt_pattern, dest_txt_path)
                        moved_files.append(txt_filename)
                
                moved_files.append(filename)
                
            except Exception as e:
                self.status_label.configure(text=f"移动 {os.path.basename(img_path)} 失败: {str(e)}")
        
        # 刷新缩略图和主编辑器
        self.refresh_thumbnails()
        self.caption_editor.load_images()  # 刷新主编辑器的图片列表
        
        # 显示结果
        message = f"已移动 {len(moved_files)} 个文件到临时文件夹:\n{sub_temp_folder}"
        messagebox.showinfo("删除完成", message)
        self.status_label.configure(text=f"已删除 {len(files_to_delete)} 个文件")
    
    def restore_from_temp(self):
        """从临时文件夹还原文件"""
        folder_path = self.caption_editor.folder_entry.get()
        temp_folder = os.path.join(folder_path, "deleted_temp")
        
        if not os.path.exists(temp_folder):
            messagebox.showinfo("信息", "临时文件夹不存在")
            return
        
        # 让用户选择要还原的子文件夹
        restore_window = RestoreWindow(self, folder_path, self.refresh_thumbnails)
        restore_window.grab_set()
    
    def open_image_in_editor(self, image_path):
        """在编辑器中打开图片"""
        # 查找图片在列表中的索引
        for i, (img_path, cn_txt_path, en_txt_path) in enumerate(self.caption_editor.caption_pairs):
            if img_path == image_path:
                self.caption_editor.current_index = i
                self.caption_editor.load_current_image()
                self.master.focus_force()  # 聚焦到主窗口
                break
    
    def open_gif_window(self):
        """打开GIF生成窗口"""
        gif_window = GifWindow(self, self.caption_editor)
        gif_window.grab_set()
    
    def on_closing(self):
        """窗口关闭时的处理"""
        self.destroy()