"""
GIF粒子提取器面板

从GIF拆分后的帧序列中，通过绘制矩形遮罩批量提取粒子图片。
使用 QLabel 显示参考帧，重写鼠标事件实现遮罩绘制交互。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QSpinBox,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog,
    QListWidget, QListWidgetItem, QSplitter,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThreadPool, QRect, QPoint, Signal, QTimer, QSize
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QFont, QMouseEvent, QIcon
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
        self.is_resizing: bool = False
        self.resize_edge: str = ""       # top/bottom/left/right/topleft/topright/bottomleft/bottomright
        self.resize_anchor: tuple = (0, 0, 0, 0)  # 对角锚点 (x,y,w,h) 原始坐标
        self.draw_start: QPoint | None = None
        self.draw_current: QPoint | None = None
        self.move_offset: QPoint | None = None

        # 鼠标追踪（用于边缘检测显示光标）
        self.setMouseTracking(True)
        self._edge_threshold = 8  # 边缘检测像素阈值

    # ---------- 图片加载 ----------

    def load_image(self, path: str):
        """加载参考帧图片（会清空已有遮罩）"""
        if not self._load_pixmap(path):
            return False
        self.masks.clear()
        self.next_mask_id = 1
        self.selected_mask_idx = -1
        self._update_display()
        self.masks_changed.emit()
        return True

    def switch_image(self, path: str):
        """切换参考帧图片（保留已有遮罩）"""
        if not self._load_pixmap(path):
            return False
        self._update_display()
        return True

    def _load_pixmap(self, path: str):
        """加载pixmap底层逻辑"""
        import os as _os
        path = _os.path.normpath(path)
        # 缓存原始pixmap以在加载失败时保持上一次成功状态
        prev_pixmap = self.original_pixmap
        prev_size = self.original_size
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.original_pixmap = pixmap
                self.original_size = (pixmap.width(), pixmap.height())
                return True
            # QPixmap失败时尝试PIL
            from PIL import Image
            import io as _io
            try:
                img = Image.open(path)
                img = img.convert('RGBA')
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                pixmap = QPixmap()
                pixmap.loadFromData(buf.read())
            except Exception:
                pass
            if not pixmap.isNull():
                self.original_pixmap = pixmap
                self.original_size = (pixmap.width(), pixmap.height())
                return True
            # 全部失败，恢复旧状态
            print(f"[粒子面板] 无法加载: {_os.path.basename(path)}")
            self.original_pixmap = prev_pixmap
            self.original_size = prev_size
            return False
        except Exception:
            self.original_pixmap = prev_pixmap
            self.original_size = prev_size
            return False

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

            # 所有遮罩都显示中心十字
            center_cx = cx1 + (cx2 - cx1) // 2
            center_cy = cy1 + (cy2 - cy1) // 2

            if is_selected:
                # 选中遮罩：中心十字 + 延伸至图片边界的虚线（对齐辅助线）
                pen_center = QPen(QColor('#ff4444'), 2)
                pen_guide = QPen(QColor('#ff4444'), 1, Qt.PenStyle.DashLine)
                pen_guide.setDashPattern([4, 6])
            else:
                # 未选中：淡色小十字
                pen_center = QPen(QColor(color.red(), color.green(), color.blue(), 120), 1)
                pen_guide = QPen(Qt.PenStyle.NoPen)

            # 水平辅助线（延伸到图片边界）
            if is_selected:
                result_w = result.width()
                result_h = result.height()
                painter.setPen(pen_guide)
                painter.drawLine(0, center_cy, result_w, center_cy)
                painter.drawLine(center_cx, 0, center_cx, result_h)

            # 中心十字（所有遮罩都画，选中更突出）
            cross_size = 10 if is_selected else 6
            painter.setPen(pen_center)
            painter.drawLine(
                center_cx - cross_size, center_cy,
                center_cx + cross_size, center_cy)
            painter.drawLine(
                center_cx, center_cy - cross_size,
                center_cx, center_cy + cross_size)

            # 选中遮罩：半宽/半高范围辅助线（灰色虚线，仅遮罩内部）
            if is_selected:
                pen_inner = QPen(QColor('#888888'), 1, Qt.PenStyle.DotLine)
                painter.setPen(pen_inner)
                painter.drawLine(center_cx, cy1, center_cx, cy2)
                painter.drawLine(cx1, center_cy, cx2, center_cy)

                # 分段蓝色虚线：从左到右/从上到下均匀划分
                seg_cols = mask.get('seg_cols', 0)
                seg_rows = mask.get('seg_rows', 0)
                if seg_cols > 1 or seg_rows > 1:
                    pen_seg = QPen(QColor('#4488ff'), 1.5, Qt.PenStyle.DashLine)
                    pen_seg.setDashPattern([6, 4])
                    painter.setPen(pen_seg)
                    mask_w = cx2 - cx1
                    mask_h = cy2 - cy1
                    # 水平分段（列）：从左到右均匀划分
                    if seg_cols > 1:
                        col_w = mask_w / seg_cols
                        for col in range(1, seg_cols):
                            x = int(cx1 + col * col_w)
                            painter.drawLine(x, cy1, x, cy2)
                    # 垂直分段（行）：从上到下均匀划分
                    if seg_rows > 1:
                        row_h = mask_h / seg_rows
                        for row in range(1, seg_rows):
                            y = int(cy1 + row * row_h)
                            painter.drawLine(cx1, y, cx2, y)

            # 选中遮罩的调整手柄（8个点：四角+四边中点）
            if is_selected:
                handle_size = 6
                handles = [
                    (cx1, cy1), (cx1 + (cx2-cx1)//2, cy1), (cx2, cy1),
                    (cx2, cy1 + (cy2-cy1)//2), (cx2, cy2),
                    (cx1 + (cx2-cx1)//2, cy2), (cx1, cy2),
                    (cx1, cy1 + (cy2-cy1)//2),
                ]
                for hx, hy in handles:
                    painter.fillRect(
                        int(hx - handle_size//2), int(hy - handle_size//2),
                        handle_size, handle_size, QColor('#ffffff'))
                    painter.setPen(QPen(color, 1))
                    painter.drawRect(
                        int(hx - handle_size//2), int(hy - handle_size//2),
                        handle_size, handle_size)

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

    def _get_resize_edge(self, mask_idx: int, cx: int, cy: int) -> str:
        """检测鼠标是否在遮罩边缘或手柄上（用于调整大小），返回边缘名称"""
        if mask_idx < 0:
            return ""
        m = self.masks[mask_idx]
        # 转换4个角的显示坐标
        dl = int(m['x'] * self.scale_factor) + self.offset_x
        dt = int(m['y'] * self.scale_factor) + self.offset_y
        dr = int((m['x'] + m['width']) * self.scale_factor) + self.offset_x
        db = int((m['y'] + m['height']) * self.scale_factor) + self.offset_y
        th = self._edge_threshold
        # 扩大检测范围（包含手柄区域）
        hh = 8  # 手柄半尺寸

        # 检查8个手柄位置
        corners = [
            (dl, dt, 'topleft'), (dl + (dr-dl)//2, dt, 'top'),
            (dr, dt, 'topright'), (dr, dt + (db-dt)//2, 'right'),
            (dr, db, 'bottomright'), (dl + (dr-dl)//2, db, 'bottom'),
            (dl, db, 'bottomleft'), (dl, dt + (db-dt)//2, 'left'),
        ]
        for hx, hy, name in corners:
            if abs(cx - hx) <= hh and abs(cy - hy) <= hh:
                return name

        # 备选：边缘线条检测（扩大范围）
        on_left = abs(cx - dl) <= th and dt - th <= cy <= db + th
        on_right = abs(cx - dr) <= th and dt - th <= cy <= db + th
        on_top = abs(cy - dt) <= th and dl - th <= cx <= dr + th
        on_bottom = abs(cy - db) <= th and dl - th <= cx <= dr + th

        if on_top and on_left: return 'topleft'
        if on_top and on_right: return 'topright'
        if on_bottom and on_left: return 'bottomleft'
        if on_bottom and on_right: return 'bottomright'
        if on_left: return 'left'
        if on_right: return 'right'
        if on_top: return 'top'
        if on_bottom: return 'bottom'
        return ""

    # ---------- 鼠标事件 ----------

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下：开始绘制/选中遮罩/调整大小"""
        if not self.original_pixmap:
            return

        mx, my = int(event.position().x()), int(event.position().y())

        if event.button() == Qt.MouseButton.LeftButton:
            # 优先检测遮罩边缘（用于调整大小）— 边缘点击可能在遮罩外部
            edge_idx = -1
            edge_name = ""
            for i in range(len(self.masks) - 1, -1, -1):
                e = self._get_resize_edge(i, mx, my)
                if e:
                    edge_idx = i
                    edge_name = e
                    break

            if edge_idx >= 0:
                # 拖拽边缘→调整大小
                self.selected_mask_idx = edge_idx
                m = self.masks[edge_idx]
                self.is_resizing = True
                self.is_moving = False
                self.is_drawing = False
                self.resize_edge = edge_name
                if 'left' in edge_name:
                    anchor_x = m['x'] + m['width']
                else:
                    anchor_x = m['x']
                if 'top' in edge_name:
                    anchor_y = m['y'] + m['height']
                else:
                    anchor_y = m['y']
                self.resize_anchor = (anchor_x, anchor_y, m['width'], m['height'])
            elif (clicked_idx := self._find_mask_at(mx, my)) >= 0:
                # 点击遮罩内部→移动
                self.selected_mask_idx = clicked_idx
                m = self.masks[clicked_idx]
                ox, oy = self._canvas_to_original(mx, my)
                self.is_moving = True
                self.is_resizing = False
                self.is_drawing = False
                self.move_offset = QPoint(ox - m['x'], oy - m['y'])
            else:
                # 点击空白→开始绘制新遮罩
                self.selected_mask_idx = -1
                self.is_drawing = True
                self.is_moving = False
                self.is_resizing = False
                self.draw_start = QPoint(mx, my)
                self.draw_current = self.draw_start
            self._update_display()
            self.masks_changed.emit()

        elif event.button() == Qt.MouseButton.RightButton:
            if self.is_drawing:
                self.is_drawing = False
            clicked_idx = self._find_mask_at(mx, my)
            if clicked_idx >= 0:
                del self.masks[clicked_idx]
                self.selected_mask_idx = -1
            self.is_moving = False
            self.is_resizing = False
            self._update_display()
            self.masks_changed.emit()

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动：更新绘制预览、移动遮罩或调整大小"""
        if not self.original_pixmap:
            return

        mx, my = int(event.position().x()), int(event.position().y())

        if self.is_drawing:
            self.draw_current = QPoint(mx, my)
            self._update_display()

        elif self.is_resizing and self.selected_mask_idx >= 0:
            m = self.masks[self.selected_mask_idx]
            ox, oy = self._canvas_to_original(mx, my)
            img_w, img_h = self.original_size
            edge = self.resize_edge

            # 使用delta方式计算（相对于锚点，更直观）
            if 'left' in edge:
                # 左边拖拽：锚点在右边，左边界跟随鼠标
                anchor_right = m['x'] + m['width']
                new_left = max(0, min(ox, anchor_right - MIN_MASK_SIZE))
                m['width'] = anchor_right - new_left
                m['x'] = new_left
            elif 'right' in edge:
                # 右边拖拽：锚点在左边，右边界跟随鼠标
                new_right = max(m['x'] + MIN_MASK_SIZE, ox)
                m['width'] = min(new_right - m['x'], img_w - m['x'])

            if 'top' in edge:
                # 上边拖拽：锚点在下边，上边界跟随鼠标
                anchor_bottom = m['y'] + m['height']
                new_top = max(0, min(oy, anchor_bottom - MIN_MASK_SIZE))
                m['height'] = anchor_bottom - new_top
                m['y'] = new_top
            elif 'bottom' in edge:
                # 下边拖拽：锚点在上边，下边界跟随鼠标
                new_bottom = max(m['y'] + MIN_MASK_SIZE, oy)
                m['height'] = min(new_bottom - m['y'], img_h - m['y'])

            self._update_display()

        elif self.is_moving and self.selected_mask_idx >= 0 and self.move_offset:
            ox, oy = self._canvas_to_original(mx, my)
            m = self.masks[self.selected_mask_idx]
            new_x = ox - self.move_offset.x()
            new_y = oy - self.move_offset.y()
            img_w, img_h = self.original_size
            new_x = max(0, min(new_x, img_w - m['width']))
            new_y = max(0, min(new_y, img_h - m['height']))
            m['x'] = new_x
            m['y'] = new_y
            self._update_display()

        else:
            # 非拖拽状态：根据鼠标位置更新光标样式
            self._update_cursor(mx, my)

    def _update_cursor(self, mx: int, my: int):
        """根据鼠标悬停位置更新光标样式"""
        # 检查选中遮罩的边缘
        if self.selected_mask_idx >= 0:
            edge = self._get_resize_edge(self.selected_mask_idx, mx, my)
            if edge:
                cursor_map = {
                    'left': Qt.CursorShape.SizeHorCursor,
                    'right': Qt.CursorShape.SizeHorCursor,
                    'top': Qt.CursorShape.SizeVerCursor,
                    'bottom': Qt.CursorShape.SizeVerCursor,
                    'topleft': Qt.CursorShape.SizeFDiagCursor,
                    'bottomright': Qt.CursorShape.SizeFDiagCursor,
                    'topright': Qt.CursorShape.SizeBDiagCursor,
                    'bottomleft': Qt.CursorShape.SizeBDiagCursor,
                }
                self.setCursor(cursor_map.get(edge, Qt.CursorShape.ArrowCursor))
                return

        # 检查是否在任意遮罩内部
        if self._find_mask_at(mx, my) >= 0:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return

        # 默认光标
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event):
        """鼠标离开控件时恢复默认光标"""
        self.setCursor(Qt.CursorShape.ArrowCursor)

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
        elif self.is_resizing:
            self.is_resizing = False

    def resizeEvent(self, event):
        """窗口大小变化时重新缩放图片"""
        super().resizeEvent(event)
        if self.original_pixmap:
            # 延迟到当前paint周期结束后再更新，避免BackingStore冲突
            QTimer.singleShot(0, self._update_display)


class ParticlePanel(BaseToolPanel):
    """GIF粒子提取器面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames_dir: str = ""
        self.ref_image_path: str = ""
        self.worker: BaseWorker | None = None
        self._play_timer: QTimer | None = None
        self._play_fps: int = 5  # 播放速率（帧/秒）
        self._play_index: int = 0
        self._setup_ui()

    def _setup_ui(self):
        """创建界面布局"""
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # ---- 顶部：文件夹加载 ----
        top_layout = QHBoxLayout()
        self.frames_label = QLabel()
        top_layout.addWidget(self.frames_label)
        self.frames_entry = DragDropFolderLineEdit()
        self.frames_entry.textChanged.connect(
            lambda t: setattr(self, 'frames_dir', t.strip()))
        top_layout.addWidget(self.frames_entry, stretch=1)
        self.frames_btn = QPushButton()
        self.frames_btn.clicked.connect(self._select_frames_dir)
        top_layout.addWidget(self.frames_btn)
        self.load_btn = QPushButton()
        self.load_btn.clicked.connect(self._load_folder)
        self.load_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        top_layout.addWidget(self.load_btn)
        layout.addLayout(top_layout)

        # ---- 中部：缩略图列表 + 图片显示 + 遮罩列表 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：缩略图列表
        thumb_panel = QWidget()
        thumb_layout = QVBoxLayout(thumb_panel)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(2)

        thumb_header = QHBoxLayout()
        self.thumb_label = QLabel()
        thumb_header.addWidget(self.thumb_label)
        thumb_header.addStretch()
        self.thumb_select_all_btn = QPushButton()
        self.thumb_select_all_btn.clicked.connect(self._thumb_select_all)
        thumb_header.addWidget(self.thumb_select_all_btn)
        self.thumb_deselect_btn = QPushButton()
        self.thumb_deselect_btn.clicked.connect(self._thumb_deselect_all)
        thumb_header.addWidget(self.thumb_deselect_btn)
        thumb_layout.addLayout(thumb_header)

        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(64, 48))
        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumb_list.setMovement(QListWidget.Movement.Static)
        self.thumb_list.setSpacing(2)
        self.thumb_list.setMinimumWidth(200)
        self.thumb_list.setMaximumWidth(240)
        self.thumb_list.itemClicked.connect(self._on_thumb_clicked)
        thumb_layout.addWidget(self.thumb_list)

        self.thumb_count_label = QLabel()
        self.thumb_count_label.setStyleSheet("color: gray; font-size: 11px;")
        thumb_layout.addWidget(self.thumb_count_label)

        # 播放序列帧控件
        play_label = QLabel()
        play_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        thumb_layout.addWidget(play_label)
        self.play_label = play_label

        play_row = QHBoxLayout()
        play_row.setSpacing(4)
        self.play_slower_btn = QPushButton("-")
        self.play_slower_btn.setFixedSize(28, 28)
        self.play_slower_btn.setStyleSheet("QPushButton { padding: 0px; font-size: 16px; font-weight: bold; }")
        self.play_slower_btn.clicked.connect(self._play_slower)
        play_row.addWidget(self.play_slower_btn)

        self.play_speed_spin = QSpinBox()
        self.play_speed_spin.setRange(1, 60)
        self.play_speed_spin.setValue(5)
        self.play_speed_spin.setSuffix(" fps")
        self.play_speed_spin.setFixedWidth(70)
        self._play_debounce = QTimer()
        self._play_debounce.setSingleShot(True)
        self._play_debounce.setInterval(350)
        self.play_speed_spin.valueChanged.connect(lambda: self._play_debounce.start())
        self._play_debounce.timeout.connect(lambda: self._on_play_speed_changed(self.play_speed_spin.value()))
        play_row.addWidget(self.play_speed_spin)

        self.play_faster_btn = QPushButton("+")
        self.play_faster_btn.setFixedSize(28, 28)
        self.play_faster_btn.setStyleSheet("QPushButton { padding: 0px; font-size: 16px; font-weight: bold; }")
        self.play_faster_btn.clicked.connect(self._play_faster)
        play_row.addWidget(self.play_faster_btn)

        self.play_toggle_btn = QPushButton()
        self.play_toggle_btn.clicked.connect(self._toggle_play)
        self.play_toggle_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 4px 10px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        play_row.addWidget(self.play_toggle_btn)
        thumb_layout.addLayout(play_row)

        splitter.addWidget(thumb_panel)

        # 中间：图片显示
        self.image_label = ImageLabel()
        splitter.addWidget(self.image_label)

        # 右侧：遮罩列表面板
        right_panel = QGroupBox()
        right_layout = QVBoxLayout(right_panel)
        self.mask_list_label = QLabel()
        self.mask_list_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.mask_list_label)

        self.mask_list = QListWidget()
        self.mask_list.currentRowChanged.connect(self._on_mask_selected)
        right_layout.addWidget(self.mask_list)

        # 选中遮罩的手动编辑区域
        edit_label = QLabel()
        edit_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        right_layout.addWidget(edit_label)
        self.mask_edit_label = edit_label

        edit_grid = QGridLayout()
        edit_grid.setSpacing(2)
        # X, Y, W, H 四行
        for row, (key, label) in enumerate([
            ('x', 'X'), ('y', 'Y'), ('w', 'W'), ('h', 'H')
        ]):
            lbl = QLabel(f"  {label}:")
            lbl.setFixedWidth(60)
            edit_grid.addWidget(lbl, row, 0)
            spin = QSpinBox()
            spin.setKeyboardTracking(False)
            spin.setRange(0, 99999)
            spin.setMinimumWidth(160)
            # 使用编辑完成信号 + 防抖定时器，避免逐字触发
            spin._debounce = QTimer()
            spin._debounce.setSingleShot(True)
            spin._debounce.setInterval(350)
            spin._debounce_key = key
            spin.valueChanged.connect(lambda v, s=spin: s._debounce.start())
            spin._debounce.timeout.connect(lambda s=spin: self._on_mask_edit(s._debounce_key, s.value()))
            edit_grid.addWidget(spin, row, 1)
            setattr(self, f'mask_{key}_spin', spin)

        # 质点分隔
        pivot_label = QLabel()
        pivot_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        right_layout.addWidget(pivot_label)
        self.pivot_label = pivot_label

        # 半宽 / 半高（调整质点半径，保持中心不变）
        for row, (key, label) in enumerate([
            ('hw', 'W/2'), ('hh', 'H/2')
        ]):
            lbl = QLabel(f"  {label}:")
            lbl.setFixedWidth(60)
            edit_grid.addWidget(lbl, row + 4, 0)
            spin = QSpinBox()
            spin.setRange(1, 99999)
            spin.setMinimumWidth(160)
            spin._debounce = QTimer()
            spin._debounce.setSingleShot(True)
            spin._debounce.setInterval(350)
            spin._debounce_key = key
            spin.valueChanged.connect(lambda v, s=spin: s._debounce.start())
            spin._debounce.timeout.connect(lambda s=spin: self._on_pivot_edit(s._debounce_key, s.value()))
            edit_grid.addWidget(spin, row + 4, 1)
            setattr(self, f'mask_{key}_spin', spin)

        # 分段分隔
        seg_label = QLabel()
        seg_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        right_layout.addWidget(seg_label)
        self.seg_label = seg_label

        # 分段 列数/行数（蓝色虚线从最左/最上开始均匀划分）
        for row, (key, label, rng) in enumerate([
            ('sw', '列数', 50), ('sh', '行数', 50)
        ]):
            lbl = QLabel(f"  {label}:")
            lbl.setFixedWidth(60)
            edit_grid.addWidget(lbl, row + 6, 0)
            spin = QSpinBox()
            spin.setRange(1, rng)
            spin.setValue(1)
            spin.setMinimumWidth(160)
            spin._debounce = QTimer()
            spin._debounce.setSingleShot(True)
            spin._debounce.setInterval(350)
            spin._debounce_key = key
            spin.valueChanged.connect(lambda v, s=spin: s._debounce.start())
            spin._debounce.timeout.connect(lambda s=spin: self._on_segment_edit(s._debounce_key, s.value()))
            edit_grid.addWidget(spin, row + 6, 1)
            setattr(self, f'mask_{key}_spin', spin)
        right_layout.addLayout(edit_grid)

        # 启用拆分（按网格拆分为子图片）
        from PySide6.QtWidgets import QCheckBox
        self.split_check = QCheckBox()
        self.split_check.toggled.connect(self._on_split_toggled)
        right_layout.addWidget(self.split_check)

        self.delete_mask_btn = QPushButton()
        self.delete_mask_btn.clicked.connect(self._delete_mask)
        self.delete_mask_btn.setMinimumHeight(30)
        self.delete_mask_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_layout.addWidget(self.delete_mask_btn)

        self.clear_masks_btn = QPushButton()
        self.clear_masks_btn.clicked.connect(self._clear_masks)
        self.clear_masks_btn.setMinimumHeight(30)
        self.clear_masks_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_layout.addWidget(self.clear_masks_btn)

        self.save_masks_btn = QPushButton()
        self.save_masks_btn.clicked.connect(self._save_masks)
        self.save_masks_btn.setMinimumHeight(30)
        self.save_masks_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_layout.addWidget(self.save_masks_btn)

        self.load_masks_btn = QPushButton()
        self.load_masks_btn.clicked.connect(self._load_masks)
        self.load_masks_btn.setMinimumHeight(30)
        self.load_masks_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_layout.addWidget(self.load_masks_btn)

        right_panel.setMinimumWidth(320)
        right_panel.setMaximumWidth(450)
        splitter.addWidget(right_panel)

        # 右侧面板优先保证最小宽度（按钮文本完整显示）
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 400, 320])
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        layout.addWidget(splitter, stretch=1)

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
        self.log_area.setMaximumHeight(100)
        layout.addWidget(self.log_area)

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
        self.load_btn.setText(self.tr("load_images"))
        self.thumb_label.setText(self.tr("thumbnails"))
        self.thumb_select_all_btn.setText(self.tr("select_all"))
        self.thumb_deselect_btn.setText(self.tr("deselect_all"))
        self.play_label.setText(self.tr("play_frames"))
        self.play_toggle_btn.setText("▶ " + self.tr("play"))
        self.mask_list_label.setText(self.tr("masks_panel"))
        self.delete_mask_btn.setText(self.tr("btn_delete_mask"))
        self.clear_masks_btn.setText(self.tr("btn_clear_masks"))
        self.save_masks_btn.setText(self.tr("btn_save_masks"))
        self.load_masks_btn.setText(self.tr("btn_load_masks"))
        self.mask_edit_label.setText(self.tr("mask_edit"))
        self.pivot_label.setText(self.tr("pivot_edit"))
        self.seg_label.setText(self.tr("seg_edit"))
        self.split_check.setText(self.tr("enable_split"))
        self.start_btn.setText(self.tr("start_extract"))
        self.stop_btn.setText(self.tr("stop"))

    # ---------- 文件夹加载 ----------

    def _select_frames_dir(self):
        """选择帧序列文件夹"""
        folder = self.browse_folder(self.tr("select_frames_folder"))
        if folder:
            self.frames_entry.setText(folder)

    def _load_folder(self):
        """加载文件夹：显示缩略图，自动加载第一张为参考帧"""
        folder = self.frames_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            return

        supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        files = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(supported):
                files.append(os.path.join(folder, f))

        if not files:
            self.status_label.setText(self.tr("pe_error_no_frames"))
            return

        self.frames_dir = os.path.normpath(folder)
        self._build_thumb_list(files)

        # 自动加载第一张为参考帧
        first_file = os.path.normpath(files[0])
        if self.image_label.load_image(first_file):
            self.ref_image_path = files[0]
            self.log(f"已加载 {len(files)} 张图片，参考帧: {os.path.basename(files[0])}")
            self.status_label.setText(
                f"已加载 {len(files)} 张 | 点击缩略图切换参考帧")
        else:
            self.show_error(self.tr("error_title"), "无法加载图片文件")

    # ---------- 缩略图 ----------

    def _build_thumb_list(self, files: list[str]):
        """构建缩略图列表（跳过无法加载的图片）"""
        self.thumb_list.clear()
        for path in files:
            name = os.path.basename(path)
            normalized = os.path.normpath(path)
            pixmap = QPixmap(normalized)
            if pixmap.isNull():
                # 跳过无法加载的缩略图
                continue
            icon = QIcon(pixmap.scaled(
                64, 48, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            item = QListWidgetItem(icon, name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)  # 默认全选
            self.thumb_list.addItem(item)
        self._update_thumb_count()

    def _on_thumb_clicked(self, item: QListWidgetItem):
        """点击缩略图→切换参考帧（保留遮罩）"""
        path = os.path.normpath(item.data(Qt.ItemDataRole.UserRole))
        if self.image_label.switch_image(path):
            self.ref_image_path = path
            self.status_label.setText(f"参考帧: {os.path.basename(path)}")

    def _thumb_select_all(self):
        for i in range(self.thumb_list.count()):
            self.thumb_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._update_thumb_count()

    def _thumb_deselect_all(self):
        for i in range(self.thumb_list.count()):
            self.thumb_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._update_thumb_count()

    def _update_thumb_count(self):
        checked = sum(1 for i in range(self.thumb_list.count())
                      if self.thumb_list.item(i).checkState() == Qt.CheckState.Checked)
        self.thumb_count_label.setText(
            f"已选 {checked}/{self.thumb_list.count()}")

    # ---------- 播放序列帧 ----------

    def _toggle_play(self):
        """启动/停止播放序列帧"""
        if self._play_timer and self._play_timer.isActive():
            self._play_timer.stop()
            self.play_toggle_btn.setText("▶ 播放")
            self.play_toggle_btn.setStyleSheet(
                "QPushButton { background-color: #0078d4; color: white; "
                "padding: 4px 10px; font-weight: bold; border: none; }"
                "QPushButton:hover { background-color: #1084e0; }")
            return

        if self.thumb_list.count() == 0:
            return

        if not self._play_timer:
            self._play_timer = QTimer(self)
            self._play_timer.timeout.connect(self._play_next_frame)

        self._play_index = 0
        interval = max(16, 1000 // self._play_fps)  # 最小16ms防过载
        self._play_timer.start(interval)
        self._play_next_frame()
        self.play_toggle_btn.setText("⏸ 停止")
        self.play_toggle_btn.setStyleSheet(
            "QPushButton { background-color: #c42b1c; color: white; "
            "padding: 4px 10px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #d4382b; }")

    def _play_next_frame(self):
        """播放下一帧：跳过无法加载的图片"""
        count = self.thumb_list.count()
        if count == 0:
            self._toggle_play()
            return
        # 最多尝试count次，跳过坏帧
        for _ in range(count):
            self._play_index = (self._play_index + 1) % count
            path = self.thumb_list.item(self._play_index).data(Qt.ItemDataRole.UserRole)
            if self.image_label.switch_image(path):
                self.ref_image_path = path
                self.status_label.setText(
                    f"播放中 [{self._play_index + 1}/{count}] "
                    f"{os.path.basename(path)}")
                return

    def _play_faster(self):
        """加快播放速率"""
        val = self.play_speed_spin.value()
        if val < 60:
            self.play_speed_spin.setValue(min(60, val + 5))

    def _play_slower(self):
        """减慢播放速率"""
        val = self.play_speed_spin.value()
        if val > 1:
            self.play_speed_spin.setValue(max(1, val - 1))

    def _on_play_speed_changed(self, fps: int):
        """播放速率改变"""
        self._play_fps = fps
        if self._play_timer and self._play_timer.isActive():
            self._play_timer.setInterval(max(16, 1000 // fps))

    def _update_play_speed(self):
        """更新播放速率显示"""
        self.play_speed_spin.setValue(self._play_fps)

    def _get_checked_images(self) -> list[str]:
        """获取已勾选的图片路径列表"""
        return [self.thumb_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.thumb_list.count())
                if self.thumb_list.item(i).checkState() == Qt.CheckState.Checked]

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
        """遮罩列表选中→同步到图片显示和编辑框"""
        self.image_label.selected_mask_idx = idx
        self.image_label._update_display()
        self._update_mask_edits()

    def _update_mask_list(self):
        """更新遮罩列表（从image_label同步）"""
        self.mask_list.blockSignals(True)
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
        self.mask_list.blockSignals(False)
        self._update_mask_edits()

    def _update_mask_edits(self):
        """根据选中的遮罩更新编辑框数值"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            m = self.image_label.masks[idx]
            self.mask_x_spin.blockSignals(True)
            self.mask_y_spin.blockSignals(True)
            self.mask_w_spin.blockSignals(True)
            self.mask_h_spin.blockSignals(True)
            self.mask_x_spin.setValue(m.get('x', 0))
            self.mask_y_spin.setValue(m.get('y', 0))
            self.mask_w_spin.setValue(m.get('width', m.get('w', 0)))
            self.mask_h_spin.setValue(m.get('height', m.get('h', 0)))
            self.mask_x_spin.blockSignals(False)
            self.mask_y_spin.blockSignals(False)
            self.mask_w_spin.blockSignals(False)
            self.mask_h_spin.blockSignals(False)
            self.mask_hw_spin.blockSignals(True)
            self.mask_hh_spin.blockSignals(True)
            self.mask_hw_spin.setValue(m['width'] // 2)
            self.mask_hh_spin.setValue(m['height'] // 2)
            self.mask_hw_spin.blockSignals(False)
            self.mask_hh_spin.blockSignals(False)
            self.mask_x_spin.setEnabled(True)
            self.mask_y_spin.setEnabled(True)
            self.mask_w_spin.setEnabled(True)
            self.mask_h_spin.setEnabled(True)
            self.mask_sw_spin.blockSignals(True)
            self.mask_sh_spin.blockSignals(True)
            self.mask_sw_spin.setValue(m.get('seg_cols', 1))
            self.mask_sh_spin.setValue(m.get('seg_rows', 1))
            self.mask_sw_spin.blockSignals(False)
            self.mask_sh_spin.blockSignals(False)
            self.mask_hw_spin.setEnabled(True)
            self.mask_hh_spin.setEnabled(True)
            self.split_check.blockSignals(True)
            self.split_check.setChecked(m.get('split', False))
            self.split_check.blockSignals(False)
            self.mask_sw_spin.setEnabled(True)
            self.mask_sh_spin.setEnabled(True)
            self.split_check.setEnabled(True)
        else:
            for attr in ('x', 'y', 'w', 'h', 'hw', 'hh', 'sw', 'sh'):
                spin = getattr(self, f'mask_{attr}_spin', None)
                if spin:
                    spin.setEnabled(False)
            self.split_check.setEnabled(False)

    def _on_mask_edit(self, key: str, value: int):
        """手动编辑遮罩数值（x/y/w/h直接修改）"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            # 短键→全名映射（与MaskDef字段一致）
            key_map = {'x': 'x', 'y': 'y', 'w': 'width', 'h': 'height'}
            real_key = key_map.get(key, key)
            self.image_label.masks[idx][real_key] = value
            self.image_label._update_display()
            self._update_mask_list()
            self._update_mask_edits()  # 同步半宽/半高

    def _on_pivot_edit(self, key: str, value: int):
        """质点编辑：调整半宽/半高，保持中心点不变"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            m = self.image_label.masks[idx]
            cx = m['x'] + m['width'] // 2
            cy = m['y'] + m['height'] // 2
            if key == 'hw':
                m['width'] = value * 2
                m['x'] = cx - value
            else:
                m['height'] = value * 2
                m['y'] = cy - value
            self.image_label._update_display()
            self._update_mask_list()
            self._update_mask_edits()

    def _on_segment_edit(self, key: str, value: int):
        """分段编辑：设置列数/行数（单元格数），视觉辅助"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            m = self.image_label.masks[idx]
            m['seg_cols'] = value if key == 'sw' else m.get('seg_cols', 1)
            m['seg_rows'] = value if key == 'sh' else m.get('seg_rows', 1)
            self.image_label._update_display()

    def _on_split_toggled(self, checked: bool):
        """启用/禁用拆分"""
        idx = self.image_label.selected_mask_idx
        if 0 <= idx < len(self.image_label.masks):
            self.image_label.masks[idx]['split'] = checked

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
            maskdefs = [MaskDef(id=m.get('id',0), label=m.get('label',''), x=m.get('x',0), y=m.get('y',0), width=m.get('width', m.get('w',0)), height=m.get('height', m.get('h',0))) for m in self.image_label.masks]
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

        # 只处理已勾选的图片
        checked_files = self._get_checked_images()
        if not checked_files:
            self.show_error(self.tr("error_title"), "请先在缩略图中勾选要处理的图片")
            return
        total = len(checked_files)

        output_dir = os.path.join(self.frames_dir, "particles")

        # 确认
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
        from particle_extractor import MaskDef, ParticleExtractor
        maskdefs = [MaskDef(id=m.get('id',0), label=m.get('label',''), x=m.get('x',0), y=m.get('y',0), width=m.get('width', m.get('w',0)), height=m.get('height', m.get('h',0))) for m in self.image_label.masks]

        class ExtractWorker(BaseWorker):
            def __init__(slf):
                super().__init__()
                slf.extractor = ParticleExtractor(
                    log_callback=lambda msg: slf.signals.log.emit(msg))

            def run(slf):
                try:
                    # 直接对勾选的文件列表应用遮罩（不扫描整个目录）
                    os.makedirs(output_dir, exist_ok=True)
                    for mask in maskdefs:
                        os.makedirs(os.path.join(output_dir, mask.label), exist_ok=True)

                    for idx, img_path in enumerate(checked_files):
                        if slf._stop_flag:
                            break
                        try:
                            from PIL import Image
                            filename = os.path.basename(img_path)
                            with Image.open(img_path) as img:
                                for mi, mask in enumerate(maskdefs):
                                    # 从原始dict获取split/segment参数
                                    orig = self.image_label.masks[mi]
                                    left = max(0, mask.x)
                                    top = max(0, mask.y)
                                    right = min(img.width, mask.x + mask.width)
                                    bottom = min(img.height, mask.y + mask.height)
                                    if right > left and bottom > top:
                                        cropped = img.crop((left, top, right, bottom))
                                        ext = os.path.splitext(img_path)[1]
                                        base_name = os.path.splitext(filename)[0]
                                        # 拆分模式：按行列拆分为子图
                                        cols = orig.get('seg_cols', 1)
                                        rows = orig.get('seg_rows', 1)
                                        if orig.get('split') and (cols > 1 or rows > 1):
                                            cw = cropped.width / cols
                                            rh = cropped.height / rows
                                            for r in range(rows):
                                                for c_val in range(cols):
                                                    x1 = int(c_val * cw)
                                                    y1 = int(r * rh)
                                                    x2 = int((c_val + 1) * cw)
                                                    y2 = int((r + 1) * rh)
                                                    sub = cropped.crop((x1, y1, x2, y2))
                                                    sub.save(os.path.join(
                                                        output_dir, mask.label,
                                                        f"{base_name}_r{r}c{c_val}{ext}"))
                                        else:
                                            out_path = os.path.join(
                                                output_dir, mask.label,
                                                base_name + ext)
                                            cropped.save(out_path)
                        except Exception as e:
                            slf.signals.log.emit(f"跳过 {img_path}: {e}")
                        slf.signals.progress.emit(idx + 1, total)

                    slf.signals.log.emit(
                        f"提取完成! 共处理 {total} 帧 × {len(maskdefs)} 个遮罩")
                    slf.signals.finished.emit({
                        'success': True, 'frame_count': total,
                        'mask_count': len(maskdefs), 'output_dir': output_dir})
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
