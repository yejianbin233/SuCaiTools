import customtkinter as ctk
import json
import os
import tkinter as tk
from tkinter import messagebox
import requests
import threading


class ConfigDialog(ctk.CTkToplevel):
    """配置对话框"""
    
    def __init__(self, parent, translator_config, save_callback):
        super().__init__(parent)
        
        self.translator_config = translator_config
        self.save_callback = save_callback
        self.parent = parent
        
        self.title("翻译服务配置")
        self.geometry("600x600")
        self.resizable(True, True)
        
        # 设置模态置顶对话框
        self.transient(parent)
        self.grab_set()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        
        # 居中显示
        self.update_idletasks()
        width = 600
        height = 600
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        self.create_widgets()
        
        # 绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        """创建界面组件"""
        # 创建滚动框架
        scroll_frame = ctk.CTkScrollableFrame(self)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ctk.CTkLabel(
            scroll_frame, 
            text="翻译服务配置",
            font=("Arial", 20, "bold")
        )
        title_label.pack(pady=(0, 20))
        
        # 翻译服务选择
        service_frame = ctk.CTkFrame(scroll_frame)
        service_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            service_frame, 
            text="默认翻译服务:",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(10, 5), padx=10)
        
        self.service_var = ctk.StringVar(value=self.translator_config.get('current_service', 'google'))
        
        # 创建服务选项
        services = [
            ("谷歌翻译 (免费)", "google"),
            ("百度翻译 (需要API)", "baidu"),
            ("腾讯翻译 (需要API)", "tencent"),
            ("有道翻译 (需要API)", "youdao"),
            ("OpenAI (需要API)", "openai"),
            ("DeepSeek (需要API)", "deepseek"),
            ("通义千问 (需要API)", "qwen"),
        ]
        
        for text, value in services:
            ctk.CTkRadioButton(
                service_frame,
                text=text,
                variable=self.service_var,
                value=value,
                command=self.on_service_changed
            ).pack(anchor="w", padx=20, pady=2)
        
        # 百度翻译配置
        self.baidu_frame = ctk.CTkFrame(scroll_frame)
        self.baidu_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            self.baidu_frame, 
            text="百度翻译配置",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", pady=(10, 5), padx=10)
        
        ctk.CTkLabel(self.baidu_frame, text="App ID:").pack(anchor="w", padx=20)
        self.baidu_appid_entry = ctk.CTkEntry(self.baidu_frame, width=300)
        self.baidu_appid_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.baidu_appid_entry.insert(0, self.translator_config.get('baidu_appid', ''))
        
        ctk.CTkLabel(self.baidu_frame, text="密钥:").pack(anchor="w", padx=20)
        self.baidu_key_entry = ctk.CTkEntry(self.baidu_frame, width=300, show="*")
        self.baidu_key_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.baidu_key_entry.insert(0, self.translator_config.get('baidu_key', ''))
        
        # 腾讯翻译配置
        self.tencent_frame = ctk.CTkFrame(scroll_frame)
        self.tencent_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            self.tencent_frame, 
            text="腾讯翻译配置",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", pady=(10, 5), padx=10)
        
        ctk.CTkLabel(self.tencent_frame, text="SecretId:").pack(anchor="w", padx=20)
        self.tencent_secret_id_entry = ctk.CTkEntry(self.tencent_frame, width=300)
        self.tencent_secret_id_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.tencent_secret_id_entry.insert(0, self.translator_config.get('tencent_secret_id', ''))
        
        ctk.CTkLabel(self.tencent_frame, text="SecretKey:").pack(anchor="w", padx=20)
        self.tencent_secret_key_entry = ctk.CTkEntry(self.tencent_frame, width=300, show="*")
        self.tencent_secret_key_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.tencent_secret_key_entry.insert(0, self.translator_config.get('tencent_secret_key', ''))
        
        ctk.CTkLabel(self.tencent_frame, text="区域 (Region):").pack(anchor="w", padx=20)
        self.tencent_region_var = ctk.StringVar(value=self.translator_config.get('tencent_region', 'ap-beijing'))
        tencent_region_combo = ctk.CTkOptionMenu(
            self.tencent_frame,
            values=['ap-beijing', 'ap-shanghai', 'ap-guangzhou', 'ap-chengdu'],
            variable=self.tencent_region_var,
            width=200
        )
        tencent_region_combo.pack(anchor="w", padx=20, pady=(0, 10))
        
        # 有道翻译配置
        self.youdao_frame = ctk.CTkFrame(scroll_frame)
        self.youdao_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            self.youdao_frame, 
            text="有道翻译配置",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", pady=(10, 5), padx=10)
        
        ctk.CTkLabel(self.youdao_frame, text="App Key:").pack(anchor="w", padx=20)
        self.youdao_appkey_entry = ctk.CTkEntry(self.youdao_frame, width=300)
        self.youdao_appkey_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.youdao_appkey_entry.insert(0, self.translator_config.get('youdao_appkey', ''))
        
        ctk.CTkLabel(self.youdao_frame, text="App Secret:").pack(anchor="w", padx=20)
        self.youdao_secret_entry = ctk.CTkEntry(self.youdao_frame, width=300, show="*")
        self.youdao_secret_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.youdao_secret_entry.insert(0, self.translator_config.get('youdao_secret', ''))
        
        # AI翻译配置
        self.ai_frame = ctk.CTkFrame(scroll_frame)
        self.ai_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            self.ai_frame, 
            text="AI翻译配置 (OpenAI/DeepSeek/Qwen)",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", pady=(10, 5), padx=10)
        
        ctk.CTkLabel(self.ai_frame, text="API密钥:").pack(anchor="w", padx=20)
        self.ai_api_key_entry = ctk.CTkEntry(self.ai_frame, width=300, show="*")
        self.ai_api_key_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.ai_api_key_entry.insert(0, self.translator_config.get('ai_api_key', ''))
        
        ctk.CTkLabel(self.ai_frame, text="API地址 (可选):").pack(anchor="w", padx=20)
        self.ai_api_base_entry = ctk.CTkEntry(self.ai_frame, width=300)
        self.ai_api_base_entry.pack(fill="x", padx=20, pady=(0, 10))
        self.ai_api_base_entry.insert(0, self.translator_config.get('ai_api_base', ''))
        
        # 测试按钮
        test_frame = ctk.CTkFrame(scroll_frame)
        test_frame.pack(fill="x", pady=(0, 10))
        
        self.test_btn = ctk.CTkButton(
            test_frame,
            text="测试当前服务",
            command=self.test_current_service,
            width=120
        )
        self.test_btn.pack(side="left", padx=(20, 10), pady=10)
        
        self.test_result_label = ctk.CTkLabel(
            test_frame,
            text="",
            text_color="gray"
        )
        self.test_result_label.pack(side="left", padx=10, pady=10)
        
        # 按钮区域
        button_frame = ctk.CTkFrame(scroll_frame)
        button_frame.pack(fill="x", pady=20)
        
        self.save_btn = ctk.CTkButton(
            button_frame,
            text="保存配置",
            command=self.save_config,
            width=100
        )
        self.save_btn.pack(side="right", padx=5)
        
        self.cancel_btn = ctk.CTkButton(
            button_frame,
            text="取消",
            command=self.on_closing,
            width=100
        )
        self.cancel_btn.pack(side="right", padx=5)
        
        # 初始化框架显示状态
        self.on_service_changed()
    
    def on_service_changed(self):
        """服务选择变化时的回调"""
        current_service = self.service_var.get()
        
        # 隐藏所有配置框架
        self.baidu_frame.pack_forget()
        self.tencent_frame.pack_forget()
        self.youdao_frame.pack_forget()
        self.ai_frame.pack_forget()
        
        # 根据当前服务显示对应的配置框架
        if current_service == 'baidu':
            self.baidu_frame.pack(fill="x", pady=(0, 10))
        elif current_service == 'tencent':
            self.tencent_frame.pack(fill="x", pady=(0, 10))
        elif current_service == 'youdao':
            self.youdao_frame.pack(fill="x", pady=(0, 10))
        elif current_service in ['openai', 'deepseek', 'qwen']:
            self.ai_frame.pack(fill="x", pady=(0, 10))
    
    def test_current_service(self):
        """测试当前选择的翻译服务"""
        current_service = self.service_var.get()
        
        # 创建临时配置
        temp_config = self.get_current_config()
        
        def test_thread():
            try:
                # 在主线程中更新按钮状态
                self.after(0, lambda: self.test_btn.configure(state="disabled", text="测试中..."))
                self.after(0, lambda: self.test_result_label.configure(text="正在测试...", text_color="yellow"))
                
                # 根据服务类型进行测试
                if current_service == 'google':
                    # 谷歌翻译无需配置，直接测试
                    result = "谷歌翻译无需API密钥，可直接使用"
                    success = True
                    
                elif current_service == 'baidu':
                    # 测试百度翻译
                    from caption.translator_manager import BaiduTranslator
                    translator = BaiduTranslator(temp_config)
                    result = translator.translate_to_chinese("hello")
                    if "hello" not in result.lower() and len(result) > 0:
                        success = True
                    else:
                        success = False
                        
                elif current_service == 'tencent':
                    # 测试腾讯翻译
                    from caption.translator_manager import TencentTranslator
                    translator = TencentTranslator(temp_config)
                    result = translator.translate_to_chinese("hello")
                    if "hello" not in result.lower() and len(result) > 0:
                        success = True
                    else:
                        success = False
                        
                elif current_service == 'youdao':
                    # 测试有道翻译
                    from caption.translator_manager import YoudaoTranslator
                    translator = YoudaoTranslator(temp_config)
                    result = translator.translate_to_chinese("hello")
                    if "hello" not in result.lower() and len(result) > 0:
                        success = True
                    else:
                        success = False
                        
                elif current_service in ['openai', 'deepseek', 'qwen']:
                    # 测试AI翻译
                    from caption.translator_manager import AITranslator
                    temp_config['ai_service'] = current_service
                    translator = AITranslator(temp_config)
                    result = translator.translate_to_chinese("hello")
                    if "hello" not in result.lower() and len(result) > 0:
                        success = True
                    else:
                        success = False
                else:
                    result = f"不支持的服务: {current_service}"
                    success = False
                
                # 在主线程中更新结果
                if success:
                    self.after(0, lambda: self.test_result_label.configure(
                        text=f"测试成功: {result[:50]}...", 
                        text_color="green"
                    ))
                else:
                    self.after(0, lambda: self.test_result_label.configure(
                        text=f"测试失败: {result[:100]}", 
                        text_color="red"
                    ))
                
            except Exception as e:
                error_msg = str(e)[:100]
                self.after(0, lambda: self.test_result_label.configure(
                    text=f"测试异常: {error_msg}", 
                    text_color="red"
                ))
            finally:
                # 恢复按钮状态
                self.after(0, lambda: self.test_btn.configure(state="normal", text="测试当前服务"))
        
        # 在新线程中执行测试
        thread = threading.Thread(target=test_thread, daemon=True)
        thread.start()
    
    def get_current_config(self):
        """获取当前配置"""
        config = {
            'current_service': self.service_var.get(),
        }
        
        # 百度翻译配置
        config['baidu_appid'] = self.baidu_appid_entry.get().strip()
        config['baidu_key'] = self.baidu_key_entry.get().strip()
        
        # 腾讯翻译配置
        config['tencent_secret_id'] = self.tencent_secret_id_entry.get().strip()
        config['tencent_secret_key'] = self.tencent_secret_key_entry.get().strip()
        config['tencent_region'] = self.tencent_region_var.get()
        
        # 有道翻译配置
        config['youdao_appkey'] = self.youdao_appkey_entry.get().strip()
        config['youdao_secret'] = self.youdao_secret_entry.get().strip()
        
        # AI翻译配置
        config['ai_api_key'] = self.ai_api_key_entry.get().strip()
        config['ai_api_base'] = self.ai_api_base_entry.get().strip()
        
        return config
    
    def save_config(self):
        """保存配置"""
        try:
            # 获取当前配置
            new_config = self.get_current_config()
            
            # 验证必填字段
            current_service = new_config['current_service']
            
            if current_service == 'baidu':
                if not new_config['baidu_appid'] or not new_config['baidu_key']:
                    messagebox.showwarning("警告", "百度翻译需要App ID和密钥")
                    return
                    
            elif current_service == 'tencent':
                if not new_config['tencent_secret_id'] or not new_config['tencent_secret_key']:
                    messagebox.showwarning("警告", "腾讯翻译需要SecretId和SecretKey")
                    return
                    
            elif current_service == 'youdao':
                if not new_config['youdao_appkey'] or not new_config['youdao_secret']:
                    messagebox.showwarning("警告", "有道翻译需要App Key和Secret")
                    return
                    
            elif current_service in ['openai', 'deepseek', 'qwen']:
                if not new_config['ai_api_key']:
                    messagebox.showwarning("警告", f"{current_service}翻译需要API密钥")
                    return
            
            # 更新配置
            self.translator_config.update(new_config)
            
            # 调用保存回调
            if self.save_callback:
                self.save_callback()
            
            messagebox.showinfo("成功", "配置已保存")
            self.on_closing()
            
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def on_closing(self):
        """关闭对话框"""
        self.grab_release()
        self.destroy()


def load_config():
    """加载配置文件"""
    config_paths = [
        "translator_config.json",
        os.path.join(os.path.expanduser("~"), ".translator_config.json"),
        os.path.join(os.path.dirname(__file__), "translator_config.json")
    ]
    
    default_config = {
        'current_service': 'google',
        'baidu_appid': '',
        'baidu_key': '',
        'tencent_secret_id': '',
        'tencent_secret_key': '',
        'tencent_region': 'ap-beijing',
        'youdao_appkey': '',
        'youdao_secret': '',
        'ai_api_key': '',
        'ai_api_base': '',
    }
    
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
                print(f"从 {path} 加载配置")
                break
            except Exception as e:
                print(f"加载配置文件 {path} 失败: {e}")
    
    return default_config


def save_config(config):
    """保存配置文件"""
    config_paths = [
        "translator_config.json",
        os.path.join(os.path.expanduser("~"), ".translator_config.json"),
    ]
    
    for path in config_paths:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"配置已保存到 {path}")
            return True
        except Exception as e:
            print(f"保存配置文件 {path} 失败: {e}")
    
    return False


if __name__ == "__main__":
    # 测试配置对话框
    root = ctk.CTk()
    root.title("测试配置对话框")
    root.geometry("400x300")
    
    config = load_config()
    
    def on_save():
        save_config(config)
        print("配置已保存")
    
    def open_config():
        dialog = ConfigDialog(root, config, on_save)
        root.wait_window(dialog)
    
    btn = ctk.CTkButton(root, text="打开配置", command=open_config)
    btn.pack(pady=50)
    
    root.mainloop()