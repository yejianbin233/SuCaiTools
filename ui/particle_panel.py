"""
GIF粒子提取器面板

从GIF拆分后的帧序列中，通过绘制矩形遮罩批量提取粒子图片。
使用 QLabel 显示参考帧，重写鼠标事件实现遮罩绘制交互。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog,
    QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThreadPool, QRect, QPoint, Signal
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QFont, QMouseEvent
)

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit, DragDropLineEdit
from core.base_worker import BaseWorker

# 遮罩颜色调色板（与旧版 particle_extractor_gui.py 保持一致）
MASK_COLORS = [
    QColor('#FF6B6B'), QColor('#4ECDC4'), QColor('#45B7D1'),
    QColor('#96CEB4'), QColor('#FFEAA7'), QColor('#DDA0DD'),
    QColor('#F7DC6F'), QColor('#BB8FCE'), QColor('#85C1E9'),
    QColor('#F8C471'), QColor('#82E0AA'), QColor('#F1948A'),
]
MASK_NORMAL_WIDTH = 2
MASK_SELECTED_WIDTH = 3
MASK_DRAWING_COLOR = QColor('#FFFF44')
MIN_MASK_SIZE = 5


class ImageLabel(QLabel):
    """可绘制遮罩的图片显示组件

    支持鼠标拖拽绘制矩形遮罩、点击选中遮罩、右键删除遮罩。
    所有遮罩坐标自动在显示坐标和原始图像坐标之间转换。
    """

    # 信号：遮罩变更时通知外部更新列表
    masks_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #e8e8e8; border: 1px solid #ccc;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 原始图片
        self.original_pixmap: QPixmap | None = None
        self.original_size: tuple[int, int] = (0, 0)

        # 显示参数
        self.scale_factor: float = 1.0
        self.offset_x: int = 0
        self.offset_y: int = 0

        # 遮罩数据
        self.masks: list[dict] = []
        self.next_mask_id: int = 1
        self.selected_mask_idx: int = -1

        # 交互状态
        self.is_drawing: bool = False
        self.is_moving: bool = False
        self.draw_start: QPoint | None = None
        self.draw_current: QPoint | None = None
        self.move_offset: QPoint | None = None

        # 鼠标追踪
        self.setMouseTracking(True)

    # ---------- 图片加载 ----------

    def load_image(self, path: str):
        """加载并显示参考帧图片"""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self.original_pixmap = pixmap
        self.original_size = (pixmap.width(), pixmap.height())
        self.masks.clear()
        self.next_mask_id = 1
        self.selected_mask_idx = -1
        self._update_display()
        self.masks_changed.emit()
        return True

    def _update_display(self):
        """更新显示：缩放图片并重绘"""
        if not self.original_pixmap:
            return

        # 计算缩放比（适应label大小，保持宽高比）
        label_w = self.width() - 20
        label_h = self.height() - 20
        if label_w < 10 or label_h < 10:
            return

        img_w, img_h = self.original_size
        self.scale_factor = min(label_w / img_w, label_h / img_h)

        # 缩放pixmap
        display_w = max(1, int(img_w * self.scale_factor))
        display_h = max(1, int(img_h * self.scale_factor))
        scaled = self.original_pixmap.scaled(
            display_w, display_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

        # 居中偏移
        self.offset_x = (self.width() - display_w) // 2
        self.offset_y = (self.height() - display_h) // 2

        # 绘制到带遮罩的pixmap
        result = QPixmap(self.width(), self.height())
        result.fill(QColor('#e8e8e8'))
        painter = QPainter(result)
        painter.drawPixmap(self.offset_x, self.offset_y, scaled)

        # 绘制所有遮罩
        for i, mask in enumerate(self.masks):
            is_selected = (i == self.selected_mask_idx)
            color = MASK_COLORS[i % len(MASK_COLORS)]
            width = MASK_SELECTED_WIDTH if is_selected else MASK_NORMAL_WIDTH

            # 原始坐标→显示坐标
            cx1 = int(mask['x'] * self.scale_factor) + self.offset_x
            cy1 = int(mask['y'] * self.scale_factor) + self.offset_y
            cx2 = cx1 + max(1, int(mask['width'] * self.scale_factor))
            cy2 = cy1 + max(1, int(mask['height'] * self.scale_factor))

            pen = QPen(color, width)
            painter.setPen(pen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
            painter.drawRect(cx1, cy1, cx2 - cx1, cy2 - cy1)

            # 标签
            label = mask['label']
            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            painter.drawText(cx1 + 4, cy1 + 14, label)
            painter.setPen(QPen(color, 1))
            painter.drawText(cx1 + 3, cy1 + 13, label)

        # 正在绘制的预览矩形
        if self.is_drawing and self.draw_start and self.draw_current:
            pen = QPen(MASK_DRAWING_COLOR, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 255, 68, 30))
            x1, y1 = self.draw_start.x(), self.draw_start.y()
            x2, y2 = self.draw_current.x(), self.draw_current.y()
            painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

        painter.end()
        self.setPixmap(result)

    # ---------- 坐标转换 ----------

    def _canvas_to_original(self, cx: int, cy: int) -> tuple[int, int]:
        """显示坐标→原始图像坐标"""
        ox = (cx - self.offset_x) / self.scale_factor if self.scale_factor > 0 else 0
        oy = (cy - self.offset_y) / self.scale_factor if self.scale_factor > 0 else 0
        img_w, img_h = self.original_size
        return (max(0, min(int(ox), img_w - 1)),
                max(0, min(int(oy), img_h - 1)))

    def _find_mask_at(self, cx: int, cy: int) -> int:
        """查找显示坐标处的遮罩索引，无则返回-1"""
        ox, oy = self._canvas_to_original(cx, cy)
        for i in range(len(self.masks) - 1, -1, -1):
            m = self.masks[i]
            if m['x'] <= ox <= m['x'] + m['width'] and m['y'] <= oy <= m['y'] + m['height']:
                return i
        return -1

    # ---------- 鼠标事件 ----------

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下：开始绘制或选中遮罩"""
        if not self.original_pixmap:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            clicked_idx = self._find_mask_at(event.position().x(), event.position().y())
            if clicked_idx >= 0:
                # 点击遮罩→选中并准备移动
                self.selected_mask_idx = clicked_idx
                self.is_moving = True
                self.is_drawing = False
                ox, oy = self._canvas_to_original(
                    int(event.position().x()), int(event.position().y()))
                m = self.masks[clicked_idx]
                self.move_offset = QPoint(ox - m['x'], oy - m['y'])
            else:
                # 点击空白→开始绘制新遮罩
                self.selected_mask_idx = -1
                self.is_drawing = True
                self.is_moving = False
                self.draw_start = QPoint(int(event.position().x()), int(event.position().y()))
                self.draw_current = self.draw_start
            self._update_display()
            self.masks_changed.emit()

        elif event.button() == Qt.MouseButton.RightButton:
            # 右键删除
            if self.is_drawing:
                self.is_drawing = False
            clicked_idx = self._find_mask_at(event.position().x(), event.position().y())
            if clicked_idx >= 0:
                del self.masks[clicked_idx]
                self.selected_mask_idx = -1
            self.is_moving = False
            self._update_display()
            self.masks_changed.emit()

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动：更新绘制预览或移动遮罩"""
        if not self.original_pixmap:
            return

        if self.is_drawing:
            self.draw_current = QPoint(int(event.position().x()), int(event.position().y()))
            self._update_display()

        elif self.is_moving and self.selected_mask_idx >= 0 and self.move_offset:
            ox, oy = self._canvas_to_original(
                int(event.position().x()), int(event.position().y()))
            m = self.masks[self.selected_mask_idx]
            new_x = ox - self.move_offset.x()
            new_y = oy - self.move_offset.y()
            # 边界钳制
            img_w, img_h = self.original_size
            new_x = max(0, min(new_x, img_w - m['width']))
            new_y = max(0, min(new_y, img_h - m['height']))
            m['x'] = new_x
            m['y'] = new_y
            self._update_display()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放：完成绘制或移动"""
        if not self.original_pixmap:
            return

        if self.is_drawing and self.draw_start and self.draw_current:
            self.is_drawing = False
            # 计算遮罩（原始坐标）
            ox1, oy1 = self._canvas_to_original(
                self.draw_start.x(), self.draw_start.y())
            ox2, oy2 = self._canvas_to_original(
                self.draw_current.x(), self.draw_current.y())
            x, y = min(ox1, ox2), min(oy1, oy2)
            w, h = abs(ox2 - ox1), abs(oy2 - oy1)
            if w >= MIN_MASK_SIZE and h >= MIN_MASK_SIZE:
                mask = {
                    'id': self.next_mask_id,
                    'label': f"mask_{self.next_mask_id:02d}",
                    'x': x, 'y': y, 'width': w, 'height': h
                }
                self.masks.append(mask)
                self.next_mask_id += 1
                self.selected_mask_idx = len(self.masks) - 1
            self.draw_start = None
            self.draw_current = None
            self._update_display()
            self.masks_changed.emit()

        elif self.is_moving:
            self.is_moving = False

    def resizeEvent(self, event):
        """窗口大小变化时重新缩放图片"""
        super().resizeEvent(event)
        if self.original_pixmap:
            self._update_display()


class ParticlePanel(BaseToolPanel):
    """GIF粒子提取器面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames_dir: str = ""
        self.ref_image_path: str = ""
        self.worker: BaseWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        """创建界面布局"""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ---- 顶部：文件夹和参考帧选择 ----
        top_layout = QGridLayout()

        self.frames_label = QLabel()
        top_layout.addWidget(self.frames_label, 0, 0)
        self.frames_entry = DragDropFolderLineEdit()
        self.frames_entry.textChanged.connect(
            lambda t: setattr(self, 'frames_dir', t.strip()))
        top_layout.addWidget(self.frames_entry, 0, 1)
        self.frames_btn = QPushButton()
        self.frames_btn.clicked.connect(self._select_frames_dir)
        top_layout.addWidget(self.frames_btn, 0, 2)

        self.ref_label = QLabel()
        top_layout.addWidget(self.ref_label, 1, 0)
        self.ref_entry = QLineEdit()
        self.ref_entry.setReadOnly(True)
        top_layout.addWidget(self.ref_entry, 1, 1)
        self.ref_btn = QPushButton()
        self.ref_btn.clicked.connect(self._select_ref_image)
        top_layout.addWidget(self.ref_btn, 1, 2)
        self.load_btn = QPushButton()
        self.load_btn.clicked.connect(self._load_ref_image)
        self.load_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        top_layout.addWidget(self.load_btn, 1, 3)

        layout.addLayout(top_layout)

        # ---- 中部：图片显示 + 遮罩列表 ----
        work_layout = QHBoxLayout()

        # 左侧：可绘制遮罩的图片显示
        self.image_label = ImageLabel()
        work_layout.addWidget(self.image_label, stretch=3)

        # 右侧：遮罩列表面板
        right_panel = QGroupBox()
        right_layout = QVBoxLayout(right_panel)
        self.mask_list_label = QLabel()
        self.mask_list_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.mask_list_label)

        self.mask_list = QListWidget()
        self.mask_list.currentRowChanged.connect(self._on_mask_selected)
        right_layout.addWidget(self.mask_list)

        # 按钮垂直排列，确保文字完整显示
        self.delete_mask_btn = QPushButton()
        self.delete_mask_btn.clicked.connect(self._delete_mask)
        self.delete_mask_btn.setMinimumWidth(180)
        right_layout.addWidget(self.delete_mask_btn)

        self.clear_masks_btn = QPushButton()
        self.clear_masks_btn.clicked.connect(self._clear_masks)
        self.clear_masks_btn.setMinimumWidth(180)
        right_layout.addWidget(self.clear_masks_btn)

        self.save_masks_btn = QPushButton()
        self.save_masks_btn.clicked.connect(self._save_masks)
        self.save_masks_btn.setMinimumWidth(180)
        right_layout.addWidget(self.save_masks_btn)

        self.load_masks_btn = QPushButton()
        self.load_masks_btn.clicked.connect(self._load_masks)
        self.load_masks_btn.setMinimumWidth(180)
        right_layout.addWidget(self.load_masks_btn)

        right_panel.setFixedWidth(220)
        work_layout.addWidget(right_panel)

        layout.addLayout(work_layout, stretch=1)

        # ---- 底部：操作和日志 ----
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.start_btn.clicked.connect(self._start_extraction)
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

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(120)
        layout.addWidget(self.log_area)

        # 连接图片遮罩变更信号
        self.image_label.masks_changed.connect(self._update_mask_list)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    # ---------- 语言切换 ----------

    def retranslate_ui(self):
        """更新UI文本"""
        self.frames_label.setText(self.tr("select_frames_folder"))
        self.frames_btn.setText(self.tr("browse"))
        self.ref_label.setText(self.tr("select_ref_frame"))
        self.ref_btn.setText(self.tr("browse"))
        self.load_btn.setText(self.tr("load_ref_frame"))
        self.mask_list_label.setText(self.tr("masks_panel"))
        self.delete_mask_btn.setText(self.tr("btn_delete_mask"))
        self.clear_masks_btn.setText(self.tr("btn_clear_masks"))
        self.save_masks_btn.setText(self.tr("btn_save_masks"))
        self.load_masks_btn.setText(self.tr("btn_load_masks"))
        self.start_btn.setText(self.tr("start_extract"))
        self.stop_btn.setText(self.tr("stop"))

    # ---------- 文件操作 ----------

    def _select_frames_dir(self):
        """选择帧序列文件夹"""
        folder = self.browse_folder(self.tr("select_frames_folder"))
        if folder:
            self.frames_entry.setText(folder)

    def _select_ref_image(self):
        """选择参考帧图片"""
        path = self.browse_file(
            self.tr("select_ref_frame"),
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)")
        if path:
            self.ref_entry.setText(path)

    def _load_ref_image(self):
        """加载参考帧到图片显示组件"""
        path = self.ref_entry.text().strip()
        if not path or not os.path.isfile(path):
            self.show_error(self.tr("error_title"), self.tr("pe_error_no_ref_frame"))
            return
        if self.image_label.load_image(path):
            self.ref_image_path = path
            self.log(f"已加载参考帧: {os.path.basename(path)} "
                     f"({self.image_label.original_size[0]}×"
                     f"{self.image_label.original_size[1]})")
            self.status_label.setText(self.tr("status_ready"))
        else:
            self.show_error(self.tr("error_title"), "无法加载图片文件")

    # ---------- 遮罩管理 ----------

    def _delete_mask(self):
        """删除选中遮罩"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            mask = self.image_label.masks.pop(idx)
            self.log(f"已删除遮罩 {mask['label']}")
            self.image_label.selected_mask_idx = -1
            self.image_label._update_display()
            self._update_mask_list()

    def _clear_masks(self):
        """清空所有遮罩"""
        count = len(self.image_label.masks)
        self.image_label.masks.clear()
        self.image_label.next_mask_id = 1
        self.image_label.selected_mask_idx = -1
        self.image_label._update_display()
        self.log(f"已清空 {count} 个遮罩")
        self._update_mask_list()

    def _on_mask_selected(self, idx: int):
        """遮罩列表选中→同步到图片显示"""
        self.image_label.selected_mask_idx = idx
        self.image_label._update_display()

    def _update_mask_list(self):
        """更新遮罩列表（从image_label同步）"""
        self.mask_list.clear()
        for i, mask in enumerate(self.image_label.masks):
            text = (f"{mask['label']}  ({mask['x']},{mask['y']}) "
                    f"{mask['width']}×{mask['height']}")
            item = QListWidgetItem(text)
            color = MASK_COLORS[(mask['id'] - 1) % len(MASK_COLORS)]
            item.setForeground(color)
            self.mask_list.addItem(item)
            if i == self.image_label.selected_mask_idx:
                self.mask_list.setCurrentRow(i)

    # ---------- 遮罩保存/加载 ----------

    def _save_masks(self):
        """保存遮罩到JSON文件"""
        if not self.image_label.masks:
            self.show_warning(self.tr("warning_title"), self.tr("pe_error_no_masks"))
            return
        path = self.browse_save_file(self.tr("save_masks_title"), "JSON文件 (*.json)")
        if not path:
            return
        try:
            from particle_extractor import ParticleExtractor
            from particle_extractor import MaskDef
            maskdefs = [MaskDef(**m) for m in self.image_label.masks]
            ParticleExtractor.save_masks_to_file(
                maskdefs, path,
                reference_image_path=self.ref_image_path,
                image_size=self.image_label.original_size)
            self.log(f"遮罩已保存: {path}")
        except Exception as e:
            self.show_error(self.tr("error_title"), f"保存失败: {e}")

    def _load_masks(self):
        """从JSON文件加载遮罩"""
        path = self.browse_file(self.tr("load_masks_title"), "JSON文件 (*.json)")
        if not path:
            return
        try:
            from particle_extractor import ParticleExtractor
            maskdefs, metadata = ParticleExtractor.load_masks_from_file(path)
            self.image_label.masks = [
                {'id': m.id, 'label': m.label,
                 'x': m.x, 'y': m.y, 'width': m.width, 'height': m.height}
                for m in maskdefs
            ]
            self.image_label.next_mask_id = max((m['id'] for m in self.image_label.masks), default=0) + 1
            self.image_label.selected_mask_idx = -1
            self.image_label._update_display()
            self._update_mask_list()
            self.log(f"已加载 {len(maskdefs)} 个遮罩: {path}")
        except Exception as e:
            self.show_error(self.tr("error_title"), f"加载失败: {e}")

    # ---------- 批量提取 ----------

    def _start_extraction(self):
        """开始批量提取粒子"""
        if not self.frames_dir:
            self.show_error(self.tr("error_title"), self.tr("pe_error_no_frames"))
            return
        if not self.image_label.masks:
            self.show_error(self.tr("error_title"), self.tr("pe_error_no_masks"))
            return

        output_dir = os.path.join(self.frames_dir, "particles")

        # 确认
        try:
            from particle_extractor import ParticleExtractor
            ext = ParticleExtractor()
            frame_files = ext.scan_frame_files(self.frames_dir)
            total = len(frame_files)
        except Exception as e:
            self.show_error(self.tr("error_title"), str(e))
            return

        # 使用自定义按钮确保文本正确显示
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(self.tr("pe_confirm_extract_title"))
        msg_box.setText(self.tr("pe_confirm_extract").format(
            mask_count=len(self.image_label.masks), total_frames=total))
        msg_box.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg_box.addButton(self.tr("confirm_yes"), QMessageBox.ButtonRole.YesRole)
        no_btn = msg_box.addButton(self.tr("confirm_no"), QMessageBox.ButtonRole.NoRole)
        msg_box.exec()
        if msg_box.clickedButton() != yes_btn:
            return

        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        # 创建提取Worker — 将dict转换为MaskDef对象
        from particle_extractor import MaskDef
        maskdefs = [MaskDef(**m) for m in self.image_label.masks]

        class ExtractWorker(BaseWorker):
            def __init__(slf):
                super().__init__()
                slf.extractor = ParticleExtractor(
                    log_callback=lambda msg: slf.signals.log.emit(msg))

            def run(slf):
                try:
                    result = slf.extractor.extract_particles(
                        maskdefs, self.frames_dir, output_dir,
                        progress_callback=lambda c, t:
                        slf.signals.progress.emit(c, t))
                    slf.signals.finished.emit(result)
                except Exception as e:
                    slf.signals.error.emit(str(e))
                    slf.signals.finished.emit({'success': False, 'error': str(e)})

        self.worker = ExtractWorker()
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self.worker)

    def _stop(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)

    def _on_progress(self, cur, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(cur)
        self.status_label.setText(
            self.tr("pe_status_extracting").format(current=cur, total=total))

    def _on_log(self, msg):
        self.log(msg)

    def _on_error(self, err):
        self.log(f"[错误] {err}")

    def _on_finished(self, result):
        self.set_processing(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            frames = result.get('frame_count', 0)
            masks_n = result.get('mask_count', 0)
            self.status_label.setText(
                self.tr("pe_status_complete").format(frames=frames, masks=masks_n))
            self.progress_bar.setValue(self.progress_bar.maximum())
            QMessageBox.information(
                self, self.tr("info_title"),
                f"提取完成! {frames}帧 × {masks_n}遮罩\n"
                f"输出目录: {result.get('output_dir', '')}")
        else:
            self.status_label.setText("提取失败")
