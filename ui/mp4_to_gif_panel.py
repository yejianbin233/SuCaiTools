"""
MP4转GIF工具面板

将MP4视频转换为GIF动图。
修复原版将所有帧加载到内存的严重问题——改为流式逐帧处理+控制最大帧数。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QSpinBox,
    QProgressBar, QGroupBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropLineEdit
from core.base_worker import BaseWorker

# 安全上限：最大处理帧数，防止内存溢出
MAX_FRAMES = 500
# 目标GIF帧率
TARGET_FPS = 10


class Mp4ToGifWorker(BaseWorker):
    """MP4→GIF转换工作线程

    改进：逐帧处理，只保留降采样后的帧（最多MAX_FRAMES帧），
    不会将所有视频帧加载到内存。
    """

    def __init__(self, video_path: str, output_path: str,
                 fps: int = TARGET_FPS, max_frames: int = MAX_FRAMES):
        super().__init__()
        self.video_path = video_path
        self.output_path = output_path
        self.fps = fps
        self.max_frames = max_frames

    def run(self):
        """执行MP4→GIF转换"""
        import cv2
        from PIL import Image

        try:
            self.signals.log.emit(f"正在打开: {os.path.basename(self.video_path)}")

            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.signals.error.emit("无法打开视频文件")
                self.signals.finished.emit(
                    {'success': False, 'error': '无法打开视频'})
                return

            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.signals.log.emit(
                f"视频: {total_frames}帧, {video_fps:.1f}fps")

            # 计算采样间隔
            interval = max(1, int(video_fps / self.fps))
            self.signals.log.emit(
                f"目标: {self.fps}fps, 每隔{interval}帧采样, "
                f"最多{self.max_frames}帧")

            # 逐帧处理，收集降采样后的帧（限制最大数量）
            pil_frames = []
            frame_idx = 0
            while len(pil_frames) < self.max_frames:
                if self._stop_flag:
                    break
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % interval == 0:
                    # 转换BGR→RGB
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    # 限制GIF尺寸（最大640宽）
                    if pil_img.width > 640:
                        ratio = 640 / pil_img.width
                        new_h = int(pil_img.height * ratio)
                        pil_img = pil_img.resize(
                            (640, new_h), Image.Resampling.LANCZOS)
                    pil_frames.append(pil_img)
                    self.signals.progress.emit(
                        len(pil_frames), self.max_frames)

                frame_idx += 1

            cap.release()

            if not pil_frames:
                self.signals.error.emit("未能提取任何帧")
                self.signals.finished.emit(
                    {'success': False, 'error': '无帧'})
                return

            # 保存GIF
            self.signals.log.emit(f"正在保存GIF ({len(pil_frames)}帧)...")
            duration = int(1000 / self.fps)  # 每帧毫秒数
            pil_frames[0].save(
                self.output_path,
                save_all=True,
                append_images=pil_frames[1:],
                duration=duration,
                loop=0,
                optimize=True  # 优化GIF大小
            )

            file_size = os.path.getsize(self.output_path)
            self.signals.log.emit(
                f"GIF保存完成! {len(pil_frames)}帧, "
                f"{file_size / 1024:.1f}KB")
            self.signals.finished.emit({
                'success': True,
                'frame_count': len(pil_frames),
                'output_path': self.output_path
            })

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


class Mp4ToGifPanel(BaseToolPanel):
    """MP4转GIF面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path: str = ""
        self.worker: Mp4ToGifWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 视频选择
        file_group = QGroupBox()
        file_layout = QGridLayout(file_group)
        self.video_label = QLabel()
        file_layout.addWidget(self.video_label, 0, 0)
        self.video_entry = DragDropLineEdit(
            allowed_extensions=('.mp4', '.avi', '.mov', '.mkv'))
        self.video_entry.setPlaceholderText("选择MP4/视频文件或拖放到此处")
        self.video_entry.textChanged.connect(
            lambda t: setattr(self, 'video_path', t.strip()))
        file_layout.addWidget(self.video_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_video)
        file_layout.addWidget(self.browse_btn, 0, 2)
        layout.addWidget(file_group)

        # 设置
        settings = QHBoxLayout()
        self.fps_label = QLabel()
        settings.addWidget(self.fps_label)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(TARGET_FPS)
        self.fps_spin.setSuffix(" fps")
        settings.addWidget(self.fps_spin)
        self.max_label = QLabel()
        settings.addWidget(self.max_label)
        self.max_spin = QSpinBox()
        self.max_spin.setRange(10, MAX_FRAMES)
        self.max_spin.setValue(MAX_FRAMES)
        self.max_spin.setSuffix(" 帧")
        settings.addWidget(self.max_spin)
        settings.addStretch()
        layout.addLayout(settings)

        # 操作
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

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    def retranslate_ui(self):
        self.video_label.setText(self.tr("select_mp4_file"))
        self.browse_btn.setText(self.tr("browse"))
        self.fps_label.setText(self.tr("fps"))
        self.max_label.setText(self.tr("max_frames"))
        self.start_btn.setText(self.tr("start_convert"))
        self.stop_btn.setText(self.tr("stop"))

    def _select_video(self):
        path = self.browse_file(
            self.tr("select_mp4_file"),
            "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*.*)")
        if path:
            self.video_entry.setText(path)

    def _start(self):
        if not self.video_path or not os.path.isfile(self.video_path):
            self.show_error(self.tr("error_title"),
                            self.tr("error_no_video"))
            return
        output = os.path.join(
            os.path.dirname(self.video_path),
            os.path.splitext(os.path.basename(self.video_path))[0] + '.gif')

        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = Mp4ToGifWorker(
            self.video_path, output,
            self.fps_spin.value(), self.max_spin.value())
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
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

    def _on_error(self, err):
        self.log(f"[错误] {err}")

    def _on_finished(self, result):
        self.set_processing(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            self.status_label.setText(
                f"完成! {result.get('frame_count', 0)}帧 "
                f"({os.path.getsize(result.get('output_path', '')) / 1024:.0f}KB)")
            QMessageBox.information(
                self, self.tr("info_title"),
                f"GIF转换完成!\n{result.get('output_path', '')}")
