"""
基础工作线程类

提供信号/槽模式的异步任务基类，解决原项目中后台线程直接操作UI的线程安全问题。

使用方式:
    class MyWorker(BaseWorker):
        def run(self):
            self.signals.log.emit("开始处理...")
            for i in range(100):
                if self._stop_flag:
                    break
                # 执行耗时操作...
                self.signals.progress.emit(i + 1, 100)
            self.signals.finished.emit({'success': True})

    worker = MyWorker()
    worker.signals.log.connect(self.on_log)
    worker.signals.progress.connect(self.on_progress)
    worker.signals.finished.connect(self.on_finished)
    QThreadPool.globalInstance().start(worker)
"""

from PySide6.QtCore import QObject, Signal, QRunnable


class WorkerSignals(QObject):
    """工作线程信号集合

    所有信号都是线程安全的——Qt的信号/槽机制会自动将跨线程信号
    排队到接收者所在的线程（通常是主线程），无需手动使用 after()。
    """
    finished = Signal(dict)       # 任务完成，携带结果字典
    progress = Signal(int, int)   # 进度更新 (当前值, 总数)
    log = Signal(str)             # 日志消息
    error = Signal(str)           # 错误消息


class BaseWorker(QRunnable):
    """异步工作线程基类

    所有耗时操作（图片处理、视频转换等）应继承此类，
    通过 signals 与主线程通信，禁止在 run() 中直接操作UI组件。
    """

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._stop_flag = False

    def stop(self):
        """请求停止正在执行的任务"""
        self._stop_flag = True

    def run(self):
        """子类必须重写此方法实现具体的任务逻辑"""
        raise NotImplementedError("子类必须实现 run() 方法")
