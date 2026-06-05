import os
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import cv2
from PIL import Image
from tkinterdnd2 import DND_FILES
from drag_drop_handler import handle_file_drop # Assuming a similar handler exists or will be created
# from language_manager import LanguageManager # Passed in



class Mp4ToGifFrame(ctk.CTkFrame):
    def __init__(self, master, lang_manager):
        super().__init__(master)
        self.lang_manager = lang_manager

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(4, weight=1) # Adjust row index for log area

        self.mp4_path = tk.StringVar()
        self.gif_path = tk.StringVar()
        self.is_running = False
 

        # --- GUI Elements ---
        current_row = 0

        # 1. MP4 File Selection
        ctk.CTkLabel(self, text=self.lang_manager.get_text('select_mp4_file')).grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
        self.mp4_entry = ctk.CTkEntry(self, textvariable=self.mp4_path, width=350)
        self.mp4_entry.grid(row=current_row, column=1, padx=5, pady=5, sticky="ew")
        self.browse_mp4_button = ctk.CTkButton(self, text=self.lang_manager.get_text('browse'), command=self.browse_mp4_file)
        self.browse_mp4_button.grid(row=current_row, column=2, padx=5, pady=5)
        current_row += 1

        # Drag and Drop for MP4 input
        try:
            self.mp4_entry.drop_target_register(DND_FILES)
            # Use handle_file_drop, assuming it updates the entry
            self.mp4_entry.dnd_bind('<<Drop>>',
                                      lambda e: handle_file_drop(e, self.mp4_entry, self.lang_manager, ['.mp4']))
        except Exception as e:
            print(f"MP4拖拽功能初始化失败: {e}")

        # 2. GIF Output Selection
        ctk.CTkLabel(self, text=self.lang_manager.get_text('select_gif_output')).grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
        self.gif_entry = ctk.CTkEntry(self, textvariable=self.gif_path, width=350)
        self.gif_entry.grid(row=current_row, column=1, padx=5, pady=5, sticky="ew")
        self.browse_gif_button = ctk.CTkButton(self, text=self.lang_manager.get_text('browse'), command=self.browse_gif_output)
        self.browse_gif_button.grid(row=current_row, column=2, padx=5, pady=5)
        current_row += 1

        # 3. FPS Display and Input
        self.fps_label = ctk.CTkLabel(self, text=self.lang_manager.get_text('original_fps') + ": N/A")
        self.fps_label.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(self, text=self.lang_manager.get_text('set_fps')).grid(row=current_row, column=1, padx=5, pady=5, sticky="e")
        self.fps_entry = ctk.CTkEntry(self, width=100)
        self.fps_entry.grid(row=current_row, column=2, padx=5, pady=5, sticky="w")
        current_row += 1

        # 4. Start Button
        self.convert_button = ctk.CTkButton(self, text=self.lang_manager.get_text('start_conversion'), command=self.start_conversion_thread)
        self.convert_button.grid(row=current_row, column=0, columnspan=3, padx=5, pady=10)
        current_row += 1

        # 4. Log Area
        ctk.CTkLabel(self, text=self.lang_manager.get_text('log')).grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
        current_row += 1
        self.log_area = ctk.CTkTextbox(self, wrap=tk.WORD, height=150)
        self.log_area.grid(row=current_row, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.log_area.configure(state='disabled')

    def update_ui_texts(self):
        # Update labels and buttons
        self.grid_slaves(row=0, column=0)[0].configure(text=self.lang_manager.get_text('select_mp4_file'))
        self.browse_mp4_button.configure(text=self.lang_manager.get_text('browse'))
        self.grid_slaves(row=1, column=0)[0].configure(text=self.lang_manager.get_text('select_gif_output'))
        self.browse_gif_button.configure(text=self.lang_manager.get_text('browse'))
        self.convert_button.configure(text=self.lang_manager.get_text('start_conversion') if not self.is_running else self.lang_manager.get_text('processing'))
        self.grid_slaves(row=3, column=0)[0].configure(text=self.lang_manager.get_text('log'))

    def log(self, message):
        def _update_log():
            self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
            self.log_area.configure(state='disabled')
        self.after(0, _update_log)

    def browse_mp4_file(self):
        if self.is_running:
            messagebox.showwarning(self.lang_manager.get_text('title'), self.lang_manager.get_text('task_running'))
            return
        filepath = filedialog.askopenfilename(title=self.lang_manager.get_text('select_mp4_file'),
                                            filetypes=[("MP4 files", "*.mp4")])
        if filepath:
            self.mp4_path.set(filepath)
            
            # Get and display original FPS
            try:
                cap = cv2.VideoCapture(filepath)
                original_fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                if original_fps > 0:
                    self.fps_label.configure(text=self.lang_manager.get_text('original_fps') + f": {original_fps:.2f}")
                    self.fps_entry.delete(0, tk.END)
                    self.fps_entry.insert(0, f"{original_fps:.2f}") # Pre-fill with original FPS
                else:
                    self.fps_label.configure(text=self.lang_manager.get_text('original_fps') + ": N/A")
                    self.fps_entry.delete(0, tk.END)
            except Exception as e:
                self.log(f"Error getting video info: {e}")
                self.fps_label.configure(text=self.lang_manager.get_text('original_fps') + ": Error")
                self.fps_entry.delete(0, tk.END)

            # Auto-suggest output path
            if not self.gif_path.get():
                output_dir = os.path.dirname(filepath)
                base_name = os.path.splitext(os.path.basename(filepath))[0]
                self.gif_path.set(os.path.join(output_dir, f"{base_name}.gif"))

    def browse_gif_output(self):
        if self.is_running:
            messagebox.showwarning(self.lang_manager.get_text('title'), self.lang_manager.get_text('task_running'))
            return
        filepath = filedialog.asksaveasfilename(title=self.lang_manager.get_text('select_gif_output'),
                                              defaultextension=".gif",
                                              filetypes=[("GIF files", "*.gif")])
        if filepath:
            self.gif_path.set(filepath)

    def start_conversion_thread(self):
        if self.is_running:
            messagebox.showwarning(self.lang_manager.get_text('title'), self.lang_manager.get_text('task_running'))
            return


        mp4_file = self.mp4_path.get()
        gif_file = self.gif_path.get()

        if not mp4_file or not os.path.isfile(mp4_file):
            messagebox.showerror(self.lang_manager.get_text('error'), self.lang_manager.get_text('invalid_mp4_path'))
            return
        if not gif_file:
            messagebox.showerror(self.lang_manager.get_text('error'), self.lang_manager.get_text('invalid_gif_path'))
            return
        if os.path.isdir(gif_file):
             messagebox.showerror(self.lang_manager.get_text('error'), self.lang_manager.get_text('output_is_directory'))
             return

        # Confirmation (optional)
        # if not messagebox.askyesno(self.lang_manager.get_text('confirm', 'Confirm'),
        #                           self.lang_manager.get_text('confirm_conversion', 'Start conversion?')):
        #     return

        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.configure(state='disabled')
        self.convert_button.configure(state='disabled', text=self.lang_manager.get_text('processing'))
        self.browse_mp4_button.configure(state='disabled')
        self.browse_gif_button.configure(state='disabled')
        self.is_running = True

        # Get desired FPS from entry
        try:
            desired_fps = float(self.fps_entry.get())
            if desired_fps <= 0:
                raise ValueError("FPS must be positive.")
        except ValueError:
            messagebox.showerror(self.lang_manager.get_text('error'), self.lang_manager.get_text('invalid_fps_value'))
            self.is_running = False
            self.convert_button.configure(state='normal', text=self.lang_manager.get_text('start_conversion'))
            self.browse_mp4_button.configure(state='normal')
            self.browse_gif_button.configure(state='normal')
            return

        self.conversion_thread = threading.Thread(target=self.run_conversion_task, args=(mp4_file, gif_file, desired_fps))
        self.conversion_thread.daemon = True
        self.conversion_thread.start()

    def run_conversion_task(self, mp4_file, gif_file, desired_fps):
        try:
            self.log(self.lang_manager.get_text('conversion_started').format(input=mp4_file, output=gif_file))
            
            # --- Actual Conversion Logic using OpenCV and Pillow ---
            self.convert_mp4_to_gif_opencv(mp4_file, gif_file, desired_fps)
            
            self.log(self.lang_manager.get_text('conversion_success').format(output=gif_file))
        except Exception as e:
            self.log(self.lang_manager.get_text('conversion_error').format(error=str(e)))
        finally:
            # Re-enable UI elements in the main thread
            def _finalize_ui():
                self.is_running = False
                self.convert_button.configure(state='normal', text=self.lang_manager.get_text('start_conversion'))
                self.browse_mp4_button.configure(state='normal')
                self.browse_gif_button.configure(state='normal')
        self.after(0, _finalize_ui)

    # 安全上限：防止内存溢出
    MAX_GIF_FRAMES = 300
    MAX_GIF_WIDTH = 480

    def convert_mp4_to_gif_opencv(self, mp4_path, gif_path, desired_fps):
        """
        将MP4视频转换为GIF（使用OpenCV + Pillow）

        改进：采样帧+限制最大帧数+限制分辨率，防止内存溢出。
        """
        cap = cv2.VideoCapture(mp4_path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频文件: {mp4_path}")

        # 获取视频原始FPS和总帧数
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps_to_use = max(1, min(desired_fps, video_fps))

        # 计算采样间隔：每隔N帧取1帧
        sample_interval = max(1, int(video_fps / fps_to_use))
        estimated_frames = total_frames // sample_interval

        # 如果估计帧数超过上限，增大采样间隔
        if estimated_frames > self.MAX_GIF_FRAMES:
            sample_interval = max(1, total_frames // self.MAX_GIF_FRAMES)
            estimated_frames = total_frames // sample_interval
            actual_fps = video_fps / sample_interval
            self.log(f"帧数超限({estimated_frames}>{self.MAX_GIF_FRAMES})，"
                     f"自动调整为 {actual_fps:.1f}fps")

        self.log(f"视频: {total_frames}帧/{video_fps:.1f}fps, "
                 f"采样间隔: {sample_interval}, 目标: {fps_to_use}fps")

        frames = []
        frame_idx = 0
        while len(frames) < self.MAX_GIF_FRAMES:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                # BGR→RGB
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img)
                # 限制GIF宽度，保持宽高比
                if pil_img.width > self.MAX_GIF_WIDTH:
                    ratio = self.MAX_GIF_WIDTH / pil_img.width
                    new_h = int(pil_img.height * ratio)
                    pil_img = pil_img.resize(
                        (self.MAX_GIF_WIDTH, new_h), Image.Resampling.LANCZOS)
                frames.append(pil_img)

            frame_idx += 1

        cap.release()

        if not frames:
            raise ValueError("未从视频中读取到任何帧。")

        duration_ms = int(1000 / fps_to_use)

        self.log(f"共采样 {len(frames)} 帧，开始生成 GIF...")

        frames[0].save(gif_path,
                       save_all=True,
                       append_images=frames[1:],
                       duration=duration_ms,
                       loop=0,
                       optimize=True)

        self.log("GIF 生成完成。")


# Example usage (for testing standalone)
if __name__ == '__main__':
    # Mock LanguageManager for standalone testing
    class MockLangManager:
        def get_text(self, key, default=''):
            # Simple mock: return key or default
            texts = {
                'select_mp4_file': 'Select MP4 File',
                'browse': 'Browse',
                'select_gif_output': 'Select GIF Output',
                'start_conversion': 'Start Conversion',
                'log': 'Log',
                'title': 'Info',
                'task_running': 'Task is already running.',
                'error': 'Error',
                'invalid_mp4_path': 'Invalid MP4 file path.',
                'invalid_gif_path': 'Invalid GIF output path.',
                'output_is_directory': 'Output path is a directory.',
                'processing': 'Processing...',
                'select_mp4_file': 'Select MP4 File',
                'browse': 'Browse',
                'select_gif_output': 'Select GIF Output',
                'total_frames': 'Total Frames:',
                'compression_ratio': 'Compression Ratio:',
                'compression_ratio_desc': '(e.g., 2 means process every 2nd frame)',
                'start_conversion': 'Start Conversion',
                'log': 'Log',
                'title': 'Info',
                'task_running': 'Task is already running.',
                'error': 'Error',
                'invalid_mp4_path': 'Invalid MP4 file path.',
                'invalid_gif_path': 'Invalid GIF output path.',
                'output_is_directory': 'Output path is a directory.',
                'processing': 'Processing...',
                'conversion_started': 'Conversion started: {input} to {output}',
                'conversion_success': 'Conversion successful: {output}',
                'conversion_error': 'Conversion error: {error}',
                'error_opening_video': 'Error opening video file: {file}',
                'total_frames_loaded': 'Total frames loaded: {frames}',
                'error_loading_video_info': 'Error loading video info: {error}',
                'invalid_compression_ratio': 'Invalid compression ratio. Using 1 (no compression).',
                'video_info': 'Video Info - FPS: {fps}, Total Frames: {total_frames}, Compression Ratio: {compression}',
                'processing_frame': 'Processing frame {frame_num}',
                'no_frames_read': 'No frames read from video.',
                'generating_gif': 'Read {num_frames} frames, starting GIF generation...',
                'gif_generation_complete': 'GIF generation complete.'
            }
            return texts.get(key, default.format(key=key)) # Basic formatting if needed
        def get_supported_languages(self):
            return {'en': 'English'}
        def get_current_language(self):
            return 'en'
        def load_language(self, lang_code):
            return True

    root = ctk.CTk()
    root.title("MP4 to GIF Test")
    root.geometry("600x400")
    lang_manager = MockLangManager()
    frame = Mp4ToGifFrame(root, lang_manager)
    frame.pack(expand=True, fill="both", padx=10, pady=10)
    root.mainloop()
