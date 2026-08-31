"""
图片像素化工具面板
===================
把普通图片批量转换为像素风 PNG。
管线与纯逻辑模块 pixelizer.py 一致：
色键抠除（可选）→ 自动裁切（可选）→ 盒滤波降采样 → 调色板映射/自动量化
→ 抖动（可选）→ alpha 处理 → 边缘清理。
支持尺寸（宽高独立/0=原图/锁定比例/像素块大小/附加尺寸）、调色板（固定/自动量化）、
抖动、alpha 模式、自动裁切、色键等多参数精细控制，输出到独立目录（不覆盖原图）。
像素块大小 N：整体尺寸不变，每个色块占 N×N 个输出像素（同色），
处理在网格（输出尺寸/N）上进行，最后最近邻放大回输出尺寸。
"""

import os

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QProgressBar, QGroupBox, QSpinBox, QCheckBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit
from core.base_worker import BaseWorker

from pixelizer import (
    collect_images, pixelize_image, build_contact_sheet,
    build_shared_palette, compute_crop_boxes, resolve_palette,
    _parse_color_keys,
)


class PixelizerWorker(BaseWorker):
    """图片像素化工作线程（异步，禁止在 run 中操作 UI）"""

    def __init__(self, input_dir: str, output_dir: str,
                 width: int, height: int, extra_sizes: list[int],
                 palette_hex: list[str], palette_label: str,
                 alpha_threshold: int = 128, edge_iters: int = 2,
                 color_keys=None, color_key_tolerance: int = 50,
                 dither: str = "none", alpha_mode: str = "hard",
                 autocrop: str = "none", crop_margin: int = 6,
                 quantize: str = "off", quantize_colors: int = 16,
                 contact_scale: int = 8, pixel_size: int = 1):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.width = width
        self.height = height
        self.extra_sizes = extra_sizes
        self.palette_hex = palette_hex
        self.palette_label = palette_label
        self.alpha_threshold = alpha_threshold
        self.edge_iters = edge_iters
        self.color_keys = color_keys
        self.color_key_tolerance = color_key_tolerance
        self.dither = dither
        self.alpha_mode = alpha_mode
        self.autocrop = autocrop
        self.crop_margin = crop_margin
        self.quantize = quantize
        self.quantize_colors = quantize_colors
        self.contact_scale = contact_scale
        self.pixel_size = pixel_size

    def run(self):
        """执行批量像素化，输出到 <输出目录>/<调色板名>_<宽>x<高>/"""
        import json

        files = collect_images(self.input_dir, exclude=self.output_dir)
        total = len(files)
        if total == 0:
            self.signals.log.emit("未找到图片文件")
            self.signals.finished.emit({'success': True, 'processed': 0})
            return

        self.signals.log.emit(f"找到 {total} 张图片")

        # 共享调色板（自动量化）与裁切框
        palette_hex, label = self.palette_hex, self.palette_label
        if self.quantize != "off":
            palette_hex, label = build_shared_palette(
                files, self.quantize, self.quantize_colors,
                self.color_keys, self.color_key_tolerance)
            self.signals.log.emit(f"自动量化调色板: {label} 共 {len(palette_hex)} 色")
        crop_boxes = compute_crop_boxes(
            files, self.autocrop, self.crop_margin,
            self.color_keys, self.color_key_tolerance)
        if crop_boxes is not None:
            self.signals.log.emit(
                f"自动裁切: {'整批共享边框' if self.autocrop == 'batch' else '每帧独立'}")

        sizes = [(self.width, self.height)]
        if self.extra_sizes and self.width > 0 and self.height > 0 and self.width == self.height:
            sizes += [(s, s) for s in self.extra_sizes]
        elif self.extra_sizes:
            self.signals.log.emit("附加尺寸仅在显式正方形尺寸时生效（宽=高>0），已忽略")

        ok, fail = 0, 0
        for idx, f in enumerate(files):
            if self._stop_flag:
                break
            for (w, h) in sizes:
                tag = f"{w}x{h}" if (w > 0 and h > 0) else "orig"
                if self.pixel_size > 1:
                    tag += f"_p{self.pixel_size}"
                sub = os.path.join(self.output_dir, f"{label}_{tag}")
                out_p = os.path.join(
                    sub, os.path.splitext(os.path.basename(f))[0] + ".png")
                try:
                    rep = pixelize_image(
                        f, out_p, w, h, palette_hex,
                        alpha_threshold=self.alpha_threshold,
                        edge_iters=self.edge_iters,
                        color_keys=self.color_keys,
                        color_key_tolerance=self.color_key_tolerance,
                        dither=self.dither,
                        alpha_mode=self.alpha_mode,
                        crop_box=None if crop_boxes is None else crop_boxes[f],
                        pixel_size=self.pixel_size)
                    ok += 1
                except Exception as e:
                    fail += 1
                    self.signals.log.emit(
                        f"处理失败 {os.path.basename(f)}: {e}")
            self.signals.progress.emit(idx + 1, total)

        # 写 report.json（含所用参数）+ 生成接触表（如有）
        params = {
            "size": [self.width, self.height], "pixel_size": self.pixel_size,
            "palette": label,
            "palette_hex": palette_hex,
            "alpha_threshold": self.alpha_threshold,
            "edge_iters": self.edge_iters,
            "color_keys": self.color_keys,
            "color_key_tolerance": self.color_key_tolerance,
            "dither": self.dither, "alpha_mode": self.alpha_mode,
            "autocrop": self.autocrop, "crop_margin": self.crop_margin,
            "quantize": self.quantize,
            "quantize_colors": self.quantize_colors,
        }
        for (w, h) in sizes:
            tag = f"{w}x{h}" if (w > 0 and h > 0) else "orig"
            if self.pixel_size > 1:
                tag += f"_p{self.pixel_size}"
            sub = os.path.join(self.output_dir, f"{label}_{tag}")
            with open(os.path.join(sub, "report.json"), "w",
                      encoding="utf-8") as fp:
                json.dump({"params": params, "files": []}, fp,
                          ensure_ascii=False, indent=2)
            if self.contact_scale > 0:
                build_contact_sheet(sub, scale=self.contact_scale)

        self.signals.log.emit(f"像素化完成！成功 {ok} 张，失败 {fail} 张")
        self.signals.finished.emit({'success': True, 'processed': ok})


class PixelizerPanel(BaseToolPanel):
    """图片转像素面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_dir: str = ""
        self.output_dir: str = ""
        self.worker: PixelizerWorker | None = None
        self._ratio: float | None = None  # 输入首图宽高比（锁定比例用）
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 输入/输出文件夹 ----
        io_group = QGroupBox()
        io_layout = QGridLayout(io_group)
        self.input_label = QLabel()
        io_layout.addWidget(self.input_label, 0, 0)
        self.input_entry = DragDropFolderLineEdit()
        self.input_entry.textChanged.connect(
            lambda t: setattr(self, 'input_dir', t.strip()))
        io_layout.addWidget(self.input_entry, 0, 1)
        self.input_btn = QPushButton()
        self.input_btn.clicked.connect(self._select_input)
        io_layout.addWidget(self.input_btn, 0, 2)
        self.output_label = QLabel()
        io_layout.addWidget(self.output_label, 1, 0)
        self.output_entry = DragDropFolderLineEdit()
        self.output_entry.textChanged.connect(
            lambda t: setattr(self, 'output_dir', t.strip()))
        io_layout.addWidget(self.output_entry, 1, 1)
        self.output_btn = QPushButton()
        self.output_btn.clicked.connect(self._select_output)
        io_layout.addWidget(self.output_btn, 1, 2)
        layout.addWidget(io_group)

        # ---- 尺寸 ----
        size_group = QGroupBox()
        size_layout = QGridLayout(size_group)
        self.width_label = QLabel()
        size_layout.addWidget(self.width_label, 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 4096)
        self.width_spin.setValue(0)
        self.width_spin.valueChanged.connect(
            lambda v: self._on_dim_changed("w", v))
        size_layout.addWidget(self.width_spin, 0, 1)
        self.height_label = QLabel()
        size_layout.addWidget(self.height_label, 0, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 4096)
        self.height_spin.setValue(0)
        self.height_spin.valueChanged.connect(
            lambda v: self._on_dim_changed("h", v))
        size_layout.addWidget(self.height_spin, 0, 3)
        self.lock_check = QCheckBox()
        self.lock_check.setChecked(True)
        size_layout.addWidget(self.lock_check, 0, 4)
        self.pixel_size_label = QLabel()
        size_layout.addWidget(self.pixel_size_label, 1, 0)
        self.pixel_size_spin = QSpinBox()
        self.pixel_size_spin.setRange(1, 64)
        self.pixel_size_spin.setValue(1)
        size_layout.addWidget(self.pixel_size_spin, 1, 1)
        self.extra_label = QLabel()
        size_layout.addWidget(self.extra_label, 1, 2)
        self.extra_entry = QLineEdit("")
        size_layout.addWidget(self.extra_entry, 1, 3, 1, 2)
        layout.addWidget(size_group)

        # ---- 调色板 / 量化 / 抖动 ----
        pal_group = QGroupBox()
        pal_layout = QGridLayout(pal_group)
        self.palette_label = QLabel()
        pal_layout.addWidget(self.palette_label, 0, 0)
        self.palette_combo = QComboBox()
        self.palette_combo.addItems(["gray8", "sweetie16", "custom"])
        self.palette_combo.currentTextChanged.connect(self._on_palette_changed)
        pal_layout.addWidget(self.palette_combo, 0, 1)
        self.custom_palette_entry = QLineEdit("")
        self.custom_palette_entry.setEnabled(False)
        pal_layout.addWidget(self.custom_palette_entry, 0, 2, 1, 2)
        self.quantize_label = QLabel()
        pal_layout.addWidget(self.quantize_label, 1, 0)
        self.quantize_combo = QComboBox()
        self.quantize_combo.addItem("off", "off")
        self.quantize_combo.addItem("median_cut", "median_cut")
        self.quantize_combo.addItem("octree", "octree")
        self.quantize_combo.currentIndexChanged.connect(self._on_quantize_changed)
        pal_layout.addWidget(self.quantize_combo, 1, 1)
        self.colors_label = QLabel()
        pal_layout.addWidget(self.colors_label, 1, 2)
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(4, 256)
        self.colors_spin.setValue(16)
        self.colors_spin.setEnabled(False)
        pal_layout.addWidget(self.colors_spin, 1, 3)
        self.dither_label = QLabel()
        pal_layout.addWidget(self.dither_label, 2, 0)
        self.dither_combo = QComboBox()
        self.dither_combo.addItem("none", "none")
        self.dither_combo.addItem("Floyd-Steinberg", "floyd")
        self.dither_combo.addItem("ordered (Bayer)", "ordered")
        pal_layout.addWidget(self.dither_combo, 2, 1, 1, 3)
        layout.addWidget(pal_group)

        # ---- 高级参数 ----
        adv_group = QGroupBox()
        adv_layout = QGridLayout(adv_group)
        self.alpha_mode_label = QLabel()
        adv_layout.addWidget(self.alpha_mode_label, 0, 0)
        self.alpha_mode_combo = QComboBox()
        self.alpha_mode_combo.addItem("hard", "hard")
        self.alpha_mode_combo.addItem("keep", "keep")
        adv_layout.addWidget(self.alpha_mode_combo, 0, 1)
        self.alpha_label = QLabel()
        adv_layout.addWidget(self.alpha_label, 0, 2)
        self.alpha_spin = QSpinBox()
        self.alpha_spin.setRange(0, 255)
        self.alpha_spin.setValue(128)
        adv_layout.addWidget(self.alpha_spin, 0, 3)
        self.autocrop_label = QLabel()
        adv_layout.addWidget(self.autocrop_label, 1, 0)
        self.autocrop_combo = QComboBox()
        self.autocrop_combo.addItem("none", "none")
        self.autocrop_combo.addItem("batch", "batch")
        self.autocrop_combo.addItem("frame", "frame")
        self.autocrop_combo.currentIndexChanged.connect(self._on_autocrop_changed)
        adv_layout.addWidget(self.autocrop_combo, 1, 1)
        self.margin_label = QLabel()
        adv_layout.addWidget(self.margin_label, 1, 2)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 20)
        self.margin_spin.setValue(6)
        self.margin_spin.setEnabled(False)
        adv_layout.addWidget(self.margin_spin, 1, 3)
        self.edge_label = QLabel()
        adv_layout.addWidget(self.edge_label, 2, 0)
        self.edge_spin = QSpinBox()
        self.edge_spin.setRange(0, 8)
        self.edge_spin.setValue(2)
        adv_layout.addWidget(self.edge_spin, 2, 1)
        self.key_label = QLabel()
        adv_layout.addWidget(self.key_label, 2, 2)
        self.key_entry = QLineEdit("")
        adv_layout.addWidget(self.key_entry, 2, 3)
        self.tol_label = QLabel()
        adv_layout.addWidget(self.tol_label, 3, 0)
        self.tol_spin = QSpinBox()
        self.tol_spin.setRange(0, 255)
        self.tol_spin.setValue(50)
        adv_layout.addWidget(self.tol_spin, 3, 1)
        self.contact_label = QLabel()
        adv_layout.addWidget(self.contact_label, 3, 2)
        self.contact_spin = QSpinBox()
        self.contact_spin.setRange(0, 16)
        self.contact_spin.setValue(8)
        adv_layout.addWidget(self.contact_spin, 3, 3)
        layout.addWidget(adv_group)

        # ---- 操作区 ----
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.start_btn.clicked.connect(self._start)
        action_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton()
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        action_layout.addWidget(self.stop_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        action_layout.addWidget(self.status_label)
        layout.addLayout(action_layout)

        # ---- 日志区 ----
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    # ---------- 语言切换 ----------

    def retranslate_ui(self):
        self.input_label.setText(self.tr("select_input"))
        self.output_label.setText(self.tr("output_dir"))
        self.input_btn.setText(self.tr("browse"))
        self.output_btn.setText(self.tr("browse"))
        self.input_entry.setPlaceholderText(self.tr("px_placeholder_input"))
        self.output_entry.setPlaceholderText(self.tr("px_placeholder_output"))
        self.width_label.setText(self.tr("px_width"))
        self.height_label.setText(self.tr("px_height"))
        self.lock_check.setText(self.tr("px_lock_ratio"))
        self.width_spin.setToolTip(self.tr("px_size_tip"))
        self.height_spin.setToolTip(self.tr("px_size_tip"))
        self.pixel_size_label.setText(self.tr("px_pixel_size"))
        self.pixel_size_spin.setToolTip(self.tr("px_pixel_size_tip"))
        self.extra_label.setText(self.tr("px_extra_sizes"))
        self.extra_entry.setPlaceholderText("128 / 128,96")
        self.palette_label.setText(self.tr("px_palette"))
        self.custom_palette_entry.setPlaceholderText(
            self.tr("px_custom_palette_ph"))
        self.quantize_label.setText(self.tr("px_quantize"))
        self.colors_label.setText(self.tr("px_quantize_colors"))
        self.dither_label.setText(self.tr("px_dither"))
        self.alpha_mode_label.setText(self.tr("px_alpha_mode"))
        self.alpha_label.setText(self.tr("px_alpha_threshold"))
        self.autocrop_label.setText(self.tr("px_autocrop"))
        self.margin_label.setText(self.tr("px_crop_margin"))
        self.edge_label.setText(self.tr("px_edge_iters"))
        self.key_label.setText(self.tr("px_color_key"))
        self.key_entry.setPlaceholderText("0,0,0;255,255,255")
        self.tol_label.setText(self.tr("px_color_key_tol"))
        self.contact_label.setText(self.tr("px_contact_scale"))
        self.start_btn.setText(self.tr("px_start"))
        self.stop_btn.setText(self.tr("stop"))

    # ---------- 事件 ----------

    def _on_palette_changed(self, name: str):
        """切换调色板时启用/禁用自定义输入框"""
        self.custom_palette_entry.setEnabled(
            name == "custom" and self.quantize_combo.currentData() == "off")

    def _on_quantize_changed(self):
        """开启自动量化时禁用固定调色板；关闭时恢复"""
        on = self.quantize_combo.currentData() != "off"
        self.colors_spin.setEnabled(on)
        self.palette_combo.setEnabled(not on)
        self.custom_palette_entry.setEnabled(
            not on and self.palette_combo.currentText() == "custom")

    def _on_autocrop_changed(self):
        self.margin_spin.setEnabled(
            self.autocrop_combo.currentData() != "none")

    def _on_dim_changed(self, which: str, value: int):
        """锁定比例：改宽自动算高（按输入首图比例），反之亦然；0 = 原图尺寸"""
        if self.lock_check.isChecked() and self._ratio:
            if which == "w":
                self.height_spin.blockSignals(True)
                self.height_spin.setValue(0 if value == 0
                                          else max(0, round(value / self._ratio)))
                self.height_spin.blockSignals(False)
            else:
                self.width_spin.blockSignals(True)
                self.width_spin.setValue(0 if value == 0
                                         else max(0, round(value * self._ratio)))
                self.width_spin.blockSignals(False)

    def _select_input(self):
        folder = self.browse_folder(self.tr("select_input"))
        if folder:
            self.input_dir = folder
            self.input_entry.setText(folder)
            if not self.output_dir:
                default_out = os.path.join(folder, "pixelized")
                self.output_entry.setText(default_out)
                self.output_dir = default_out
            self._update_ratio(folder)

    def _update_ratio(self, folder: str):
        """读取输入目录首张图的宽高比（锁定比例用）"""
        self._ratio = None
        try:
            from PIL import Image
            files = collect_images(folder)
            if files:
                img = Image.open(files[0])
                self._ratio = img.width / img.height
        except Exception:
            self._ratio = None

    def _select_output(self):
        folder = self.browse_folder(self.tr("select_output_dir"))
        if folder:
            self.output_dir = folder
            self.output_entry.setText(folder)

    def _start(self):
        if not self.input_dir:
            self.show_error(self.tr("error_title"),
                            self.tr("error_no_input"))
            return

        # 固定调色板（自动量化时忽略）
        palette_hex, label = [], "auto"
        if self.quantize_combo.currentData() == "off":
            combo = self.palette_combo.currentText()
            if combo == "custom":
                custom = self.custom_palette_entry.text().strip()
                if not custom:
                    self.show_error(self.tr("error_title"),
                                    self.tr("px_error_palette"))
                    return
                palette_hex, label = resolve_palette(custom)
            else:
                palette_hex, label = resolve_palette(combo)

        # 附加尺寸（逗号分隔，可留空）
        extra_sizes = []
        if self.extra_entry.text().strip():
            try:
                extra_sizes = [int(s) for s in
                               self.extra_entry.text().split(",") if s.strip()]
                if any(s <= 0 for s in extra_sizes):
                    raise ValueError
            except ValueError:
                self.show_error(self.tr("error_title"),
                                self.tr("px_error_size"))
                return

        # 色键抠除（留空 = 关闭；分号分隔多键）
        color_keys = None
        if self.key_entry.text().strip():
            try:
                color_keys = _parse_color_keys(self.key_entry.text())
            except ValueError as e:
                self.show_error(self.tr("error_title"), str(e))
                return

        output = self.output_dir or os.path.join(self.input_dir, "pixelized")
        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = PixelizerWorker(
            self.input_dir, output,
            self.width_spin.value(), self.height_spin.value(),
            extra_sizes, palette_hex, label,
            alpha_threshold=self.alpha_spin.value(),
            edge_iters=self.edge_spin.value(),
            color_keys=color_keys,
            color_key_tolerance=self.tol_spin.value(),
            dither=self.dither_combo.currentData(),
            alpha_mode=self.alpha_mode_combo.currentData(),
            autocrop=self.autocrop_combo.currentData(),
            crop_margin=self.margin_spin.value(),
            quantize=self.quantize_combo.currentData(),
            quantize_colors=self.colors_spin.value(),
            contact_scale=self.contact_spin.value(),
            pixel_size=self.pixel_size_spin.value())
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self.worker)

    def _stop(self):
        if self.worker:
            self.worker.stop()

    def _on_progress(self, cur, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(cur)

    def _on_log(self, msg):
        self.log(msg)

    def _on_finished(self, result):
        self.set_processing(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            self.status_label.setText(
                f"完成! {result.get('processed', 0)} 张")
