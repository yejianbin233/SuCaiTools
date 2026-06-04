import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os
import glob
from pathlib import Path
import threading
import json
import shutil
from typing import Optional, List, Dict, Tuple
import requests
import re
import time
from tkinter import messagebox
from tkinter import ttk
import random
import string
from datetime import datetime

class RestoreWindow(ctk.CTkToplevel):
    """恢复文件窗口"""
    def __init__(self, master, folder_path, refresh_callback):
        super().__init__(master)
        self.folder_path = folder_path
        self.refresh_callback = refresh_callback
        self.title("恢复删除的文件")
        self.geometry("600x400")
        
        self.create_widgets()
        self.load_temp_folders()
    
    def create_widgets(self):
        """创建恢复窗口组件"""
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="选择要恢复的删除批次:", font=("Arial", 16)).pack(pady=(0, 10))
        
        # 列表容器
        list_frame = ctk.CTkFrame(main_frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # 滚动条
        self.listbox_frame = ctk.CTkScrollableFrame(list_frame)
        self.listbox_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 按钮区域
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(0, 10))
        
        self.refresh_btn = ctk.CTkButton(
            button_frame,
            text="刷新",
            width=80,
            command=self.load_temp_folders
        )
        self.refresh_btn.pack(side="left", padx=5)
        
        self.restore_btn = ctk.CTkButton(
            button_frame,
            text="恢复选中",
            width=100,
            command=self.restore_selected,
            fg_color="#388E3C",
            hover_color="#2E7D32"
        )
        self.restore_btn.pack(side="left", padx=5)
        
        self.delete_btn = ctk.CTkButton(
            button_frame,
            text="永久删除",
            width=100,
            command=self.permanent_delete,
            fg_color="#D32F2F",
            hover_color="#B71C1C"
        )
        self.delete_btn.pack(side="left", padx=5)
        
        # 状态标签
        self.status_label = ctk.CTkLabel(main_frame, text="")
        self.status_label.pack()
    
    def load_temp_folders(self):
        """加载临时文件夹列表"""
        # 清空列表
        for widget in self.listbox_frame.winfo_children():
            widget.destroy()
        
        temp_folder = os.path.join(self.folder_path, "deleted_temp")
        if not os.path.exists(temp_folder):
            self.status_label.configure(text="临时文件夹为空")
            return
        
        # 获取所有子文件夹
        subfolders = []
        for item in os.listdir(temp_folder):
            item_path = os.path.join(temp_folder, item)
            if os.path.isdir(item_path):
                subfolders.append(item_path)
        
        if not subfolders:
            self.status_label.configure(text="临时文件夹为空")
            return
        
        # 按修改时间排序
        subfolders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # 创建选择列表
        self.selected_vars = []
        for folder_path in subfolders:
            folder_name = os.path.basename(folder_path)
            create_time = time.ctime(os.path.getmtime(folder_path))
            
            # 统计文件数量
            file_count = len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
            
            var = ctk.BooleanVar(value=False)
            self.selected_vars.append(var)
            
            checkbox = ctk.CTkCheckBox(
                self.listbox_frame,
                text=f"{folder_name} ({create_time}) - {file_count} 个文件",
                variable=var
            )
            checkbox.pack(anchor="w", pady=2)
        
        self.status_label.configure(text=f"找到 {len(subfolders)} 个删除批次")
    
    def restore_selected(self):
        """恢复选中的文件夹"""
        selected_folders = []
        for i, var in enumerate(self.selected_vars):
            if var.get():
                selected_folders.append(i)
        
        if not selected_folders:
            messagebox.showwarning("警告", "请选择要恢复的文件夹")
            return
        
        if not messagebox.askyesno("确认恢复", f"确定要恢复 {len(selected_folders)} 个文件夹中的文件吗？"):
            return
        
        # 获取临时文件夹路径
        temp_folder = os.path.join(self.folder_path, "deleted_temp")
        
        restored_files = 0
        for folder_index in selected_folders:
            # 获取文件夹路径
            folder_path = os.path.join(temp_folder, os.listdir(temp_folder)[folder_index])
            
            # 移动文件回原目录
            for filename in os.listdir(folder_path):
                src_path = os.path.join(folder_path, filename)
                dst_path = os.path.join(self.folder_path, filename)
                
                try:
                    shutil.move(src_path, dst_path)
                    restored_files += 1
                except Exception as e:
                    self.status_label.configure(text=f"恢复 {filename} 失败: {str(e)}")
        
        # 如果文件夹为空，删除文件夹
        for folder_index in selected_folders:
            folder_path = os.path.join(temp_folder, os.listdir(temp_folder)[folder_index])
            if not os.listdir(folder_path):
                os.rmdir(folder_path)
        
        # 刷新
        self.load_temp_folders()
        if hasattr(self.refresh_callback, '__call__'):
            self.refresh_callback()
        
        messagebox.showinfo("恢复完成", f"已恢复 {restored_files} 个文件")
    
    def permanent_delete(self):
        """永久删除选中的文件夹"""
        if not messagebox.askyesno("确认删除", "警告：这将永久删除选中的文件夹及其所有内容！\n此操作不可恢复！"):
            return
        
        selected_folders = []
        for i, var in enumerate(self.selected_vars):
            if var.get():
                selected_folders.append(i)
        
        if not selected_folders:
            messagebox.showwarning("警告", "请选择要删除的文件夹")
            return
        
        temp_folder = os.path.join(self.folder_path, "deleted_temp")
        deleted_count = 0
        
        for folder_index in selected_folders:
            folder_path = os.path.join(temp_folder, os.listdir(temp_folder)[folder_index])
            try:
                shutil.rmtree(folder_path)
                deleted_count += 1
            except Exception as e:
                self.status_label.configure(text=f"删除 {os.path.basename(folder_path)} 失败: {str(e)}")
        
        # 刷新列表
        self.load_temp_folders()
        
        messagebox.showinfo("删除完成", f"已永久删除 {deleted_count} 个文件夹")