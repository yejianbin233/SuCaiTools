"""
视频转PNG序列工具面板

将视频文件转换为逐帧PNG图片序列，支持自定义帧率采样。
基于OpenCV实现，修复原版独立Tk应用无法嵌入主程序的问题。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QGroupBox, QSpinBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropLineEdit
from core.base_worker import BaseWorker


class VideoToPngWorker(BaseWorker):
    """视频转PNG工作线程"""

    def __init__(self, video_path: str, output_dir: str,
                 fps: int = 0):
        super().__init__()
        self.video_path = video_path
        self.output_dir = output_dir
        self.fps = fps

    def run(self):
        """执行视频帧提取"""
        import cv2

        try:
            self.signals.log.emit(f"正在打开视频: {os.path.basename(self.video_path)}")

            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.signals.error.emit("无法打开视频文件")
                self.signals.finished.emit(
                    {'success': False, 'error': '无法打开视频'})
                return

            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            self.signals.log.emit(
                f"视频信息: {width}x{height}, {video_fps:.1f}fps, "
                f"{total_frames}帧")

            # 计算采样间隔
            sample_fps = self.fps if self.fps > 0 else video_fps
            interval = max(1, int(video_fps / sample_fps))
            expected = total_frames // interval + 1

            self.signals.log.emit(
                f"采样帧率: {sample_fps}fps, 间隔: {interval}帧, "
                f"预计提取: {expected}帧")

            os.makedirs(self.output_dir, exist_ok=True)

            frame_idx = 0
            saved = 0
            while True:
                if self._stop_flag:
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % interval == 0:
                    out_path = os.path.join(
                        self.output_dir, f"frame_{saved:05d}.png")
                    cv2.imwrite(out_path, frame)
                    saved += 1
                    self.signals.progress.emit(saved, expected)

                frame_idx += 1

            cap.release()

            self.signals.log.emit(f"提取完成! 共保存 {saved} 帧")
            self.signals.log.emit(f"输出目录: {self.output_dir}")
            self.signals.finished.emit(
                {'success': True, 'frame_count': saved,
                 'output_dir': self.output_dir})

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


class VideoToPngPanel(BaseToolPanel):
    """视频转PNG序列面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path: str = ""
        self.output_dir: str = ""
        self.worker: VideoToPngWorker | None = None
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
            allowed_extensions=('.mp4', '.avi', '.mov', '.mkv', '.webm'))
        self.video_entry.setPlaceholderText("选择视频文件或拖放到此处")
        file_layout.addWidget(self.video_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_video)
        file_layout.addWidget(self.browse_btn, 0, 2)
        layout.addWidget(file_group)

        # 输出和帧率设置
        settings_layout = QHBoxLayout()
        self.fps_label = QLabel()
        settings_layout.addWidget(self.fps_label)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(0, 120)
        self.fps_spin.setValue(0)
        self.fps_spin.setSpecialValueText("原始帧率")
        self.fps_spin.setSuffix(" fps")
        settings_layout.addWidget(self.fps_spin)
        self.output_label = QLabel()
        settings_layout.addWidget(self.output_label)
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("留空则在视频同目录创建")
        settings_layout.addWidget(self.output_entry)
        self.output_btn = QPushButton()
        self.output_btn.clicked.connect(self._select_output)
        settings_layout.addWidget(self.output_btn)
        layout.addLayout(settings_layout)

        # 操作按钮
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
        self.video_label.setText(self.tr("select_video"))
        self.browse_btn.setText(self.tr("browse"))
        self.fps_label.setText(self.tr("fps"))
        self.output_label.setText(self.tr("output_dir"))
        self.output_btn.setText(self.tr("browse"))
        self.start_btn.setText(self.tr("start_extraction"))
        self.stop_btn.setText(self.tr("stop"))

    def _select_video(self):
        path = self.browse_file(
            self.tr("select_video"),
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.webm);;所有文件 (*.*)")
        if path:
            self.video_path = path
            self.video_entry.setText(path)
            if not self.output_dir:
                default_out = os.path.join(
                    os.path.dirname(path),
                    os.path.splitext(os.path.basename(path))[0] + "_frames")
                self.output_entry.setText(default_out)

    def _select_output(self):
        folder = self.browse_folder(self.tr("output_dir"))
        if folder:
            self.output_dir = folder
            self.output_entry.setText(folder)

    def _start(self):
        path = self.video_entry.text().strip()
        if not path or not os.path.isfile(path):
            self.show_error(self.tr("error_title"), self.tr("error_no_video"))
            return
        self.video_path = path
        output = self.output_entry.text().strip() or os.path.join(
            os.path.dirname(path),
            os.path.splitext(os.path.basename(path))[0] + "_frames")

        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = VideoToPngWorker(
            self.video_path, output, self.fps_spin.value())
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
            count = result.get('frame_count', 0)
            self.status_label.setText(
                self.tr("status_complete").format(count=count))
            QMessageBox.information(
                self, self.tr("info_title"),
                f"提取 {count} 帧完成!\n{result.get('output_dir', '')}")
