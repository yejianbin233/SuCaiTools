import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
from tkinterdnd2 import DND_FILES
from PIL import Image
from drag_drop_handler import handle_file_drop
import tkinter as tk

class GifSplitterFrame(ctk.CTkFrame):
    """GIF拆分图片界面"""
    
    def __init__(self, master, lang_manager):
        super().__init__(master)
        self.lang_manager = lang_manager
        self.gif_path = ""
        self.output_dir = ""
        self.is_processing = False
        
        # 从语言文件中获取文本，如果不存在则使用默认值
        self.texts = {
            'tab_gif_splitter': self.lang_manager.get_text('tab_gif_splitter') or "GIF拆分图片",
            'select_gif_file': self.lang_manager.get_text('select_gif_file') or "选择GIF文件:",
            'browse': self.lang_manager.get_text('browse') or "浏览...",
            'output_format': self.lang_manager.get_text('output_format') or "输出格式:",
            'start_split': self.lang_manager.get_text('start_split') or "开始拆分",
            'processing': self.lang_manager.get_text('processing') or "处理中...",
            'log': self.lang_manager.get_text('log') or "日志:",
            'clear_log': self.lang_manager.get_text('clear_log') or "清空日志",
            'status_idle': self.lang_manager.get_text('status_idle') or "请选择GIF文件",
            'error_title': self.lang_manager.get_text('error_title') or "错误",
            'info_title': self.lang_manager.get_text('info_title') or "信息",
            'select_gif_file_dialog_title': self.lang_manager.get_text('select_gif_file_dialog_title') or "选择GIF文件",
            'gif_files': self.lang_manager.get_text('gif_files') or "GIF文件",
            'all_files': self.lang_manager.get_text('all_files') or "所有文件",
            'select_folder_dialog_title': self.lang_manager.get_text('select_folder_dialog_title') or "选择输出目录",
            'custom_output_folder': self.lang_manager.get_text('custom_output_folder') or "自定义输出目录:",
            'use_default_output': self.lang_manager.get_text('use_default_output') or "使用默认输出目录 (GIF同目录下新建文件夹)",
            'gif_info': self.lang_manager.get_text('gif_info') or "GIF信息:",
            'no_gif_selected': self.lang_manager.get_text('no_gif_selected') or "未选择GIF文件",
            'gif_selected': self.lang_manager.get_text('gif_selected') or "已选择GIF文件: {filename}",
            'invalid_gif_path': self.lang_manager.get_text('invalid_gif_path') or "无效的GIF文件路径。",
            'splitting_started': self.lang_manager.get_text('splitting_started') or "开始拆分GIF...",
            'splitting_complete': self.lang_manager.get_text('splitting_complete') or "GIF拆分完成! 共拆分为 {count} 帧",
            'splitting_error': self.lang_manager.get_text('splitting_error') or "拆分GIF时出错: {error}",
            'output_location': self.lang_manager.get_text('output_location') or "输出位置: {path}",
            'confirm_split': self.lang_manager.get_text('confirm_split') or "开始拆分GIF吗?",
        }
        
        # 配置网格布局
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(5, weight=1)  # 日志区域
        
        self.create_widgets()
        
    def create_widgets(self):
        """创建界面组件"""
        current_row = 0
        
        # 1. GIF文件选择
        ctk.CTkLabel(self, text=self.texts['select_gif_file']).grid(
            row=current_row, column=0, padx=10, pady=(10, 5), sticky="w")
        
        self.gif_entry = ctk.CTkEntry(self, placeholder_text=self.texts['select_gif_file_dialog_title'], width=350)
        self.gif_entry.grid(row=current_row, column=1, padx=10, pady=(10, 5), sticky="ew")
        self.gif_entry.bind("<KeyRelease>", self.on_gif_path_changed)
        
        self.browse_gif_btn = ctk.CTkButton(self, text=self.texts['browse'], 
                                           command=self.select_gif_file, width=80)
        self.browse_gif_btn.grid(row=current_row, column=2, padx=10, pady=(10, 5))
        current_row += 1
        
        # 拖放支持
        try:
            self.gif_entry.drop_target_register(DND_FILES)
            self.gif_entry.dnd_bind('<<Drop>>', 
                                  lambda e: handle_file_drop(e, self.gif_entry, self.lang_manager, ['.gif']))
        except Exception as e:
            print(f"GIF拖拽功能初始化失败: {e}")
        
        # 2. GIF信息显示
        self.gif_info_frame = ctk.CTkFrame(self)
        self.gif_info_frame.grid(row=current_row, column=0, columnspan=3, 
                               padx=10, pady=5, sticky="ew")
        self.gif_info_frame.grid_columnconfigure(1, weight=1)
        
        self.gif_info_label = ctk.CTkLabel(self.gif_info_frame, 
                                          text=self.texts['gif_info'], font=("Arial", 12, "bold"))
        self.gif_info_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.gif_details_label = ctk.CTkLabel(self.gif_info_frame, 
                                             text=self.texts['no_gif_selected'], 
                                             text_color="gray")
        self.gif_details_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        current_row += 1
        
        # 3. 输出格式选择
        format_frame = ctk.CTkFrame(self)
        format_frame.grid(row=current_row, column=0, columnspan=3, 
                         padx=10, pady=5, sticky="ew")
        format_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(format_frame, text=self.texts['output_format']).grid(
            row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.format_var = ctk.StringVar(value="png")
        self.format_combo = ctk.CTkComboBox(
            format_frame, 
            values=["png", "jpg", "bmp", "tiff", "webp"],
            variable=self.format_var,
            width=100
        )
        self.format_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # 输出目录选项
        self.output_dir_var = ctk.BooleanVar(value=True)
        self.output_dir_checkbox = ctk.CTkCheckBox(
            format_frame,
            text=self.texts['use_default_output'],
            variable=self.output_dir_var,
            command=self.toggle_output_dir_entry
        )
        self.output_dir_checkbox.grid(row=0, column=2, padx=20, pady=5, sticky="w")
        current_row += 1
        
        # 4. 自定义输出目录（默认隐藏）
        self.custom_output_frame = ctk.CTkFrame(self)
        self.custom_output_frame.grid(row=current_row, column=0, columnspan=3, 
                                     padx=10, pady=5, sticky="ew")
        self.custom_output_frame.grid_columnconfigure(1, weight=1)
        self.custom_output_frame.grid_remove()  # 默认隐藏
        
        ctk.CTkLabel(self.custom_output_frame, text=self.texts['custom_output_folder']).grid(
            row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.output_entry = ctk.CTkEntry(self.custom_output_frame, width=300)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.browse_output_btn = ctk.CTkButton(self.custom_output_frame, text=self.texts['browse'], 
                                              command=self.select_output_dir, width=80)
        self.browse_output_btn.grid(row=0, column=2, padx=5, pady=5)
        current_row += 1
        
        # 5. 按钮区域
        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=current_row, column=0, columnspan=3, 
                         padx=10, pady=10, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        self.split_btn = ctk.CTkButton(
            button_frame,
            text=self.texts['start_split'],
            command=self.start_splitting,
            width=120,
            fg_color="#388E3C",
            hover_color="#2E7D32"
        )
        self.split_btn.grid(row=0, column=0, padx=20, pady=5)
        
        self.clear_btn = ctk.CTkButton(
            button_frame,
            text=self.texts['clear_log'],
            command=self.clear_log,
            width=120
        )
        self.clear_btn.grid(row=0, column=1, padx=20, pady=5)
        current_row += 1
        
        # 6. 状态标签
        self.status_label = ctk.CTkLabel(self, text=self.texts['status_idle'], 
                                        text_color="gray")
        self.status_label.grid(row=current_row, column=0, columnspan=3, 
                              padx=10, pady=5, sticky="w")
        current_row += 1
        
        # 7. 日志区域
        ctk.CTkLabel(self, text=self.texts['log']).grid(
            row=current_row, column=0, padx=10, pady=(10, 5), sticky="w")
        current_row += 1
        
        self.log_area = ctk.CTkTextbox(self, wrap=tk.WORD, height=200)
        self.log_area.grid(row=current_row, column=0, columnspan=3, 
                          padx=10, pady=(0, 10), sticky="nsew")
        self.log_area.configure(state='disabled')
        
    def toggle_output_dir_entry(self):
        """切换自定义输出目录输入框的显示状态"""
        if self.output_dir_var.get():
            self.custom_output_frame.grid_remove()
        else:
            self.custom_output_frame.grid()
    
    def select_gif_file(self):
        """选择GIF文件"""
        file_path = filedialog.askopenfilename(
            title=self.texts['select_gif_file_dialog_title'],
            filetypes=[
                (self.texts['gif_files'], "*.gif"),
                (self.texts['all_files'], "*.*")
            ]
        )
        if file_path:
            self.gif_path = file_path
            self.gif_entry.delete(0, 'end')
            self.gif_entry.insert(0, file_path)
            self.update_gif_info()
    
    def on_gif_path_changed(self, event=None):
        """GIF路径改变时更新信息"""
        self.gif_path = self.gif_entry.get()
        if os.path.exists(self.gif_path) and self.gif_path.lower().endswith('.gif'):
            self.update_gif_info()
        else:
            self.gif_details_label.configure(text=self.texts['no_gif_selected'], 
                                           text_color="gray")
    
    def update_gif_info(self):
        """更新GIF文件信息显示"""
        if not self.gif_path or not os.path.exists(self.gif_path):
            return
            
        try:
            with Image.open(self.gif_path) as img:
                frame_count = 0
                is_animated = getattr(img, 'is_animated', False)
                
                if is_animated:
                    frame_count = img.n_frames if hasattr(img, 'n_frames') else 0
                    info_text = f"尺寸: {img.size} | 帧数: {frame_count} | 动画: 是"
                else:
                    info_text = f"尺寸: {img.size} | 静态GIF"
                    
                self.gif_details_label.configure(
                    text=self.texts['gif_selected'].format(filename=os.path.basename(self.gif_path)),
                    text_color="white"
                )
                self.status_label.configure(text=info_text)
                
        except Exception as e:
            self.log_message(f"读取GIF信息时出错: {str(e)}")
    
    def select_output_dir(self):
        """选择输出目录"""
        dir_path = filedialog.askdirectory(title=self.texts['select_folder_dialog_title'])
        if dir_path:
            self.output_dir = dir_path
            self.output_entry.delete(0, 'end')
            self.output_entry.insert(0, dir_path)
    
    def start_splitting(self):
        """开始拆分GIF"""
        if self.is_processing:
            return
            
        if not self.gif_path or not os.path.exists(self.gif_path):
            messagebox.showerror(self.texts['error_title'], 
                               self.texts['invalid_gif_path'])
            return
            
        # 确认操作
        if not messagebox.askyesno(self.texts['info_title'], 
                                  self.texts['confirm_split']):
            return
            
        # 准备输出目录
        output_dir = None
        if not self.output_dir_var.get() and self.output_entry.get():
            output_dir = self.output_entry.get()
        
        # 设置处理状态
        self.is_processing = True
        self.split_btn.configure(text=self.texts['processing'], state="disabled")
        self.browse_gif_btn.configure(state="disabled")
        
        # 清空日志
        self.clear_log()
        
        # 记录开始
        self.log_message(self.texts['splitting_started'])
        self.log_message(f"GIF文件: {self.gif_path}")
        self.log_message(f"输出格式: {self.format_var.get()}")
        
        if output_dir:
            self.log_message(f"输出目录: {output_dir}")
        else:
            self.log_message("输出目录: 自动创建 (GIF同目录下)")
        
        # 异步处理
        from gif_splitter import GifSplitter
        self.splitter = GifSplitter(log_callback=self.log_message)
        
        def on_complete(result):
            self.is_processing = False
            self.split_btn.configure(text=self.texts['start_split'], state="normal")
            self.browse_gif_btn.configure(state="normal")
            
            if result['success']:
                self.log_message(self.texts['splitting_complete'].format(count=result['frame_count']))
                self.log_message(self.texts['output_location'].format(path=result['output_dir']))
                messagebox.showinfo(self.texts['info_title'], 
                                  f"GIF拆分完成！\n共拆分为 {result['frame_count']} 帧\n输出目录: {result['output_dir']}")
            else:
                self.log_message(self.texts['splitting_error'].format(error=result.get('error', '未知错误')))
                messagebox.showerror(self.texts['error_title'], 
                                   f"拆分失败: {result.get('error', '未知错误')}")
        
        # 启动异步拆分
        self.splitter.split_gif_async(
            gif_path=self.gif_path,
            output_dir=output_dir,
            output_format=self.format_var.get(),
            callback=on_complete
        )
    
    def log_message(self, message):
        """添加日志消息"""
        self.log_area.configure(state='normal')
        self.log_area.insert('end', message + '\n')
        self.log_area.see('end')
        self.log_area.configure(state='disabled')
    
    def clear_log(self):
        """清空日志"""
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.configure(state='disabled')
    
    def update_ui_texts(self):
        """更新界面文本（用于语言切换）"""
        # 重新获取文本
        for key in self.texts:
            new_text = self.lang_manager.get_text(key)
            if new_text:
                self.texts[key] = new_text
        
        # 更新界面组件文本
        self.grid_slaves(row=0, column=0)[0].configure(text=self.texts['select_gif_file'])
        self.browse_gif_btn.configure(text=self.texts['browse'])
        self.gif_info_label.configure(text=self.texts['gif_info'])
        
        if not self.gif_path:
            self.gif_details_label.configure(text=self.texts['no_gif_selected'])
        
        self.grid_slaves(row=2, column=0)[0].grid_slaves(row=0, column=0)[0].configure(
            text=self.texts['output_format'])
        self.output_dir_checkbox.configure(text=self.texts['use_default_output'])
        
        if hasattr(self, 'custom_output_frame') and self.custom_output_frame.winfo_ismapped():
            self.custom_output_frame.grid_slaves(row=0, column=0)[0].configure(
                text=self.texts['custom_output_folder'])
            self.browse_output_btn.configure(text=self.texts['browse'])
        
        self.split_btn.configure(text=self.texts['start_split'] if not self.is_processing 
                               else self.texts['processing'])
        self.clear_btn.configure(text=self.texts['clear_log'])
        
        if not self.is_processing and not self.gif_path:
            self.status_label.configure(text=self.texts['status_idle'])
        
        self.grid_slaves(row=4, column=0)[0].configure(text=self.texts['log'])