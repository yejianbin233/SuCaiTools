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

class GifWindow(ctk.CTkToplevel):
    """GIF生成窗口"""
    def __init__(self, master, caption_editor):
        super().__init__(master)
        self.caption_editor = caption_editor
        self.title("生成GIF动画")
        self.geometry("600x400")
        # 确保弹窗置顶和模态
        self.transient(master)
        self.grab_set()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        
        self.gif_path = ""
        self.images_for_gif = []
        
        self.create_widgets()
    
    def create_widgets(self):
        """创建GIF窗口组件"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="生成图片集合GIF", font=("Arial", 16)).pack(pady=(0, 20))
        
        # 设置区域
        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.pack(fill="x", pady=(0, 20))
        
        # 帧率设置
        fps_frame = ctk.CTkFrame(settings_frame)
        fps_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(fps_frame, text="帧率 (FPS):").pack(side="left", padx=5)
        self.fps_var = ctk.IntVar(value=10)
        self.fps_entry = ctk.CTkEntry(fps_frame, textvariable=self.fps_var, width=100)
        self.fps_entry.pack(side="left", padx=5)
        
        # 每帧持续时间设置
        duration_frame = ctk.CTkFrame(settings_frame)
        duration_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(duration_frame, text="每帧持续时间 (毫秒):").pack(side="left", padx=5)
        self.duration_var = ctk.IntVar(value=100)
        self.duration_entry = ctk.CTkEntry(duration_frame, textvariable=self.duration_var, width=100)
        self.duration_entry.pack(side="left", padx=5)
        
        # 输出文件名
        name_frame = ctk.CTkFrame(settings_frame)
        name_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(name_frame, text="输出文件名:").pack(side="left", padx=5)
        self.filename_var = ctk.StringVar(value="combined_animation.gif")
        self.filename_entry = ctk.CTkEntry(name_frame, textvariable=self.filename_var, width=200)
        self.filename_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # 图片尺寸设置
        size_frame = ctk.CTkFrame(settings_frame)
        size_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(size_frame, text="输出尺寸 (宽x高):").pack(side="left", padx=5)
        self.width_var = ctk.IntVar(value=512)
        self.height_var = ctk.IntVar(value=512)
        
        self.width_entry = ctk.CTkEntry(size_frame, textvariable=self.width_var, width=80)
        self.width_entry.pack(side="left", padx=2)
        
        ctk.CTkLabel(size_frame, text="x").pack(side="left")
        
        self.height_entry = ctk.CTkEntry(size_frame, textvariable=self.height_var, width=80)
        self.height_entry.pack(side="left", padx=2)
        
        # 循环次数设置
        loop_frame = ctk.CTkFrame(settings_frame)
        loop_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(loop_frame, text="循环次数 (0=无限):").pack(side="left", padx=5)
        self.loop_var = ctk.IntVar(value=0)
        self.loop_entry = ctk.CTkEntry(loop_frame, textvariable=self.loop_var, width=100)
        self.loop_entry.pack(side="left", padx=5)
        
        # 按钮区域
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(0, 20))
        
        self.select_btn = ctk.CTkButton(
            button_frame,
            text="选择图片",
            width=100,
            command=self.select_images
        )
        self.select_btn.pack(side="left", padx=5)
        
        self.generate_btn = ctk.CTkButton(
            button_frame,
            text="生成GIF",
            width=100,
            command=self.generate_gif,
            fg_color="#388E3C",
            hover_color="#2E7D32"
        )
        self.generate_btn.pack(side="left", padx=5)
        
        self.preview_btn = ctk.CTkButton(
            button_frame,
            text="预览GIF",
            width=100,
            command=self.preview_gif,
            state="disabled"
        )
        self.preview_btn.pack(side="left", padx=5)
        
        # 状态区域
        self.status_label = ctk.CTkLabel(main_frame, text="未选择图片")
        self.status_label.pack()
        
        # 进度条
        self.progress_bar = ctk.CTkProgressBar(main_frame)
        self.progress_bar.pack(fill="x", pady=(10, 0))
        self.progress_bar.set(0)
    
    def select_images(self):
        """选择要生成GIF的图片"""
        from tkinter import filedialog
        
        filetypes = [
            ("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
            ("所有文件", "*.*")
        ]
        
        filenames = filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=filetypes
        )
        
        if filenames:
            self.images_for_gif = list(filenames)
            self.status_label.configure(text=f"已选择 {len(self.images_for_gif)} 张图片")
            self.preview_btn.configure(state="normal" if len(self.images_for_gif) > 0 else "disabled")
    
    def generate_gif(self):
        """生成GIF"""
        if not self.images_for_gif:
            messagebox.showwarning("警告", "请先选择图片")
            return
        
        # 获取输出路径
        folder_path = self.caption_editor.folder_entry.get()
        if not folder_path:
            folder_path = os.getcwd()
        
        filename = self.filename_var.get()
        if not filename.endswith('.gif'):
            filename += '.gif'
        
        self.gif_path = os.path.join(folder_path, filename)
        
        # 检查文件是否已存在
        if os.path.exists(self.gif_path):
            if not messagebox.askyesno("确认覆盖", f"文件 {filename} 已存在，是否覆盖？"):
                return
        
        # 在后台线程中生成GIF
        self.progress_bar.set(0)
        self.status_label.configure(text="正在生成GIF...")
        self.generate_btn.configure(state="disabled")
        
        thread = threading.Thread(target=self.generate_gif_thread, daemon=True)
        thread.start()
    
    def generate_gif_thread(self):
        """在后台线程中生成GIF"""
        try:
            images = []
            total = len(self.images_for_gif)
            
            for i, img_path in enumerate(self.images_for_gif):
                try:
                    # 打开并调整图片大小
                    img = Image.open(img_path)
                    
                    # 转换为RGB（确保所有图片都是RGB模式）
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # 调整大小
                    target_size = (self.width_var.get(), self.height_var.get())
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                    
                    images.append(img)
                    
                    # 更新进度
                    progress = (i + 1) / total
                    self.after(0, lambda p=progress: self.progress_bar.set(p))
                    self.after(0, lambda idx=i+1: self.status_label.configure(text=f"处理中: {idx}/{total}"))
                    
                except Exception as e:
                    self.after(0, lambda msg=str(e): self.status_label.configure(text=f"处理 {os.path.basename(img_path)} 失败: {msg}"))
            
            if not images:
                self.after(0, lambda: self.status_label.configure(text="没有可用的图片"))
                return
            
            # 生成GIF
            try:
                # 保存GIF
                images[0].save(
                    self.gif_path,
                    save_all=True,
                    append_images=images[1:],
                    duration=self.duration_var.get(),  # 每帧持续时间（毫秒）
                    loop=self.loop_var.get(),  # 循环次数
                    optimize=True
                )
                
                self.after(0, self.on_gif_generated)
                
            except Exception as e:
                self.after(0, lambda msg=str(e): self.status_label.configure(text=f"保存GIF失败: {msg}"))
                self.after(0, lambda: self.generate_btn.configure(state="normal"))
                
        except Exception as e:
            self.after(0, lambda msg=str(e): self.status_label.configure(text=f"生成GIF失败: {msg}"))
            self.after(0, lambda: self.generate_btn.configure(state="normal"))
    
    def on_gif_generated(self):
        """GIF生成完成"""
        self.progress_bar.set(1.0)
        self.status_label.configure(text=f"GIF已保存: {os.path.basename(self.gif_path)}")
        self.generate_btn.configure(state="normal")
        self.preview_btn.configure(state="normal")
        
        messagebox.showinfo("成功", f"GIF已成功生成！\n保存位置: {self.gif_path}")
    
    def preview_gif(self):
        """预览GIF"""
        if not self.gif_path or not os.path.exists(self.gif_path):
            messagebox.showwarning("警告", "请先生成GIF")
            return
        
        preview_window = ctk.CTkToplevel(self)
        preview_window.title("GIF预览")
        preview_window.geometry("500x500")
        
        # 加载GIF
        try:
            gif = Image.open(self.gif_path)
            
            # 创建标签显示GIF
            gif_label = ctk.CTkLabel(preview_window, text="")
            gif_label.pack(fill="both", expand=True, padx=20, pady=20)
            
            # 显示GIF帧
            self.preview_gif_frames(preview_window, gif_label, gif)
            
        except Exception as e:
            error_label = ctk.CTkLabel(preview_window, text=f"无法加载GIF: {str(e)}", text_color="red")
            error_label.pack(padx=20, pady=20)
    
    def preview_gif_frames(self, window, label, gif):
        """预览GIF的帧"""
        try:
            frames = []
            for frame in range(gif.n_frames):
                gif.seek(frame)
                frames.append(gif.copy())
            
            # 创建GIF动画
            self.animate_gif(window, label, frames, 0)
            
        except Exception as e:
            label.configure(text=f"预览失败: {str(e)}")
    
    def animate_gif(self, window, label, frames, index):
        """动画GIF"""
        if index >= len(frames):
            index = 0
        
        # 获取当前帧
        frame = frames[index]
        
        # 转换为PhotoImage
        photo = ImageTk.PhotoImage(frame)
        label.configure(image=photo)
        label.image = photo  # 保持引用
        
        # 计算下一帧的延迟
        delay = frame.info.get('duration', 100)
        
        # 调度下一帧
        window.after(delay, lambda: self.animate_gif(window, label, frames, index + 1))