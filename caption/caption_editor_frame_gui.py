from caption.GifWindow import GifWindow
from caption.ThumbnailWindow import ThumbnailWindow
from caption.config_dialog import ConfigDialog
from caption.translator_manager import TranslatorManager
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


class CaptionEditorFrame(ctk.CTkFrame):
    def __init__(self, master, lang_manager):
        super().__init__(master)
        
        self.lang_manager = lang_manager
        self.current_index = 0
        self.image_paths = []
        self.caption_pairs = []  # 存储[(图片路径, 中文txt路径, 英文txt路径)]
        self.current_image_path = ""
        self.current_caption_cn_txt_path = ""
        self.current_caption_en_txt_path = ""
        
        # 翻译器配置
        secretjson = self.load_json_script_dir("tentcent_secretkey.json")
        self.translator_config = {
            'current_service': 'tencent', 
            'secret_id': secretjson.get("SecretId"),
            'secret_key': secretjson.get("SecretKey"),
            'ai_service': None,
            'ai_api_key': ''
        }
        
        # 缩略图窗口引用
        self.thumbnail_window = None
        self.gif_window = None
        
        # 加载配置
        self.load_config()
        
        # 批量翻译控制变量
        self.batch_translate_running = False
        self.batch_translate_stop_flag = False
        
        # 创建界面
        self.create_widgets()
        self.update_ui_texts()
    
    def create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_container = ctk.CTkFrame(self)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 上部：控制面板
        control_frame = ctk.CTkFrame(main_container)
        control_frame.pack(fill="x", pady=(0, 20))
        
        # 文件夹选择
        folder_frame = ctk.CTkFrame(control_frame)
        folder_frame.pack(side="left", padx=10, pady=5)
        
        ctk.CTkLabel(folder_frame, text="图片文件夹:").pack(side="left", padx=5)
        self.folder_entry = ctk.CTkEntry(folder_frame, width=300)
        self.folder_entry.pack(side="left", padx=5)
        
        self.browse_btn = ctk.CTkButton(
            folder_frame, 
            text="浏览",
            width=80,
            command=self.browse_folder
        )
        self.browse_btn.pack(side="left", padx=5)
        
        self.load_btn = ctk.CTkButton(
            folder_frame,
            text="加载图片",
            width=100,
            command=self.load_images
        )
        self.load_btn.pack(side="left", padx=5)
        
        # 缩略图按钮
        self.thumbnail_btn = ctk.CTkButton(
            folder_frame,
            text="缩略图",
            width=80,
            command=self.open_thumbnail_window,
            fg_color="#7B1FA2",  # 紫色
            hover_color="#6A1B9A"
        )
        self.thumbnail_btn.pack(side="left", padx=5)
        
        # 导航控制
        nav_frame = ctk.CTkFrame(control_frame)
        nav_frame.pack(side="right", padx=10, pady=5)
        
        self.prev_btn = ctk.CTkButton(
            nav_frame,
            text="上一张",
            width=80,
            command=self.prev_image
        )
        self.prev_btn.pack(side="left", padx=5)
        
        self.next_btn = ctk.CTkButton(
            nav_frame,
            text="下一张",
            width=80,
            command=self.next_image
        )
        self.next_btn.pack(side="left", padx=5)
        
        self.index_label = ctk.CTkLabel(
            nav_frame,
            text="0/0"
        )
        self.index_label.pack(side="left", padx=10)
        
        # 主内容区域
        content_frame = ctk.CTkFrame(main_container)
        content_frame.pack(fill="both", expand=True)
        
        # 左侧：图片显示
        image_frame = ctk.CTkFrame(content_frame)
        image_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(image_frame, text="图片预览", font=("Arial", 16)).pack(pady=5)
        
        self.image_canvas = ctk.CTkCanvas(image_frame, bg="#2b2b2b", highlightthickness=0)
        self.image_canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 右侧：文本编辑区域
        text_frame = ctk.CTkFrame(content_frame)
        text_frame.pack(side="right", fill="both", expand=True)
        
        # 英文编辑区
        english_frame = ctk.CTkFrame(text_frame)
        english_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        ctk.CTkLabel(english_frame, text="英文描述", font=("Arial", 16)).pack(anchor="w", padx=10, pady=5)
        
        self.english_text = ctk.CTkTextbox(english_frame, height=150)
        self.english_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 中文编辑区
        chinese_frame = ctk.CTkFrame(text_frame)
        chinese_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        ctk.CTkLabel(chinese_frame, text="中文翻译", font=("Arial", 16)).pack(anchor="w", padx=10, pady=5)
        
        self.chinese_text = ctk.CTkTextbox(chinese_frame, height=150)
        self.chinese_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 按钮区域
        button_frame = ctk.CTkFrame(text_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        
        # 翻译按钮
        translate_frame = ctk.CTkFrame(button_frame)
        translate_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(translate_frame, text="翻译服务:").pack(side="left", padx=5)
        
        self.translate_service_var = ctk.StringVar(value=self.translator_config['current_service'])
        self.translate_service_menu = ctk.CTkOptionMenu(
            translate_frame,
            values=['tencent', 'baidu', 'youdao', 'google', 'deepl', 'openai', 'qwen', 'deepseek'],
            variable=self.translate_service_var,
            width=100,
            command=self.change_translate_service
        )
        self.translate_service_menu.pack(side="left", padx=5)
        
        self.translate_cn_to_en_btn = ctk.CTkButton(
            translate_frame,
            text="中→英翻译",
            width=100,
            command=self.translate_cn_to_en
        )
        self.translate_cn_to_en_btn.pack(side="left", padx=5)
        
        self.translate_en_to_cn_btn = ctk.CTkButton(
            translate_frame,
            text="英→中翻译",
            width=100,
            command=self.translate_en_to_cn
        )
        self.translate_en_to_cn_btn.pack(side="left", padx=5)
        
        # 操作按钮
        action_frame = ctk.CTkFrame(button_frame)
        action_frame.pack(fill="x", pady=5)
        
        self.save_btn = ctk.CTkButton(
            action_frame,
            text="保存修改",
            width=100,
            command=self.save_changes
        )
        self.save_btn.pack(side="left", padx=5)
        
        self.refresh_btn = ctk.CTkButton(
            action_frame,
            text="刷新",
            width=80,
            command=self.refresh_current
        )
        self.refresh_btn.pack(side="left", padx=5)
        
        self.config_btn = ctk.CTkButton(
            action_frame,
            text="配置",
            width=80,
            command=self.open_config
        )
        self.config_btn.pack(side="left", padx=5)
        
        # 批量翻译按钮
        self.batch_translate_btn = ctk.CTkButton(
            action_frame,
            text="批量翻译",
            width=100,
            command=self.start_batch_translate,
            fg_color="#2E7D32",  # 绿色
            hover_color="#1B5E20"
        )
        self.batch_translate_btn.pack(side="left", padx=5)
        
        # 停止批量翻译按钮（初始隐藏）
        self.stop_batch_btn = ctk.CTkButton(
            action_frame,
            text="停止",
            width=80,
            command=self.stop_batch_translate,
            fg_color="#D32F2F",  # 红色
            hover_color="#B71C1C"
        )
        self.stop_batch_btn.pack(side="left", padx=5)
        self.stop_batch_btn.pack_forget()  # 初始隐藏
        
        # 批量翻译进度条
        self.progress_frame = ctk.CTkFrame(button_frame)
        self.progress_frame.pack(fill="x", pady=5)
        self.progress_frame.pack_forget()  # 初始隐藏
        
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=("Arial", 10)
        )
        self.progress_label.pack(side="left", padx=5)
        
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            width=200,
            height=10
        )
        self.progress_bar.pack(side="left", padx=5, fill="x", expand=True)
        self.progress_bar.set(0)
        
        # 状态栏
        self.status_label = ctk.CTkLabel(main_container, text="准备就绪")
        self.status_label.pack(fill="x", pady=(10, 0))
        
        # 绑定事件
        self.english_text.bind("<<Modified>>", self.on_text_modified)
        self.chinese_text.bind("<<Modified>>", self.on_text_modified)
    
    def open_thumbnail_window(self):
        """打开缩略图窗口"""
        if not hasattr(self, 'thumbnail_window') or not self.thumbnail_window or not self.thumbnail_window.winfo_exists():
            self.thumbnail_window = ThumbnailWindow(self.master, self)
        else:
            self.thumbnail_window.lift()
            self.thumbnail_window.focus_force()
    
    def open_gif_window(self):
        """打开GIF窗口"""
        if not hasattr(self, 'gif_window') or not self.gif_window or not self.gif_window.winfo_exists():
            self.gif_window = GifWindow(self.master, self)
        else:
            self.gif_window.lift()
            self.gif_window.focus_force()
    
    def update_ui_texts(self):
        """更新界面文本"""
        # 这里可以根据语言管理器更新文本
        # 由于没有具体的语言管理器方法，这里先使用默认文本
        self.load_btn.configure(text="加载图片")
        self.prev_btn.configure(text="上一张")
        self.next_btn.configure(text="下一张")
        self.translate_cn_to_en_btn.configure(text="中→英翻译")
        self.translate_en_to_cn_btn.configure(text="英→中翻译")
        self.save_btn.configure(text="保存修改")
        self.refresh_btn.configure(text="刷新")
        self.config_btn.configure(text="配置")
        self.batch_translate_btn.configure(text="批量翻译")
        self.stop_batch_btn.configure(text="停止")
        self.status_label.configure(text="准备就绪")
    
    def browse_folder(self):
        """浏览文件夹"""
        from tkinter import filedialog
        folder_path = filedialog.askdirectory(title="选择包含图片的文件夹")
        if folder_path:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder_path)
    
    def load_images(self):
        """加载文件夹中的所有图片和对应的标注文件"""
        folder_path = self.folder_entry.get()
        if not folder_path or not os.path.exists(folder_path):
            self.show_status("请选择有效的文件夹路径")
            return
        
        # 支持的图片格式
        image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif', '*.tiff', '*.webp']
        
        # 收集所有图片
        all_image_paths = []
        for ext in image_extensions:
            pattern = os.path.join(folder_path, ext)
            all_image_paths.extend(glob.glob(pattern, recursive=True))
            pattern = os.path.join(folder_path, '**', ext)
            all_image_paths.extend(glob.glob(pattern, recursive=True))
        
        # 去重并排序
        all_image_paths = sorted(set(all_image_paths))
        
        # 查找对应的标注文件
        self.caption_pairs = []
        for img_path in all_image_paths:
            cn_txt_path = os.path.splitext(img_path)[0] + '.txt'
            en_txt_path = os.path.splitext(img_path)[0] + '_en.txt'
            self.caption_pairs.append((img_path, cn_txt_path, en_txt_path))

        if not self.caption_pairs:
            self.show_status(f"在文件夹中未找到任何图片对应的txt标注文件")
            return
        
        self.current_index = 0
        self.show_status(f"已加载 {len(self.caption_pairs)} 个图片-标注对")
        self.load_current_image()
    
    def load_current_image(self):
        """加载当前索引的图片和标注"""
        if not self.caption_pairs or self.current_index >= len(self.caption_pairs):
            return
        
        img_path, cn_txt_path, en_txt_path= self.caption_pairs[self.current_index]
        self.current_image_path = img_path
        self.current_caption_cn_txt_path = cn_txt_path
        self.current_caption_en_txt_path = en_txt_path
        # 显示图片
        self.display_image(img_path)
        
        # 加载标注文本
        try:
            with open(en_txt_path, 'r', encoding='utf-8') as f:
                english_caption = f.read().strip()
        except:
            english_caption = ""
        
        # 更新英文文本框
        self.english_text.delete("1.0", "end")
        self.english_text.insert("1.0", english_caption)
        
        # 尝试从关联文件加载中文翻译，如果存在的话
        #chinese_path = os.path.splitext(cn_txt_path)[0] + '_cn.txt'
        chinese_path = cn_txt_path
        chinese_caption = ""
        if os.path.exists(chinese_path):
            try:
                with open(chinese_path, 'r', encoding='utf-8') as f:
                    chinese_caption = f.read().strip()
            except:
                chinese_caption = ""
        
        # 更新中文文本框
        self.chinese_text.delete("1.0", "end")
        if chinese_caption:
            self.chinese_text.insert("1.0", chinese_caption)
        else:
            # 不自动翻译，只显示空文本框
            # 用户需要手动点击翻译按钮
            self.chinese_text.insert("1.0", "")
        
        # 更新索引显示
        self.index_label.configure(text=f"{self.current_index + 1}/{len(self.caption_pairs)}")
        
        # 更新按钮状态
        self.prev_btn.configure(state="normal" if self.current_index > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.current_index < len(self.caption_pairs) - 1 else "disabled")
        
        # 显示当前文件的中文翻译状态
        if os.path.exists(chinese_path):
            self.show_status(f"已加载: {os.path.basename(img_path)} (已有中文翻译)")
        else:
            self.show_status(f"已加载: {os.path.basename(img_path)} (无中文翻译)")
    
    def display_image(self, img_path):
        """在画布上显示图片"""
        try:
            # 清空画布
            self.image_canvas.delete("all")
            
            # 打开并调整图片大小
            img = Image.open(img_path)
            img_width, img_height = img.size
            
            # 计算适合画布的尺寸
            canvas_width = self.image_canvas.winfo_width()
            canvas_height = self.image_canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 400
                canvas_height = 400
            
            scale = min(canvas_width / img_width, canvas_height / img_height, 1.0)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为PhotoImage
            self.current_photo = ImageTk.PhotoImage(img)
            
            # 在画布中心显示图片
            x = (canvas_width - new_width) // 2
            y = (canvas_height - new_height) // 2
            
            self.image_canvas.create_image(x, y, anchor="nw", image=self.current_photo)
            
            # 显示图片信息
            info_text = f"{os.path.basename(img_path)} ({img_width}x{img_height})"
            self.image_canvas.create_text(
                canvas_width // 2, 
                canvas_height - 20, 
                text=info_text, 
                fill="white", 
                font=("Arial", 10)
            )
            
        except Exception as e:
            self.image_canvas.delete("all")
            self.image_canvas.create_text(
                200, 200, 
                text=f"无法加载图片\n{str(e)}", 
                fill="red", 
                font=("Arial", 12)
            )
    
    def prev_image(self):
        """显示上一张图片"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()
    
    def next_image(self):
        """显示下一张图片"""
        if self.current_index < len(self.caption_pairs) - 1:
            self.current_index += 1
            self.load_current_image()
    
    def translate_en_to_cn(self):
        """英译中"""
        english_text = self.english_text.get("1.0", "end-1c").strip()
        if not english_text:
            self.show_status("没有英文文本可翻译")
            return
        
        self.translate_en_to_cn_async()
    
    def translate_en_to_cn_async(self):
        """异步英译中"""
        english_text = self.english_text.get("1.0", "end-1c").strip()
        if not english_text:
            return
        
        def translate_thread():
            try:
                self.show_status("正在翻译...")
                translator = TranslatorManager.get_translator(self.translator_config['current_service'], self.translator_config)
                chinese_text = translator.translate_to_chinese(english_text)
                
                # 更新UI需要在主线程
                self.after(0, lambda: self.update_chinese_text(chinese_text))
                self.after(0, lambda: self.show_status("翻译完成"))
                
            except Exception as e:
                # 将异常信息作为默认参数传递给lambda
                error_msg = str(e)  # 限制长度避免太长
                self.after(0, lambda msg=error_msg: self.show_status(f"翻译失败: {msg}"))
        
        thread = threading.Thread(target=translate_thread, daemon=True)
        thread.start()
    
    def translate_cn_to_en(self):
        """中译英"""
        chinese_text = self.chinese_text.get("1.0", "end-1c").strip()
        if not chinese_text:
            self.show_status("没有中文文本可翻译")
            return
        
        def translate_thread():
            try:
                self.show_status("正在翻译...")
                translator = TranslatorManager.get_translator(self.translator_config['current_service'], self.translator_config)
                english_text = translator.translate_to_english(chinese_text)
                
                # 更新UI需要在主线程
                self.after(0, lambda: self.update_english_text(english_text))
                self.after(0, lambda: self.show_status("翻译完成"))
                
            except Exception as e:
                self.after(0, lambda: self.show_status(f"翻译失败: {str(e)}"))
        
        thread = threading.Thread(target=translate_thread, daemon=True)
        thread.start()
    
    def update_english_text(self, text):
        """更新英文文本框"""
        self.english_text.delete("1.0", "end")
        self.english_text.insert("1.0", text)
    
    def update_chinese_text(self, text):
        """更新中文文本框"""
        self.chinese_text.delete("1.0", "end")
        self.chinese_text.insert("1.0", text)
    
    def save_changes(self):
        """保存修改"""
        if not self.caption_pairs or self.current_index >= len(self.caption_pairs):
            self.show_status("没有可保存的内容")
            return
        
        english_text = self.english_text.get("1.0", "end-1c").strip()
        chinese_text = self.chinese_text.get("1.0", "end-1c").strip()
        
        if not english_text:
            self.show_status("英文文本不能为空")
            return
        
        if not english_text:
            self.show_status("中文文本不能为空")
            return
        
        # 保存英文文本
        try:
            with open(self.current_caption_en_txt_path, 'w', encoding='utf-8') as f:
                f.write(english_text)
        except Exception as e:
            self.show_status(f"保存英文失败: {str(e)}")
            return
        
        # 保存中文翻译到单独文件
        if chinese_text:
            chinese_path = self.current_caption_cn_txt_path
            try:
                with open(chinese_path, 'w', encoding='utf-8') as f:
                    f.write(chinese_text)
            except Exception as e:
                self.show_status(f"保存中文翻译失败: {str(e)}")
        
        self.show_status("保存成功")
    
    def refresh_current(self):
        """刷新当前项"""
        if self.current_image_path:
            self.load_current_image()
    
    def on_text_modified(self, event):
        """文本修改事件"""
        # 重置Modified标志
        if isinstance(event.widget, ctk.CTkTextbox):
            event.widget.edit_modified(False)
    
    def change_translate_service(self, service):
        """更改翻译服务"""
        self.translator_config['current_service'] = service
        self.save_config()
        self.show_status(f"已切换翻译服务: {service}")
    
    def open_config(self):
        """打开配置对话框"""
        ConfigDialog(self, self.translator_config, self.save_config)
    
    def save_config(self):
        """保存配置"""
        config_path = os.path.join(os.path.expanduser("~"), ".caption_editor_config.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.translator_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def load_config(self):
        """加载配置"""
        config_path = os.path.join(os.path.expanduser("~"), ".caption_editor_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    self.translator_config.update(loaded_config)
            except Exception as e:
                print(f"加载配置失败: {e}")
    
    def show_status(self, message):
        """显示状态信息"""
        self.status_label.configure(text=message)
        print(f"状态: {message}")
    
    def start_batch_translate(self):
        """开始批量翻译"""
        if not self.caption_pairs:
            self.show_status("错误：请先加载图片")
            return
        
        # 检查是否需要用户确认
        if not messagebox.askyesno("批量翻译", f"确定要批量翻译 {len(self.caption_pairs)} 个文件吗？"):
            return
        
        # 禁用批量翻译按钮，显示停止按钮
        self.batch_translate_btn.configure(state="disabled")
        self.stop_batch_btn.pack(side="left", padx=5)
        
        # 显示进度条
        self.progress_frame.pack(fill="x", pady=5)
        
        # 启动批量翻译线程
        self.batch_translate_running = True
        self.batch_translate_stop_flag = False
        
        thread = threading.Thread(target=self.batch_translate_process, daemon=True)
        thread.start()
    
    def batch_translate_process(self):
        """批量翻译处理函数"""
        try:
            total_files = len(self.caption_pairs)
            translated_count = 0
            skipped_count = 0
            failed_count = 0
            
            # 创建翻译器
            translator = TranslatorManager.get_translator(
                self.translator_config['current_service'], 
                self.translator_config
            )
            
            for i, (img_path, cn_txt_path, en_txt_path) in enumerate(self.caption_pairs):
                # 检查是否被停止
                if self.batch_translate_stop_flag:
                    self.after(0, lambda: self.show_status("批量翻译已停止"))
                    break
                
                # 检查是否已有中文翻译
                chinese_path = cn_txt_path
                if os.path.exists(chinese_path):
                    # 已有中文翻译，跳过
                    skipped_count += 1
                    self.after(0, lambda idx=i+1, total=total_files, img=img_path: 
                              self.update_batch_progress(idx, total, f"跳过: {os.path.basename(img)}"))
                    continue
                
                # 读取英文文本
                try:
                    with open(en_txt_path, 'r', encoding='utf-8') as f:
                        english_text = f.read().strip()
                except:
                    english_text = ""
                
                if not english_text:
                    # 英文文本为空，跳过
                    skipped_count += 1
                    self.after(0, lambda idx=i+1, total=total_files, img=img_path: 
                              self.update_batch_progress(idx, total, f"跳过(无英文): {os.path.basename(img)}"))
                    continue
                
                # 更新进度
                self.after(0, lambda idx=i+1, total=total_files, img=img_path: 
                          self.update_batch_progress(idx, total, f"翻译中: {os.path.basename(img)}"))
                
                # 执行翻译
                try:
                    chinese_text = translator.translate_to_chinese(english_text)
                    
                    # 检查翻译结果是否有效
                    if not chinese_text or "失败" in chinese_text or "错误" in chinese_text:
                        failed_count += 1
                        self.after(0, lambda idx=i+1, total=total_files, img=img_path: 
                                  self.update_batch_progress(idx, total, f"翻译失败: {os.path.basename(img)}"))
                        continue
                    
                    # 保存中文翻译
                    with open(chinese_path, 'w', encoding='utf-8') as f:
                        f.write(chinese_text)
                    
                    translated_count += 1
                    
                    # 更新进度
                    self.after(0, lambda idx=i+1, total=total_files, img=img_path: 
                              self.update_batch_progress(idx, total, f"完成: {os.path.basename(img)}"))
                    
                    # 如果是当前显示的文件，更新显示
                    if i == self.current_index:
                        self.after(0, lambda: self.update_chinese_text(chinese_text))
                    
                    # 为了避免API调用频率限制，添加延迟
                    time.sleep(1)  # 1秒延迟
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)[:50]
                    self.after(0, lambda idx=i+1, total=total_files, img=img_path, err=error_msg: 
                              self.update_batch_progress(idx, total, f"错误: {os.path.basename(img)} ({err})"))
                    continue
            
            # 批量翻译完成
            self.batch_translate_running = False
            
            # 更新UI
            self.after(0, lambda: self.on_batch_translate_complete(
                total_files, translated_count, skipped_count, failed_count
            ))
            
        except Exception as e:
            error_msg = str(e)
            self.after(0, lambda: self.on_batch_translate_error(error_msg))
    
    def update_batch_progress(self, current, total, message):
        """更新批量翻译进度"""
        # 更新进度条
        progress = current / total
        self.progress_bar.set(progress)
        
        # 更新进度标签
        self.progress_label.configure(text=f"{current}/{total} {message}")
        
        # 更新状态
        self.show_status(f"批量翻译: {message}")
    
    def on_batch_translate_complete(self, total, translated, skipped, failed):
        """批量翻译完成"""
        # 隐藏进度条和停止按钮
        self.progress_frame.pack_forget()
        self.stop_batch_btn.pack_forget()
        
        # 启用批量翻译按钮
        self.batch_translate_btn.configure(state="normal")
        
        # 显示结果
        result_message = f"批量翻译完成！\n总共: {total} 个文件\n翻译: {translated} 个\n跳过: {skipped} 个\n失败: {failed} 个"
        
        if failed > 0:
            messagebox.showwarning("批量翻译完成", result_message)
        else:
            messagebox.showinfo("批量翻译完成", result_message)
        
        self.show_status("批量翻译完成")
        
        # 刷新当前显示
        if self.caption_pairs:
            self.load_current_image()
    
    def on_batch_translate_error(self, error_msg):
        """批量翻译出错"""
        # 隐藏进度条和停止按钮
        self.progress_frame.pack_forget()
        self.stop_batch_btn.pack_forget()
        
        # 启用批量翻译按钮
        self.batch_translate_btn.configure(state="normal")
        
        # 显示错误
        messagebox.showerror("批量翻译出错", f"批量翻译过程中出错:\n{error_msg}")
        self.show_status(f"批量翻译出错: {error_msg[:50]}")
    
    def stop_batch_translate(self):
        """停止批量翻译"""
        if self.batch_translate_running:
            self.batch_translate_stop_flag = True
            self.show_status("正在停止批量翻译...")
            self.stop_batch_btn.configure(state="disabled", text="停止中...")
    
    def load_json_script_dir(self, filename: str) -> dict:
        """
        加载脚本所在目录下的JSON文件
        
        Args:
            filename: JSON文件名
        """
        # 获取脚本文件所在的目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data