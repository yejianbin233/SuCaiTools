"""
GIF粒子批量切片工具 — GUI界面模块

提供遮罩绘制画布、遮罩列表管理、批量提取控制等完整交互界面。
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import threading
import tkinter as tk
from tkinterdnd2 import DND_FILES
from particle_extractor import MaskDef, ParticleExtractor

# 遮罩颜色调色板（不同遮罩用不同颜色区分）
MASK_COLORS = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
    '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
    '#F8C471', '#82E0AA', '#F1948A', '#AED6F1', '#D2B4DE',
    '#A3E4D7', '#FAD7A0', '#EDBB99', '#D5F5E3', '#F9E79F'
]

# 遮罩视觉配置
MASK_NORMAL_COLOR = '#FF4444'       # 普通遮罩边框色
MASK_SELECTED_COLOR = '#44FF44'     # 选中遮罩边框色
MASK_DRAWING_COLOR = '#FFFF44'      # 绘制中预览色
MASK_NORMAL_WIDTH = 2               # 普通边框宽度
MASK_SELECTED_WIDTH = 3             # 选中边框宽度
MASK_DRAWING_WIDTH = 2              # 预览边框宽度
MASK_ALPHA_FILL = 30                # 填充不透明度 (0-255)
MIN_MASK_SIZE = 5                   # 最小遮罩尺寸（像素）


class ParticleExtractorFrame(ctk.CTkFrame):
    """粒子提取器GUI界面"""

    def __init__(self, master, lang_manager):
        super().__init__(master)
        self.lang_manager = lang_manager

        # ---------- 核心组件 ----------
        self.extractor = ParticleExtractor(log_callback=self.log_message)

        # ---------- 图片相关 ----------
        self.original_image = None        # PIL原始图片
        self.image_tk = None              # Tkinter图片对象（必须持有引用）
        self.original_image_size = (0, 0) # 原始图片尺寸 (w, h)
        self.reference_image_path = ""    # 参考帧图片路径
        self.frames_dir = ""              # 帧序列文件夹路径

        # ---------- 显示参数 ----------
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.canvas_width = 780
        self.canvas_height = 520

        # ---------- 遮罩数据 ----------
        self.masks: list[MaskDef] = []
        self.next_mask_id = 1

        # ---------- 交互状态 ----------
        self.selected_mask_id = None       # 当前选中的遮罩ID
        self.is_drawing = False            # 是否正在绘制新遮罩
        self.is_moving = False             # 是否正在移动已有遮罩
        self.draw_start_x = 0              # 绘制起始X（画布坐标）
        self.draw_start_y = 0              # 绘制起始Y（画布坐标）
        self.move_offset_x = 0             # 移动偏移X（原始坐标）
        self.move_offset_y = 0             # 移动偏移Y（原始坐标）
        self.preview_rect_id = None        # 预览矩形画布ID

        # ---------- 处理状态 ----------
        self.is_processing = False

        # ---------- 多语言文本 ----------
        self.texts = {
            'tab_particle_extractor': self.lang_manager.get_text('tab_particle_extractor') or "GIF粒子提取器",
            'select_frames_folder': self.lang_manager.get_text('select_frames_folder') or "帧序列文件夹:",
            'browse': self.lang_manager.get_text('browse') or "浏览...",
            'select_ref_frame': self.lang_manager.get_text('select_ref_frame') or "参考帧图片:",
            'load_ref_frame': self.lang_manager.get_text('load_ref_frame') or "加载参考帧",
            'masks_panel': self.lang_manager.get_text('masks_panel') or "遮罩列表",
            'btn_clear_masks': self.lang_manager.get_text('btn_clear_masks') or "清空全部遮罩",
            'btn_save_masks': self.lang_manager.get_text('btn_save_masks') or "保存遮罩",
            'btn_load_masks': self.lang_manager.get_text('btn_load_masks') or "加载遮罩",
            'btn_delete_mask': self.lang_manager.get_text('btn_delete_mask') or "删除选中",
            'pe_output_dir': self.lang_manager.get_text('pe_output_dir') or "输出目录:",
            'output_format': self.lang_manager.get_text('output_format') or "输出格式:",
            'start_extract': self.lang_manager.get_text('start_extract') or "开始提取",
            'pe_stop': self.lang_manager.get_text('pe_stop') or "停止",
            'log': self.lang_manager.get_text('log') or "日志:",
            'clear_log': self.lang_manager.get_text('clear_log') or "清空日志",
            'pe_status_idle': self.lang_manager.get_text('pe_status_idle') or "就绪 - 请加载参考帧图片",
            'status_ready': self.lang_manager.get_text('status_ready') or "请在画布上绘制矩形遮罩标记粒子位置",
            'processing': self.lang_manager.get_text('processing') or "处理中...",
            'error_title': self.lang_manager.get_text('error_title') or "错误",
            'info_title': self.lang_manager.get_text('info_title') or "信息",
            'warning_title': self.lang_manager.get_text('warning_title') or "警告",
            'pe_confirm_extract_title': self.lang_manager.get_text('pe_confirm_extract_title') or "确认提取",
            'pe_confirm_extract': self.lang_manager.get_text('pe_confirm_extract') or "使用 {mask_count} 个遮罩从 {total_frames} 帧提取粒子?",
            'pe_status_extracting': self.lang_manager.get_text('pe_status_extracting') or "正在提取粒子... {current}/{total}",
            'pe_status_complete': self.lang_manager.get_text('pe_status_complete') or "提取完成! 共处理 {frames} 帧 × {masks} 个遮罩",
            'pe_error_no_frames': self.lang_manager.get_text('pe_error_no_frames') or "所选文件夹中没有找到帧图片。",
            'pe_error_no_masks': self.lang_manager.get_text('pe_error_no_masks') or "请至少创建一个遮罩。",
            'pe_error_no_ref_frame': self.lang_manager.get_text('pe_error_no_ref_frame') or "请先加载一张参考帧图片。",
            'save_masks_title': self.lang_manager.get_text('save_masks_title') or "保存遮罩定义",
            'load_masks_title': self.lang_manager.get_text('load_masks_title') or "加载遮罩定义",
            'mask_files': self.lang_manager.get_text('mask_files') or "遮罩文件",
            'select_output_dir_title': self.lang_manager.get_text('select_output_dir_title') or "选择输出目录",
            'log_mask_info': self.lang_manager.get_text('log_mask_info') or "遮罩 {label}: 位置({x},{y}) 尺寸{w}x{h}",
        }

        # ---------- 创建界面 ----------
        self.create_widgets()

    # ==================== 界面创建 ====================

    def create_widgets(self):
        """创建所有界面组件"""
        # 网格配置
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # 画布行可伸缩
        self.grid_rowconfigure(5, weight=1)   # 日志行可伸缩

        current_row = 0

        # ---- Row 0: 帧序列文件夹选择 ----
        folder_frame = ctk.CTkFrame(self)
        folder_frame.grid(row=current_row, column=0, padx=10, pady=(10, 5), sticky="ew")
        folder_frame.grid_columnconfigure(1, weight=1)

        self.folder_label = ctk.CTkLabel(
            folder_frame, text=self.texts['select_frames_folder'])
        self.folder_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.folder_entry = ctk.CTkEntry(folder_frame, width=350)
        self.folder_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.folder_entry.bind("<KeyRelease>", self.on_folder_entry_changed)

        self.folder_browse_btn = ctk.CTkButton(
            folder_frame, text=self.texts['browse'],
            command=self.select_frames_folder, width=80)
        self.folder_browse_btn.grid(row=0, column=2, padx=5, pady=5)

        # 拖放支持
        try:
            self.folder_entry.drop_target_register(DND_FILES)
            self.folder_entry.dnd_bind('<<Drop>>', self.on_folder_drop)
        except Exception as e:
            print(f"文件夹拖放初始化失败: {e}")

        current_row += 1

        # ---- Row 1: 参考帧图片选择 ----
        ref_frame = ctk.CTkFrame(self)
        ref_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew")
        ref_frame.grid_columnconfigure(1, weight=1)

        self.ref_label = ctk.CTkLabel(ref_frame, text=self.texts['select_ref_frame'])
        self.ref_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.ref_entry = ctk.CTkEntry(ref_frame, width=350)
        self.ref_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.ref_load_btn = ctk.CTkButton(
            ref_frame, text=self.texts['browse'],
            command=self.select_ref_image, width=80)
        self.ref_load_btn.grid(row=0, column=2, padx=5, pady=5)

        self.ref_load_action_btn = ctk.CTkButton(
            ref_frame, text=self.texts['load_ref_frame'],
            command=self.load_reference_image, width=100)
        self.ref_load_action_btn.grid(row=0, column=3, padx=5, pady=5)

        # 拖放支持
        try:
            self.ref_entry.drop_target_register(DND_FILES)
            self.ref_entry.dnd_bind('<<Drop>>', self.on_ref_image_drop)
        except Exception as e:
            print(f"参考帧拖放初始化失败: {e}")

        current_row += 1

        # ---- Row 2: 左侧画布 + 右侧遮罩列表面板 ----
        work_frame = ctk.CTkFrame(self)
        work_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="nsew")
        work_frame.grid_columnconfigure(0, weight=1)   # 画布占大部分空间
        work_frame.grid_rowconfigure(0, weight=1)

        # --- 左侧: 画布 ---
        canvas_frame = ctk.CTkFrame(work_frame)
        canvas_frame.grid(row=0, column=0, padx=(0, 5), pady=0, sticky="nsew")
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas_frame.grid_rowconfigure(0, weight=1)

        self.image_canvas = ctk.CTkCanvas(
            canvas_frame, bg="#1a1a1a", highlightthickness=0,
            width=self.canvas_width, height=self.canvas_height)
        self.image_canvas.grid(row=0, column=0, sticky="nsew")

        # 绑定画布事件
        self.image_canvas.bind('<ButtonPress-1>', self.on_canvas_mouse_down)
        self.image_canvas.bind('<B1-Motion>', self.on_canvas_mouse_drag)
        self.image_canvas.bind('<ButtonRelease-1>', self.on_canvas_mouse_up)
        self.image_canvas.bind('<ButtonPress-3>', self.on_canvas_right_click)
        self.image_canvas.bind('<Configure>', self.on_canvas_resize)
        self.bind('<Delete>', self.on_delete_key)
        self.bind('<Escape>', self.on_escape_key)

        # 绘制提示文本
        self._show_canvas_placeholder()

        # --- 右侧: 遮罩列表面板 ---
        right_panel = ctk.CTkFrame(work_frame, width=220)
        right_panel.grid(row=0, column=1, padx=(5, 0), pady=0, sticky="nsew")
        right_panel.grid_propagate(False)

        # 面板标题
        self.masks_panel_label = ctk.CTkLabel(right_panel, text=self.texts['masks_panel'],
                     font=ctk.CTkFont(size=14, weight="bold"))
        self.masks_panel_label.pack(pady=(10, 5))

        # 遮罩列表（使用tk.Listbox，因为ctk没有原生Listbox）
        list_container = ctk.CTkFrame(right_panel)
        list_container.pack(fill="both", expand=True, padx=10, pady=5)

        self.mask_listbox = tk.Listbox(
            list_container, bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#3a7eb0", selectforeground="#ffffff",
            activestyle="none", borderwidth=0, highlightthickness=0,
            font=("Consolas", 10))
        self.mask_listbox.pack(side="left", fill="both", expand=True)

        # Listbox滚动条
        list_scrollbar = ctk.CTkScrollbar(
            list_container, orientation="vertical",
            command=self.mask_listbox.yview)
        list_scrollbar.pack(side="right", fill="y")
        self.mask_listbox.configure(yscrollcommand=list_scrollbar.set)

        self.mask_listbox.bind('<<ListboxSelect>>', self.on_listbox_select)

        # 面板按钮（保存引用以便语言切换时更新文本）
        self.btn_delete = ctk.CTkButton(
            right_panel, text=self.texts['btn_delete_mask'],
            command=self.delete_selected_mask, width=180)
        self.btn_delete.pack(pady=(5, 2), padx=10)

        self.btn_clear = ctk.CTkButton(
            right_panel, text=self.texts['btn_clear_masks'],
            command=self.clear_all_masks, width=180)
        self.btn_clear.pack(pady=2, padx=10)

        self.btn_save = ctk.CTkButton(
            right_panel, text=self.texts['btn_save_masks'],
            command=self.save_masks, width=180)
        self.btn_save.pack(pady=2, padx=10)

        self.btn_load = ctk.CTkButton(
            right_panel, text=self.texts['btn_load_masks'],
            command=self.load_masks, width=180)
        self.btn_load.pack(pady=(2, 10), padx=10)

        current_row += 1

        # ---- Row 3: 输出设置 ----
        output_frame = ctk.CTkFrame(self)
        output_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew")
        output_frame.grid_columnconfigure(1, weight=1)

        self.output_dir_label = ctk.CTkLabel(
            output_frame, text=self.texts['pe_output_dir'])
        self.output_dir_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.output_entry = ctk.CTkEntry(output_frame, width=300)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.output_browse_btn = ctk.CTkButton(
            output_frame, text=self.texts['browse'],
            command=self.select_output_dir, width=80)
        self.output_browse_btn.grid(row=0, column=2, padx=5, pady=5)

        self.output_format_label = ctk.CTkLabel(
            output_frame, text=self.texts['output_format'])
        self.output_format_label.grid(row=0, column=3, padx=(15, 5), pady=5, sticky="w")

        self.format_var = ctk.StringVar(value="png")
        self.format_combo = ctk.CTkComboBox(
            output_frame, values=["png", "jpg", "bmp"],
            variable=self.format_var, width=80, state="readonly")
        self.format_combo.grid(row=0, column=4, padx=5, pady=5)

        current_row += 1

        # ---- Row 4: 操作按钮和进度 ----
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=current_row, column=0, padx=10, pady=5, sticky="ew")
        action_frame.grid_columnconfigure(2, weight=1)

        self.start_btn = ctk.CTkButton(
            action_frame, text=self.texts['start_extract'],
            command=self.start_extraction, fg_color="#2e8b57", width=120)
        self.start_btn.grid(row=0, column=0, padx=5, pady=5)

        self.stop_btn = ctk.CTkButton(
            action_frame, text=self.texts['pe_stop'],
            command=self.stop_extraction, width=80, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=5, pady=5)

        self.progress_bar = ctk.CTkProgressBar(action_frame, width=200)
        self.progress_bar.grid(row=0, column=2, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            action_frame, text=self.texts['pe_status_idle'], text_color="gray")
        self.status_label.grid(row=0, column=3, padx=5, pady=5, sticky="e")

        current_row += 1

        # ---- Row 5: 日志区域 ----
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=current_row, column=0, padx=10, pady=(5, 10), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_frame)
        log_header.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)

        self.log_label = ctk.CTkLabel(log_header, text=self.texts['log'])
        self.log_label.pack(side="left", padx=5)
        self.clear_log_btn = ctk.CTkButton(
            log_header, text=self.texts['clear_log'],
            command=self.clear_log, width=80)
        self.clear_log_btn.pack(side="right", padx=5)

        self.log_area = ctk.CTkTextbox(log_frame, wrap=tk.WORD, height=120)
        self.log_area.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        self.log_area.configure(state='disabled')

    # ==================== 日志输出 ====================

    def log_message(self, message: str):
        """输出日志到日志区域"""
        self.after(0, lambda: self._write_log(message))

    def _write_log(self, message: str):
        """在主线程写入日志"""
        try:
            self.log_area.configure(state='normal')
            self.log_area.insert('end', message + '\n')
            self.log_area.see('end')
            self.log_area.configure(state='disabled')
        except Exception:
            pass  # 组件已销毁时忽略

    def clear_log(self):
        """清空日志"""
        try:
            self.log_area.configure(state='normal')
            self.log_area.delete('1.0', 'end')
            self.log_area.configure(state='disabled')
        except Exception:
            pass

    # ==================== 文件夹/图片选择 ====================

    def select_frames_folder(self):
        """选择帧序列文件夹"""
        folder = filedialog.askdirectory(title="选择帧序列文件夹")
        if folder:
            self.frames_dir = folder
            self.folder_entry.delete(0, 'end')
            self.folder_entry.insert(0, folder)
            self.log_message(f"已选择帧序列文件夹: {folder}")

    def on_folder_entry_changed(self, event=None):
        """文件夹路径手动输入变更"""
        path = self.folder_entry.get().strip()
        if os.path.isdir(path):
            self.frames_dir = path

    def on_folder_drop(self, event):
        """拖放文件夹到帧序列输入框"""
        try:
            path = event.data.strip('{}')
            if os.path.isdir(path):
                self.frames_dir = path
                self.folder_entry.delete(0, 'end')
                self.folder_entry.insert(0, path)
                self.log_message(f"已拖放帧序列文件夹: {path}")
        except Exception as e:
            self.log_message(f"拖放处理失败: {str(e)}")

    def select_ref_image(self):
        """选择参考帧图片"""
        file_path = filedialog.askopenfilename(
            title="选择参考帧图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")])
        if file_path:
            self.ref_entry.delete(0, 'end')
            self.ref_entry.insert(0, file_path)

    def on_ref_image_drop(self, event):
        """拖放参考帧图片"""
        try:
            path = event.data.strip('{}')
            if os.path.isfile(path):
                self.ref_entry.delete(0, 'end')
                self.ref_entry.insert(0, path)
        except Exception as e:
            self.log_message(f"拖放处理失败: {str(e)}")

    def load_reference_image(self):
        """加载参考帧图片到画布"""
        path = self.ref_entry.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(
                self.texts['error_title'],
                self.texts['pe_error_no_ref_frame'])
            return

        try:
            self.original_image = Image.open(path)
            # 转为RGB模式以便Canvas显示
            if self.original_image.mode in ('RGBA', 'P', 'LA'):
                self.original_image = self.original_image.convert('RGBA')
            elif self.original_image.mode != 'RGB':
                self.original_image = self.original_image.convert('RGB')

            self.original_image_size = self.original_image.size
            self.reference_image_path = path
            self.log_message(f"已加载参考帧: {os.path.basename(path)} "
                             f"({self.original_image_size[0]}×{self.original_image_size[1]})")

            # 重置遮罩（图片尺寸改变了）
            self.masks.clear()
            self.next_mask_id = 1
            self.selected_mask_id = None
            self.update_mask_listbox()

            # 显示图片
            self.redraw_canvas()
            self.status_label.configure(text=self.texts['status_ready'], text_color="#78e46f")

        except Exception as e:
            messagebox.showerror(
                self.texts['error_title'],
                f"加载图片失败: {str(e)}")

    def select_output_dir(self):
        """选择输出目录"""
        folder = filedialog.askdirectory(title=self.texts['select_output_dir_title'])
        if folder:
            self.output_entry.delete(0, 'end')
            self.output_entry.insert(0, folder)

    # ==================== 画布显示 ====================

    def _show_canvas_placeholder(self):
        """显示占位提示文本"""
        self.image_canvas.delete("all")
        self.image_canvas.create_text(
            self.canvas_width // 2, self.canvas_height // 2,
            text="加载参考帧图片后\n在此绘制矩形遮罩",
            fill="#666666", font=("Arial", 16), justify="center")

    def on_canvas_resize(self, event=None):
        """画布大小改变时重绘"""
        if self.original_image:
            self.redraw_canvas()

    def _calc_display_params(self):
        """计算缩放比例和居中偏移量"""
        canvas_w = self.image_canvas.winfo_width()
        canvas_h = self.image_canvas.winfo_height()

        # 避免初始尺寸为1的情况
        if canvas_w < 10 or canvas_h < 10:
            canvas_w = self.canvas_width
            canvas_h = self.canvas_height

        img_w, img_h = self.original_image_size
        if img_w == 0 or img_h == 0:
            return 1.0, 0, 0

        # 等比缩放，使图片完全可见
        scale = min(canvas_w / img_w, canvas_h / img_h)

        # 居中偏移
        display_w = int(img_w * scale)
        display_h = int(img_h * scale)
        off_x = (canvas_w - display_w) // 2
        off_y = (canvas_h - display_h) // 2

        return scale, off_x, off_y

    def canvas_to_original(self, canvas_x: int, canvas_y: int) -> tuple:
        """画布坐标 → 原始图像坐标"""
        ox = (canvas_x - self.offset_x) / self.scale_factor
        oy = (canvas_y - self.offset_y) / self.scale_factor
        # 钳制到图像范围
        img_w, img_h = self.original_image_size
        ox = max(0, min(int(ox), img_w - 1))
        oy = max(0, min(int(oy), img_h - 1))
        return ox, oy

    def original_to_canvas(self, orig_x: int, orig_y: int) -> tuple:
        """原始图像坐标 → 画布坐标"""
        cx = orig_x * self.scale_factor + self.offset_x
        cy = orig_y * self.scale_factor + self.offset_y
        return cx, cy

    def redraw_canvas(self):
        """全量重绘画布：底图 + 所有遮罩"""
        self.image_canvas.delete("all")

        if not self.original_image:
            self._show_canvas_placeholder()
            return

        # 计算显示参数
        self.scale_factor, self.offset_x, self.offset_y = self._calc_display_params()

        # 缩放图片
        display_w = int(self.original_image_size[0] * self.scale_factor)
        display_h = int(self.original_image_size[1] * self.scale_factor)
        display_img = self.original_image.resize(
            (display_w, display_h), Image.Resampling.LANCZOS)

        # 转为PhotoImage（必须持有引用）
        self.image_tk = ImageTk.PhotoImage(display_img)

        # 居中绘制
        self.image_canvas.create_image(
            self.offset_x, self.offset_y,
            image=self.image_tk, anchor="nw")

        # 绘制所有遮罩
        for i, mask in enumerate(self.masks):
            is_selected = (mask.id == self.selected_mask_id)

            # 转换坐标
            cx1, cy1 = self.original_to_canvas(mask.x, mask.y)
            cx2, cy2 = self.original_to_canvas(
                mask.x + mask.width, mask.y + mask.height)

            # 选择颜色
            if is_selected:
                color = MASK_SELECTED_COLOR
                width = MASK_SELECTED_WIDTH
            else:
                color = MASK_COLORS[i % len(MASK_COLORS)]
                width = MASK_NORMAL_WIDTH

            # 绘制矩形（先填充后半透明边框）
            self.image_canvas.create_rectangle(
                cx1, cy1, cx2, cy2,
                outline=color, width=width)

            # 绘制半透明填充（通过交错点阵模拟）
            # 使用create_rectangle的stipple选项
            if is_selected:
                self.image_canvas.create_rectangle(
                    cx1 + 1, cy1 + 1, cx2 - 1, cy2 - 1,
                    fill='', outline='', stipple='gray25')

            # 绘制编号标签背景
            label = mask.label
            label_x = cx1 + 3
            label_y = cy1 + 3

            # 标签背景色块
            text_id = self.image_canvas.create_text(
                label_x + 1, label_y + 1,
                text=label, anchor="nw",
                fill="black",
                font=("Consolas", 11, "bold"))
            bbox = self.image_canvas.bbox(text_id)
            if bbox:
                self.image_canvas.create_rectangle(
                    bbox, fill="#1a1a1a", outline=color, width=1)
                self.image_canvas.tag_raise(text_id)
            self.image_canvas.itemconfig(text_id, fill=color)

    # ==================== 遮罩绘制交互 ====================

    def _find_mask_at_canvas(self, canvas_x: int, canvas_y: int) -> int | None:
        """查找画布坐标处的遮罩，返回遮罩ID（无则返回None）"""
        ox, oy = self.canvas_to_original(canvas_x, canvas_y)
        # 逆序遍历，先检查上层遮罩
        for mask in reversed(self.masks):
            if (mask.x <= ox <= mask.x + mask.width and
                    mask.y <= oy <= mask.y + mask.height):
                return mask.id
        return None

    def on_canvas_mouse_down(self, event):
        """画布鼠标按下"""
        if not self.original_image:
            return

        # 检查是否点击了已有遮罩
        clicked_mask_id = self._find_mask_at_canvas(event.x, event.y)

        if clicked_mask_id is not None:
            # 点击遮罩 → 选中并准备移动
            self.selected_mask_id = clicked_mask_id
            self.is_moving = True
            self.is_drawing = False

            # 记录移动偏移量（原始坐标）
            ox, oy = self.canvas_to_original(event.x, event.y)
            for mask in self.masks:
                if mask.id == clicked_mask_id:
                    self.move_offset_x = ox - mask.x
                    self.move_offset_y = oy - mask.y
                    break

            self.redraw_canvas()
            self.update_mask_listbox()
        else:
            # 点击空白区域 → 开始绘制新遮罩
            self.selected_mask_id = None
            self.is_drawing = True
            self.is_moving = False
            self.draw_start_x = event.x
            self.draw_start_y = event.y

            # 创建预览矩形
            self.preview_rect_id = self.image_canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=MASK_DRAWING_COLOR, width=MASK_DRAWING_WIDTH,
                dash=(6, 3))

            self.redraw_canvas()
            self.update_mask_listbox()

    def on_canvas_mouse_drag(self, event):
        """画布鼠标拖拽"""
        if not self.original_image:
            return

        if self.is_drawing and self.preview_rect_id:
            # 更新预览矩形
            self.image_canvas.coords(
                self.preview_rect_id,
                self.draw_start_x, self.draw_start_y,
                event.x, event.y)

        elif self.is_moving and self.selected_mask_id is not None:
            # 移动选中遮罩
            ox, oy = self.canvas_to_original(event.x, event.y)
            new_x = ox - self.move_offset_x
            new_y = oy - self.move_offset_y

            # 边界钳制
            img_w, img_h = self.original_image_size
            for mask in self.masks:
                if mask.id == self.selected_mask_id:
                    new_x = max(0, min(new_x, img_w - mask.width))
                    new_y = max(0, min(new_y, img_h - mask.height))
                    mask.x = int(new_x)
                    mask.y = int(new_y)
                    break

            self.redraw_canvas()
            self.update_mask_listbox()

    def on_canvas_mouse_up(self, event):
        """画布鼠标释放"""
        if self.is_drawing:
            self.is_drawing = False

            # 删除预览矩形
            if self.preview_rect_id:
                self.image_canvas.delete(self.preview_rect_id)
                self.preview_rect_id = None

            # 计算遮罩尺寸（原始坐标）
            ox1, oy1 = self.canvas_to_original(self.draw_start_x, self.draw_start_y)
            ox2, oy2 = self.canvas_to_original(event.x, event.y)

            x = min(ox1, ox2)
            y = min(oy1, oy2)
            w = abs(ox2 - ox1)
            h = abs(oy2 - oy1)

            # 最小尺寸检查
            if w >= MIN_MASK_SIZE and h >= MIN_MASK_SIZE:
                mask = MaskDef(
                    id=self.next_mask_id,
                    label=f"mask_{self.next_mask_id:02d}",
                    x=x, y=y, width=w, height=h
                )
                self.masks.append(mask)
                self.selected_mask_id = mask.id
                self.next_mask_id += 1

                self.log_message(
                    f"新建遮罩 {mask.label}: 位置({x},{y}) 尺寸{w}×{h}")
            else:
                self.selected_mask_id = None

            self.redraw_canvas()
            self.update_mask_listbox()

        elif self.is_moving:
            self.is_moving = False
            # 移动完成后记录新位置
            if self.selected_mask_id is not None:
                for mask in self.masks:
                    if mask.id == self.selected_mask_id:
                        self.log_message(
                            f"遮罩 {mask.label} 移动到: 位置({mask.x},{mask.y})")
                        break

    def on_canvas_right_click(self, event):
        """右键点击 → 删除点击处的遮罩"""
        if not self.original_image:
            return

        # 取消绘制
        if self.is_drawing:
            self.is_drawing = False
            if self.preview_rect_id:
                self.image_canvas.delete(self.preview_rect_id)
                self.preview_rect_id = None

        # 查找并删除遮罩
        clicked_id = self._find_mask_at_canvas(event.x, event.y)
        if clicked_id is not None:
            self._remove_mask_by_id(clicked_id)
        elif self.selected_mask_id is not None:
            # 如果右键空白处，也取消选中
            self.selected_mask_id = None

        self.is_moving = False
        self.redraw_canvas()
        self.update_mask_listbox()

    # ==================== 键盘操作 ====================

    def on_delete_key(self, event=None):
        """Delete键 → 删除选中遮罩"""
        if self.selected_mask_id is not None:
            self._remove_mask_by_id(self.selected_mask_id)
            self.redraw_canvas()
            self.update_mask_listbox()

    def on_escape_key(self, event=None):
        """Escape键 → 取消当前操作"""
        if self.is_drawing:
            self.is_drawing = False
            if self.preview_rect_id:
                self.image_canvas.delete(self.preview_rect_id)
                self.preview_rect_id = None
            self.redraw_canvas()
        self.selected_mask_id = None
        self.is_moving = False
        self.redraw_canvas()
        self.update_mask_listbox()

    # ==================== 遮罩管理 ====================

    def _remove_mask_by_id(self, mask_id: int):
        """按ID删除遮罩"""
        for mask in self.masks:
            if mask.id == mask_id:
                self.log_message(f"已删除遮罩 {mask.label}")
                break
        self.masks = [m for m in self.masks if m.id != mask_id]
        if self.selected_mask_id == mask_id:
            self.selected_mask_id = None

    def delete_selected_mask(self):
        """删除选中的遮罩（按钮触发）"""
        if self.selected_mask_id is not None:
            self._remove_mask_by_id(self.selected_mask_id)
            self.redraw_canvas()
            self.update_mask_listbox()

    def clear_all_masks(self):
        """清空所有遮罩"""
        if self.masks:
            self.log_message(f"已清空 {len(self.masks)} 个遮罩")
            self.masks.clear()
            self.next_mask_id = 1
            self.selected_mask_id = None
            self.redraw_canvas()
            self.update_mask_listbox()

    def update_mask_listbox(self):
        """更新遮罩列表显示"""
        self.mask_listbox.delete(0, 'end')
        for mask in self.masks:
            # 格式: "mask_01  (100,50) 200×150"
            item_text = f"{mask.label}  ({mask.x},{mask.y}) {mask.width}×{mask.height}"
            self.mask_listbox.insert('end', item_text)

            # 高亮选中的项
            if mask.id == self.selected_mask_id:
                idx = self.mask_listbox.size() - 1
                self.mask_listbox.selection_set(idx)
                self.mask_listbox.activate(idx)

    def on_listbox_select(self, event=None):
        """列表项被点击 → 选中对应遮罩"""
        selection = self.mask_listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.masks):
                self.selected_mask_id = self.masks[idx].id
                self.redraw_canvas()

    # ==================== 遮罩保存/加载 ====================

    def save_masks(self):
        """保存遮罩定义到JSON文件"""
        if not self.masks:
            messagebox.showwarning(
                self.texts['warning_title'],
                self.texts['pe_error_no_masks'])
            return

        filepath = filedialog.asksaveasfilename(
            title=self.texts['save_masks_title'],
            defaultextension=".json",
            filetypes=[(self.texts['mask_files'], "*.json"), ("所有文件", "*.*")])
        if not filepath:
            return

        try:
            ParticleExtractor.save_masks_to_file(
                self.masks, filepath,
                reference_image_path=self.reference_image_path,
                image_size=self.original_image_size)
            self.log_message(f"遮罩定义已保存到: {filepath}")
        except Exception as e:
            messagebox.showerror(
                self.texts['error_title'],
                f"保存遮罩失败: {str(e)}")

    def load_masks(self):
        """从JSON文件加载遮罩定义"""
        filepath = filedialog.askopenfilename(
            title=self.texts['load_masks_title'],
            filetypes=[(self.texts['mask_files'], "*.json"), ("所有文件", "*.*")])
        if not filepath:
            return

        try:
            masks, metadata = ParticleExtractor.load_masks_from_file(filepath)

            # 校验图片尺寸
            saved_size = metadata.get('image_size')
            if (saved_size and self.original_image and
                    saved_size != self.original_image_size):
                result = messagebox.askyesno(
                    self.texts['warning_title'],
                    f"遮罩是为 {saved_size[0]}×{saved_size[1]} 的图片创建的，"
                    f"当前图片尺寸为 {self.original_image_size[0]}×"
                    f"{self.original_image_size[1]}。\n\n"
                    f"遮罩位置可能不准确，是否继续加载？")
                if not result:
                    return

            # 应用加载的遮罩
            self.masks = masks
            self.next_mask_id = max((m.id for m in masks), default=0) + 1
            self.selected_mask_id = None

            self.redraw_canvas()
            self.update_mask_listbox()
            self.log_message(f"已加载 {len(masks)} 个遮罩定义: {filepath}")

        except Exception as e:
            messagebox.showerror(
                self.texts['error_title'],
                f"加载遮罩失败: {str(e)}")

    # ==================== 批量提取 ====================

    def start_extraction(self):
        """开始批量提取"""
        # 验证前置条件
        if not self.frames_dir or not os.path.isdir(self.frames_dir):
            messagebox.showerror(
                self.texts['error_title'],
                self.texts['pe_error_no_frames'])
            return

        if not self.masks:
            messagebox.showerror(
                self.texts['error_title'],
                self.texts['pe_error_no_masks'])
            return

        output_dir = self.output_entry.get().strip()
        if not output_dir:
            # 默认输出到帧目录下的 particles 子目录
            output_dir = os.path.join(self.frames_dir, "particles")
            self.output_entry.delete(0, 'end')
            self.output_entry.insert(0, output_dir)

        # 确认
        try:
            frame_count = len(self.extractor.scan_frame_files(self.frames_dir))
        except Exception as e:
            messagebox.showerror(self.texts['error_title'], str(e))
            return

        confirm_text = self.texts['pe_confirm_extract'].format(
            mask_count=len(self.masks), total_frames=frame_count)
        if not messagebox.askyesno(self.texts['pe_confirm_extract_title'], confirm_text):
            return

        # 进入处理状态
        self.is_processing = True
        self.start_btn.configure(state="disabled", text=self.texts['processing'])
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text=self.texts['processing'], text_color="#ffaa00")
        self.progress_bar.set(0)

        # 启动异步提取
        output_format = self.format_var.get()

        def on_progress(current, total):
            self.after(0, lambda: self._update_progress(current, total))

        def on_complete(result):
            self.after(0, lambda: self._on_extraction_complete(result))

        self.extractor.extract_async(
            masks=self.masks,
            frames_dir=self.frames_dir,
            output_dir=output_dir,
            output_format=output_format,
            callback=on_complete,
            progress_callback=on_progress
        )

    def _update_progress(self, current: int, total: int):
        """更新进度条和状态"""
        self.progress_bar.set(current / total if total > 0 else 0)
        status = self.texts['pe_status_extracting'].format(current=current, total=total)
        self.status_label.configure(text=status)

    def _on_extraction_complete(self, result: dict):
        """提取完成回调"""
        self.is_processing = False
        self.start_btn.configure(state="normal", text=self.texts['start_extract'])
        self.stop_btn.configure(state="disabled")

        if result.get('success'):
            frames = result.get('frame_count', 0)
            masks_count = result.get('mask_count', 0)
            output_dir = result.get('output_dir', '')
            status = self.texts['pe_status_complete'].format(frames=frames, masks=masks_count)
            self.status_label.configure(text=status, text_color="#78e46f")
            self.progress_bar.set(1.0)
            messagebox.showinfo(
                self.texts['info_title'],
                f"{status}\n输出目录: {output_dir}")
        else:
            error = result.get('error', '未知错误')
            self.status_label.configure(text=f"提取失败: {error}", text_color="#ff4444")
            self.progress_bar.set(0)

    def stop_extraction(self):
        """停止正在进行的提取"""
        if self.is_processing:
            self.extractor.stop()
            self.stop_btn.configure(state="disabled")

    # ==================== 语言切换 ====================

    def update_ui_texts(self):
        """语言切换时更新所有UI文本（引用GifSplitterFrame的模式）"""
        # 刷新self.texts字典
        for key in list(self.texts.keys()):
            new_text = self.lang_manager.get_text(key)
            if new_text and new_text != key:
                self.texts[key] = new_text

        # 更新各控件文本 — 使用保存的引用

        # Row 0: 帧序列文件夹
        self.folder_label.configure(text=self.texts['select_frames_folder'])
        self.folder_browse_btn.configure(text=self.texts['browse'])

        # Row 1: 参考帧
        self.ref_label.configure(text=self.texts['select_ref_frame'])
        self.ref_load_btn.configure(text=self.texts['browse'])
        self.ref_load_action_btn.configure(text=self.texts['load_ref_frame'])

        # 右侧面板: 遮罩列表
        self.masks_panel_label.configure(text=self.texts['masks_panel'])
        self.btn_delete.configure(text=self.texts['btn_delete_mask'])
        self.btn_clear.configure(text=self.texts['btn_clear_masks'])
        self.btn_save.configure(text=self.texts['btn_save_masks'])
        self.btn_load.configure(text=self.texts['btn_load_masks'])

        # Row 3: 输出设置
        self.output_dir_label.configure(text=self.texts['pe_output_dir'])
        self.output_format_label.configure(text=self.texts['output_format'])
        self.output_browse_btn.configure(text=self.texts['browse'])

        # Row 4: 操作按钮
        self.start_btn.configure(text=self.texts['start_extract'])
        self.stop_btn.configure(text=self.texts['pe_stop'])

        # 日志区域
        self.log_label.configure(text=self.texts['log'])
        self.clear_log_btn.configure(text=self.texts['clear_log'])

        # 恢复状态文本
        if not self.original_image:
            self.status_label.configure(text=self.texts['pe_status_idle'])
        else:
            self.status_label.configure(text=self.texts['status_ready'])
