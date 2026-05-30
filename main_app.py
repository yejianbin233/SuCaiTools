import customtkinter as ctk
from tkinter import ttk
from language_manager import LanguageManager
from rename_images_gui import RenamerFrame # Import the refactored frame
from image_resizer_gui import ImageResizerFrame # Import the image resizer frame
from video2png_gui import Video2PngFrame # Import the video to png frame
from mp4_to_gif_gui import Mp4ToGifFrame # Import the new MP4 to GIF frame
from image_stitcher_gui import ImageStitcherFrame # Import the image stitcher frame
from image_processor_gui import ImageProcessorFrame # Import the new image processor frame
from jpg_to_png_gui import JpgToPngFrame # Import the new JPG to PNG frame
from image_rotator_gui import ImageRotatorFrame # Import the new image rotator frame
from caption_editor_frame_gui import CaptionEditorFrame # 导入图片标注

import webbrowser
# Import other tool modules here later

import tkinterdnd2

class MainApplication(ctk.CTk):
    def __init__(self):
        super().__init__()
        # 初始化TkinterDnD，但不使用多重继承
        self.TkdndVersion = tkinterdnd2.TkinterDnD._require(self)
        
        self.lang_manager = LanguageManager()

        self.configure(bg="#242424")      # 设置主窗口背景为深灰色
 
        self.title(self.lang_manager.get_text('main_title')) # Assuming 'main_title' key exists
        self.geometry("800x600")

        # --- Language Selector --- (Moved to main app)
        self.create_language_selector()

        # --- Tab View --- 
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Add tabs for each tool
        self.renamer_tab_name = self.lang_manager.get_text('tab_rename_images')
        self.resizer_tab_name = self.lang_manager.get_text('tab_resize_images')
        self.video2png_tab_name = self.lang_manager.get_text('tab_video_to_png') # Get initial name
        self.mp4_to_gif_tab_name = self.lang_manager.get_text('tab_mp4_to_gif') # Get initial name for new tab
        self.stitcher_tab_name = self.lang_manager.get_text('tab_image_stitcher') # Get initial name for image stitcher tab
        self.image_processor_tab_name = self.lang_manager.get_text('tab_image_processor') # Get initial name for image processor tab
        self.jpg_to_png_tab_name = self.lang_manager.get_text('tab_jpg_to_png') # Get initial name for JPG to PNG tab
        self.image_rotator_tab_name = self.lang_manager.get_text('tab_image_rotator') # Get initial name for image rotator tab
        self.caption_editor_tab_name = self.lang_manager.get_text('tab_caption_editor') # caption

        self.tab_view.add(self.renamer_tab_name)
        self.tab_view.add(self.resizer_tab_name)
        self.tab_view.add(self.video2png_tab_name)
        self.tab_view.add(self.mp4_to_gif_tab_name) # Add the new tab
        self.tab_view.add(self.stitcher_tab_name) # Add the image stitcher tab
        self.tab_view.add(self.image_processor_tab_name) # Add the new image processor tab
        self.tab_view.add(self.jpg_to_png_tab_name) # Add the new JPG to PNG tab
        self.tab_view.add(self.image_rotator_tab_name) # Add the new image rotator tab
        self.tab_view.add(self.caption_editor_tab_name) # add caption
        # self.tab_view.add("Tool 4")

        # --- Embed Tool GUIs ---
        # Get the actual tab frames using the translated names
        self.renamer_tab_frame = self.tab_view.tab(self.renamer_tab_name)
        self.resizer_tab_frame = self.tab_view.tab(self.resizer_tab_name)
        self.video2png_tab_frame = self.tab_view.tab(self.video2png_tab_name)
        self.mp4_to_gif_tab_frame = self.tab_view.tab(self.mp4_to_gif_tab_name) # Get the new tab frame
        self.stitcher_tab_frame = self.tab_view.tab(self.stitcher_tab_name) # Get the image stitcher tab frame
        self.image_processor_tab_frame = self.tab_view.tab(self.image_processor_tab_name) # Get the new image processor tab frame
        self.jpg_to_png_tab_frame = self.tab_view.tab(self.jpg_to_png_tab_name) # Get the JPG to PNG tab frame
        self.image_rotator_tab_frame = self.tab_view.tab(self.image_rotator_tab_name) # Get the image rotator tab frame
        self.caption_editor_tab_frame = self.tab_view.tab(self.caption_editor_tab_name) # caption

        # Instantiate and pack the RenamerFrame into its tab
        self.renamer_app = RenamerFrame(self.renamer_tab_frame, self.lang_manager)
        self.renamer_app.pack(expand=True, fill="both")

        # Instantiate and pack the ImageResizerFrame into its tab
        self.resizer_app = ImageResizerFrame(self.resizer_tab_frame, self.lang_manager)
        self.resizer_app.pack(expand=True, fill="both")

        # Instantiate and pack the Video2PngFrame into its tab
        self.video2png_app = Video2PngFrame(self.video2png_tab_frame, self.lang_manager)
        self.video2png_app.pack(expand=True, fill="both")

        # Instantiate and pack the Mp4ToGifFrame into its tab
        self.mp4_to_gif_app = Mp4ToGifFrame(self.mp4_to_gif_tab_frame, self.lang_manager)
        self.mp4_to_gif_app.pack(expand=True, fill="both")

        # Instantiate and pack the ImageStitcherFrame into its tab
        self.stitcher_app = ImageStitcherFrame(self.stitcher_tab_frame, self.lang_manager)
        self.stitcher_app.pack(expand=True, fill="both")

        # Instantiate and pack the ImageProcessorFrame into its tab
        self.image_processor_app = ImageProcessorFrame(self.image_processor_tab_frame, self.lang_manager)
        self.image_processor_app.pack(expand=True, fill="both")

        # Instantiate and pack the JpgToPngFrame into its tab
        self.jpg_to_png_app = JpgToPngFrame(self.jpg_to_png_tab_frame, self.lang_manager)
        self.jpg_to_png_app.pack(expand=True, fill="both")

        # Instantiate and pack the ImageRotatorFrame into its tab
        self.image_rotator_app = ImageRotatorFrame(self.image_rotator_tab_frame, self.lang_manager)
        self.image_rotator_app.pack(expand=True, fill="both")

        # caption
        self.caption_editor_app = CaptionEditorFrame(self.caption_editor_tab_frame, self.lang_manager)
        self.caption_editor_app.pack(expand=True, fill="both")

        # GitHub 仓库地址
        self.github_label = ctk.CTkLabel(self, text="GitHub: https://github.com/dependon/sucaitools", cursor="hand2", text_color="#78e46f")
        self.github_label.pack(side="bottom", pady=5)
        self.github_label.bind("<Button-1>", lambda event: webbrowser.open_new("https://github.com/dependon/sucaitools"))

        # Add other tool frames here

    def create_language_selector(self):
        languages = self.lang_manager.get_supported_languages()
        current_lang = self.lang_manager.get_current_language()
        current_lang_name = languages.get(current_lang, 'English') # Default to English name if not found

        # Use CTk components if desired, or standard ttk for consistency with existing code
        # For now, using ttk to match rename_images_gui
        lang_frame = ctk.CTkFrame(self) # Use CTkFrame for consistency with main window
        lang_frame.pack(side="top", fill="x", padx=10, pady=(10, 0))

        lang_label = ctk.CTkLabel(lang_frame, text=self.lang_manager.get_text('language') + ":")
        lang_label.pack(side="left", padx=(0, 5))

        self.lang_var = ctk.StringVar(value=current_lang_name)
        self.lang_name_to_code = {v: k for k, v in languages.items()}

        # Using CTkComboBox
        self.lang_combobox = ctk.CTkComboBox(lang_frame, 
                                             variable=self.lang_var, 
                                             values=list(languages.values()), 
                                             state='readonly', 
                                             command=self.on_language_change)
        self.lang_combobox.pack(side="left")

    def on_language_change(self, choice):
        selected_lang_name = self.lang_var.get()
        selected_lang_code = self.lang_name_to_code.get(selected_lang_name)
        if selected_lang_code and self.lang_manager.load_language(selected_lang_code):
            self.restart_application()
        else:
            print(f"Could not switch language to: {selected_lang_name}") # Add logging

    def restart_application(self):
        """更新应用程序的语言设置"""
        try:
            # 在打包环境下，直接更新UI文本而不是重启应用程序
            self.update_ui_texts()
        except Exception as e:
            print(f"更新界面文本时出错：{str(e)}")
            # 如果更新失败，尝试重新加载默认语言
            self.lang_manager.load_language('en')
            self.update_ui_texts()

    def update_ui_texts(self):
        # Update main window title
        self.title(self.lang_manager.get_text('main_title'))

        # Update language selector label
        try:
            lang_frame = self.winfo_children()[0]
            lang_label = lang_frame.winfo_children()[0]
            if isinstance(lang_label, ctk.CTkLabel):
                lang_label.configure(text=self.lang_manager.get_text('language') + ":")
        except (IndexError, AttributeError) as e:
            print(f"Error finding language label: {e}")

        # Get new tab names
        new_renamer_name = self.lang_manager.get_text('tab_rename_images')
        new_resizer_name = self.lang_manager.get_text('tab_resize_images')
        new_video2png_name = self.lang_manager.get_text('tab_video_to_png')
        new_mp4_to_gif_name = self.lang_manager.get_text('tab_mp4_to_gif') # Get new name for the tab
        new_stitcher_name = self.lang_manager.get_text('tab_image_stitcher') # Get new name for the image stitcher tab
        new_image_processor_name = self.lang_manager.get_text('tab_image_processor') # Get new name for the image processor tab
        new_jpg_to_png_name = self.lang_manager.get_text('tab_jpg_to_png') # Get new name for the JPG to PNG tab
        new_image_rotator_name = self.lang_manager.get_text('tab_image_rotator') # Get new name for the image rotator tab
        # 找到更新标签名的地方，添加：
        new_caption_editor_name = self.lang_manager.get_text('tab_caption_editor')

        # Store current tab for later
        current_tab = self.tab_view.get()

        # First unpack all tool frames
        if hasattr(self, 'renamer_app'):
            self.renamer_app.pack_forget()
            self.renamer_app.destroy()
            del self.renamer_app
        if hasattr(self, 'resizer_app'):
            self.resizer_app.pack_forget()
            self.resizer_app.destroy()
            del self.resizer_app
        if hasattr(self, 'video2png_app'):
            self.video2png_app.pack_forget()
            self.video2png_app.destroy()
            del self.video2png_app
        if hasattr(self, 'mp4_to_gif_app'): # Clean up new frame
            self.mp4_to_gif_app.pack_forget()
            self.mp4_to_gif_app.destroy()
            del self.mp4_to_gif_app
        if hasattr(self, 'stitcher_app'): # Clean up image stitcher frame
            self.stitcher_app.pack_forget()
            self.stitcher_app.destroy()
            del self.stitcher_app
        if hasattr(self, 'image_processor_app'): # Clean up image processor frame
            self.image_processor_app.pack_forget()
            self.image_processor_app.destroy()
            del self.image_processor_app
        if hasattr(self, 'jpg_to_png_app'): # Clean up JPG to PNG frame
            self.jpg_to_png_app.pack_forget()
            self.jpg_to_png_app.destroy()
            del self.jpg_to_png_app
        if hasattr(self, 'image_rotator_app'): # Clean up image rotator frame
            self.image_rotator_app.pack_forget()
            self.image_rotator_app.destroy()
            del self.image_rotator_app

        # 清理旧的帧（在清理其他帧的地方添加）
        if hasattr(self, 'caption_editor_app'):
            self.caption_editor_app.pack_forget()
            self.caption_editor_app.destroy()
            del self.caption_editor_app

        # Remove all existing tabs
        for tab in self.tab_view._tab_dict.copy():
            self.tab_view._tab_dict[tab].grid_remove()
            self.tab_view._tab_dict.pop(tab)

        # Clear segmented button values
        self.tab_view._segmented_button.configure(values=[])

        # Add tabs with new names
        self.tab_view.add(new_renamer_name)
        self.tab_view.add(new_resizer_name)
        self.tab_view.add(new_video2png_name)
        self.tab_view.add(new_mp4_to_gif_name) # Add new tab with updated name
        self.tab_view.add(new_stitcher_name) # Add new image stitcher tab with updated name
        self.tab_view.add(new_image_processor_name) # Add new image processor tab with updated name
        self.tab_view.add(new_jpg_to_png_name) # Add new JPG to PNG tab with updated name
        self.tab_view.add(new_image_rotator_name) # Add new image rotator tab with updated name
        # 重新添加标签页
        self.tab_view.add(new_caption_editor_name)

        # Update stored names
        self.renamer_tab_name = new_renamer_name
        self.resizer_tab_name = new_resizer_name
        self.video2png_tab_name = new_video2png_name
        self.mp4_to_gif_tab_name = new_mp4_to_gif_name # Store new tab name
        self.stitcher_tab_name = new_stitcher_name # Store new image stitcher tab name
        self.image_processor_tab_name = new_image_processor_name # Store new image processor tab name
        self.jpg_to_png_tab_name = new_jpg_to_png_name # Store new JPG to PNG tab name
        self.image_rotator_tab_name = new_image_rotator_name # Store new image rotator tab name
        self.caption_editor_tab_name = new_caption_editor_name

        # Get new tab frames and ensure they are ready
        self.renamer_tab_frame = self.tab_view.tab(new_renamer_name)
        self.resizer_tab_frame = self.tab_view.tab(new_resizer_name)
        self.video2png_tab_frame = self.tab_view.tab(new_video2png_name)
        self.mp4_to_gif_tab_frame = self.tab_view.tab(new_mp4_to_gif_name) # Get new tab frame
        self.stitcher_tab_frame = self.tab_view.tab(new_stitcher_name) # Get new image stitcher tab frame
        self.image_processor_tab_frame = self.tab_view.tab(new_image_processor_name) # Get new image processor tab frame
        self.jpg_to_png_tab_frame = self.tab_view.tab(new_jpg_to_png_name) # Get new JPG to PNG tab frame
        self.image_rotator_tab_frame = self.tab_view.tab(new_image_rotator_name) # Get new image rotator tab frame
        self.caption_editor_tab_frame = self.tab_view.tab(new_caption_editor_name)


        # Update the UI before repacking
        self.update()

        # Re-pack the tool frames into their new tabs
        # 重新实例化并pack
        self.renamer_app = RenamerFrame(self.renamer_tab_frame, self.lang_manager)
        self.renamer_app.pack(expand=True, fill="both")
        self.renamer_app.update_ui_texts()

        self.resizer_app = ImageResizerFrame(self.resizer_tab_frame, self.lang_manager)
        self.resizer_app.pack(expand=True, fill="both")
        self.resizer_app.update_ui_texts()

        self.video2png_app = Video2PngFrame(self.video2png_tab_frame, self.lang_manager)
        self.video2png_app.pack(expand=True, fill="both")
        self.video2png_app.update_ui_texts()

        # Re-instantiate and pack the new frame
        self.mp4_to_gif_app = Mp4ToGifFrame(self.mp4_to_gif_tab_frame, self.lang_manager)
        self.mp4_to_gif_app.pack(expand=True, fill="both")
        self.mp4_to_gif_app.update_ui_texts()

        # Re-instantiate and pack the image stitcher frame
        self.stitcher_app = ImageStitcherFrame(self.stitcher_tab_frame, self.lang_manager)
        self.stitcher_app.pack(expand=True, fill="both")
        self.stitcher_app.update_ui_texts()

        # Re-instantiate and pack the image processor frame
        self.image_processor_app = ImageProcessorFrame(self.image_processor_tab_frame, self.lang_manager)
        self.image_processor_app.pack(expand=True, fill="both")
        self.image_processor_app.update_ui_texts()

        # Re-instantiate and pack the JPG to PNG frame
        self.jpg_to_png_app = JpgToPngFrame(self.jpg_to_png_tab_frame, self.lang_manager)
        self.jpg_to_png_app.pack(expand=True, fill="both")
        self.jpg_to_png_app.update_ui_texts()

        # Re-instantiate and pack the image rotator frame
        self.image_rotator_app = ImageRotatorFrame(self.image_rotator_tab_frame, self.lang_manager)
        self.image_rotator_app.pack(expand=True, fill="both")
        self.image_rotator_app.update_ui_texts()

        # 重新实例化
        self.caption_editor_app = CaptionEditorFrame(self.caption_editor_tab_frame, self.lang_manager)
        self.caption_editor_app.pack(expand=True, fill="both")
        self.caption_editor_app.update_ui_texts()

        # Try to set the previously selected tab
        try:
            if current_tab == self.renamer_tab_name:
                self.tab_view.set(new_renamer_name)
            elif current_tab == self.resizer_tab_name:
                self.tab_view.set(new_resizer_name)
            elif current_tab == self.video2png_tab_name:
                self.tab_view.set(new_video2png_name)
            elif current_tab == self.mp4_to_gif_tab_name: # Handle setting the new tab
                self.tab_view.set(new_mp4_to_gif_name)
            elif current_tab == self.stitcher_tab_name: # Handle setting the image stitcher tab
                self.tab_view.set(new_stitcher_name)
            elif current_tab == self.image_processor_tab_name: # Handle setting the image processor tab
                self.tab_view.set(new_image_processor_name)
            elif current_tab == self.jpg_to_png_tab_name: # Handle setting the JPG to PNG tab
                self.tab_view.set(new_jpg_to_png_name)
            elif current_tab == self.image_rotator_tab_name: # Handle setting the image rotator tab
                self.tab_view.set(new_image_rotator_name)
            elif current_tab == self.caption_editor_tab_name: # Handle setting the image rotator tab
                self.tab_view.set(new_caption_editor_name)
        except Exception as e:
            print(f"Error setting current tab: {e}")
            # Default to first tab if there's an error
            self.tab_view.set(new_renamer_name)

    def destroy(self):
        """重写destroy方法，确保正确清理资源"""
        try:
            # 先清理所有子组件
            for widget in self.winfo_children():
                if hasattr(widget, 'destroy'):
                    try:
                        widget.destroy()
                    except Exception as e:
                        print(f"清理子组件时出错: {str(e)}")
            
            # 手动清理可能导致问题的命令和回调
            try:
                for command in list(self.tk.call('after', 'info')):
                    self.after_cancel(command)
            except Exception as e:
                print(f"清理after命令时出错: {str(e)}")
                
            # 最后调用父类的destroy方法
            super().destroy()
        except Exception as e:
            print(f"销毁窗口时出错: {str(e)}")

if __name__ == "__main__":
    app = MainApplication()
    app.protocol("WM_DELETE_WINDOW", app.destroy)
    app.mainloop()
