import customtkinter as ctk
from PIL import Image, ImageTk
import os
import glob
from pathlib import Path
import threading
import json
from typing import Optional, List, Dict, Tuple
import requests
import re
from config_dialog import ConfigDialog
from translator_manager import TranslatorManager

class CaptionEditorFrame(ctk.CTkFrame):
    def __init__(self, master, lang_manager):
        super().__init__(master)
        
        self.lang_manager = lang_manager
        self.current_index = 0
        self.image_paths = []
        self.caption_pairs = []  # 存储[(图片路径, 英文txt路径)]
        self.current_image_path = ""
        self.current_caption_path = ""
        
        # 翻译器配置
        secretjson = self.load_json_script_dir("tentcent_secretkey.json")
        self.translator_config = {
            'current_service': 'tencent', 
            'secret_id': secretjson.get("SecretId"),
            'secret_key': secretjson.get("SecretKey"),
            'ai_service': None,
            'ai_api_key': ''
        }
        
        # 加载配置
        self.load_config()
        
        # 创建界面
        self.create_widgets()
        self.update_ui_texts()
    
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
            values=['baidu', 'youdao', 'google', 'deepl', 'openai', 'qwen', 'deepseek'],
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
        
        # 状态栏
        self.status_label = ctk.CTkLabel(main_container, text="准备就绪")
        self.status_label.pack(fill="x", pady=(10, 0))
        
        # 绑定事件
        self.english_text.bind("<<Modified>>", self.on_text_modified)
        self.chinese_text.bind("<<Modified>>", self.on_text_modified)
    
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
            txt_path = img_path + '.txt'

        for img_path in all_image_paths:
            print(f"{img_path}")
            print(f"{txt_path}")
            if os.path.exists(txt_path):
                self.caption_pairs.append((img_path, txt_path))
        
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
        
        img_path, txt_path = self.caption_pairs[self.current_index]
        self.current_image_path = img_path
        self.current_caption_path = txt_path
        
        # 显示图片
        self.display_image(img_path)
        
        # 加载标注文本
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                english_caption = f.read().strip()
        except:
            english_caption = ""
        
        # 更新英文文本框
        self.english_text.delete("1.0", "end")
        self.english_text.insert("1.0", english_caption)
        
        # 尝试从关联文件加载中文翻译，如果存在的话
        chinese_path = os.path.splitext(txt_path)[0] + '_cn.txt'
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
            # 如果没有中文翻译，尝试自动翻译
            if english_caption:
                self.translate_en_to_cn_async()
        
        # 更新索引显示
        self.index_label.configure(text=f"{self.current_index + 1}/{len(self.caption_pairs)}")
        
        # 更新按钮状态
        self.prev_btn.configure(state="normal" if self.current_index > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.current_index < len(self.caption_pairs) - 1 else "disabled")
    
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
        
        # 保存英文文本
        try:
            with open(self.current_caption_path, 'w', encoding='utf-8') as f:
                f.write(english_text)
        except Exception as e:
            self.show_status(f"保存英文失败: {str(e)}")
            return
        
        # 保存中文翻译到单独文件
        if chinese_text:
            chinese_path = os.path.splitext(self.current_caption_path)[0] + '_cn.txt'
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