import base64

import requests
import json
import hashlib
import random
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote

class BaseTranslator(ABC):
    """翻译器基类"""
    
    def __init__(self, config: dict):
        self.config = config
    
    @abstractmethod
    def translate_to_chinese(self, text: str) -> str:
        """翻译为中文"""
        pass
    
    @abstractmethod
    def translate_to_english(self, text: str) -> str:
        """翻译为英文"""
        pass


class BaiduTranslator(BaseTranslator):
    """百度翻译"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.appid = config.get('baidu_appid', '')
        self.key = config.get('baidu_key', '')
        self.api_url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """执行翻译"""
        if not self.appid or not self.key:
            raise ValueError("百度翻译需要配置appid和key")
        
        salt = str(random.randint(32768, 65536))
        sign_str = self.appid + text + salt + self.key
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        params = {
            'q': text,
            'from': from_lang,
            'to': to_lang,
            'appid': self.appid,
            'salt': salt,
            'sign': sign
        }
        
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            result = response.json()
            
            if 'trans_result' in result:
                translations = [item['dst'] for item in result['trans_result']]
                return ' '.join(translations)
            else:
                error_msg = result.get('error_msg', '未知错误')
                raise Exception(f"百度翻译错误: {error_msg}")
                
        except Exception as e:
            raise Exception(f"翻译请求失败: {str(e)}")
    
    def translate_to_chinese(self, text: str) -> str:
        return self.translate(text, 'en', 'zh')
    
    def translate_to_english(self, text: str) -> str:
        return self.translate(text, 'zh', 'en')


class YoudaoTranslator(BaseTranslator):
    """有道翻译"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.app_key = config.get('youdao_appkey', '')
        self.app_secret = config.get('youdao_secret', '')
        self.api_url = "https://openapi.youdao.com/api"
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        if not self.app_key or not self.app_secret:
            raise ValueError("有道翻译需要配置appkey和secret")
        
        salt = str(random.randint(1, 65536))
        sign_str = self.app_key + text + salt + self.app_secret
        sign = hashlib.sha256(sign_str.encode()).hexdigest()
        
        data = {
            'q': text,
            'from': from_lang,
            'to': to_lang,
            'appKey': self.app_key,
            'salt': salt,
            'sign': sign,
            'signType': 'v3'
        }
        
        try:
            response = requests.post(self.api_url, data=data, timeout=10)
            result = response.json()
            
            if 'translation' in result and result['translation']:
                return ' '.join(result['translation'])
            else:
                error_msg = result.get('errorCode', '未知错误')
                raise Exception(f"有道翻译错误: {error_msg}")
                
        except Exception as e:
            raise Exception(f"翻译请求失败: {str(e)}")
    
    def translate_to_chinese(self, text: str) -> str:
        return self.translate(text, 'en', 'zh-CHS')
    
    def translate_to_english(self, text: str) -> str:
        return self.translate(text, 'zh-CHS', 'en')

class TencentSDKTranslator(BaseTranslator):
    """使用腾讯云官方SDK的翻译器（推荐）"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.secret_id = config.get('secret_id', '')
        self.secret_key = config.get('secret_key', '')
        
        if not self.secret_id or not self.secret_key:
            raise ValueError("请配置腾讯翻译的SecretId和SecretKey")
        
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.tmt.v20180321 import tmt_client, models
            
            # 初始化凭证
            cred = credential.Credential(self.secret_id, self.secret_key)
            
            # 创建HTTP配置
            http_profile = HttpProfile()
            http_profile.endpoint = "tmt.tencentcloudapi.com"
            http_profile.reqTimeout = 10
            
            # 创建客户端配置
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            
            # 创建翻译客户端
            self.client = tmt_client.TmtClient(cred, "ap-beijing", client_profile)
            self.models = models
            
        except ImportError:
            raise ImportError(
                "请安装腾讯云SDK: pip install tencentcloud-sdk-python\n"
                "或使用其他翻译服务（如百度、谷歌）"
            )
        except Exception as e:
            raise Exception(f"初始化腾讯云客户端失败: {str(e)}")
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        """使用SDK进行翻译"""
        try:
            # 创建请求
            req = self.models.TextTranslateRequest()
            req.SourceText = text
            req.Source = from_lang
            req.Target = to_lang
            req.ProjectId = 0
            
            # 发送请求
            resp = self.client.TextTranslate(req)
            
            if hasattr(resp, 'TargetText'):
                return resp.TargetText.strip()
            else:
                raise Exception("腾讯翻译返回格式错误")
                
        except Exception as e:
            # 提供更友好的错误信息
            error_msg = str(e)
            if "AuthFailure" in error_msg:
                return "认证失败：请检查SecretId和SecretKey是否正确"
            elif "SignatureFailure" in error_msg:
                return "签名失败：请使用SDK版本或检查API密钥"
            else:
                return f"腾讯翻译失败: {error_msg}"
    
    def translate_to_chinese(self, text: str) -> str:
        return self.translate(text, 'en', 'zh')
    
    def translate_to_english(self, text: str) -> str:
        return self.translate(text, 'zh', 'en')
# class SimpleTencentTranslator(BaseTranslator):
#     """简易腾讯翻译API实现（推荐使用）
    
#     使用腾讯云机器翻译API，每月500万字符免费额度
#     需要先到腾讯云开通机器翻译服务：
#     1. 访问 https://console.cloud.tencent.com/tmt
#     2. 注册登录，完成实名认证
#     3. 创建API密钥（SecretId和SecretKey）
#     4. 免费额度：每月500万字符
    
#     注意：此实现使用简化的签名方法，适用于个人使用
#     """
    
#     def __init__(self, config: dict):
#         super().__init__(config)
#         self.secret_id = config.get('secret_id', '')
#         self.secret_key = config.get('secret_key', '')
#         self.region = config.get('tencent_region', 'ap-beijing')
        
#         # API端点
#         self.endpoint = "tmt.tencentcloudapi.com"
#         self.action = "TextTranslate"
#         self.version = "2018-03-21"
        
#         # 支持的语言
#         self.supported_languages = {
#             'zh': 'zh',       # 简体中文
#             'zh-TW': 'zh-TW', # 繁体中文
#             'en': 'en',       # 英文
#             'ja': 'ja',       # 日文
#             'ko': 'ko',       # 韩文
#             'fr': 'fr',       # 法文
#             'es': 'es',       # 西班牙文
#             'ru': 'ru',       # 俄文
#             'de': 'de',       # 德文
#         }
    
#     def _generate_signature_v1(self, text: str, source_lang: str, target_lang: str) -> dict:
#         """生成V1版本签名（兼容旧版）"""
#         import time
        
#         # 基础参数
#         params = {
#             'Action': self.action,
#             'Nonce': random.randint(1, 999999),
#             'ProjectId': 0,
#             'Region': self.region,
#             'SecretId': self.secret_id,
#             'SignatureMethod': 'HmacSHA256',
#             'Source': source_lang,
#             'SourceText': text,
#             'Target': target_lang,
#             'Timestamp': int(time.time()),
#             'Version': self.version,
#         }
        
#         # 排序参数
#         sorted_params = sorted(params.items(), key=lambda x: x[0])
        
#         # 构造签名字符串
#         sign_str = f"GET{self.endpoint}/?"
#         sign_str += '&'.join([f'{k}={quote(str(v), safe="")}' for k, v in sorted_params])
        
#         # 计算签名
#         import hmac
#         sign_key = self.secret_key.encode('utf-8')
#         signature = hmac.new(sign_key, sign_str.encode('utf-8'), hashlib.sha256).digest()
#         signature_base64 = base64.b64encode(signature).decode('utf-8')
        
#         params['Signature'] = signature_base64
#         return params
    
#     def translate(self, text: str, from_lang: str, to_lang: str) -> str:
#         """执行翻译"""
#         if not self.secret_id or not self.secret_key:
#             raise ValueError("请配置腾讯翻译的SecretId和SecretKey")
        
#         # 检查语言支持
#         if from_lang not in self.supported_languages:
#             raise ValueError(f"不支持源语言: {from_lang}")
#         if to_lang not in self.supported_languages:
#             raise ValueError(f"不支持目标语言: {to_lang}")
        
#         # 生成签名参数
#         params = self._generate_signature_v1(text, from_lang, to_lang)
        
#         try:
#             # 发送请求
#             response = requests.get(
#                 f"https://{self.endpoint}",
#                 params=params,
#                 timeout=15
#             )
            
#             result = response.json()
            
#             # 解析响应
#             if 'Response' in result:
#                 resp = result['Response']
                
#                 if 'Error' in resp:
#                     error = resp['Error']
#                     error_code = error.get('Code', 'Unknown')
#                     error_msg = error.get('Message', '未知错误')
#                     raise Exception(f"腾讯翻译错误 [{error_code}]: {error_msg}")
                
#                 if 'TargetText' in resp:
#                     return resp['TargetText'].strip()
#                 else:
#                     raise Exception("翻译结果格式错误: 缺少TargetText字段")
#             else:
#                 raise Exception("腾讯翻译API响应格式错误")
                
#         except requests.exceptions.RequestException as e:
#             raise Exception(f"腾讯翻译网络请求失败: {str(e)}")
#         except json.JSONDecodeError as e:
#             raise Exception(f"腾讯翻译JSON解析失败: {str(e)}")
#         except Exception as e:
#             raise Exception(f"腾讯翻译失败: {str(e)}")
    
#     def translate_to_chinese(self, text: str) -> str:
#         """英译中"""
#         return self.translate(text, 'en', 'zh')
    
#     def translate_to_english(self, text: str) -> str:
#         """中译英"""
#         return self.translate(text, 'zh', 'en')

class GoogleTranslator(BaseTranslator):
    """谷歌翻译（免费版，可能不稳定）"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_url = "https://translate.googleapis.com/translate_a/single"
    
    def translate(self, text: str, from_lang: str, to_lang: str) -> str:
        params = {
            'client': 'gtx',
            'sl': from_lang,
            'tl': to_lang,
            'dt': 't',
            'q': text
        }
        
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            result = response.json()
            
            if result and len(result) > 0:
                translations = [item[0] for item in result[0] if item[0]]
                return ' '.join(translations)
            else:
                raise Exception("谷歌翻译返回空结果")
                
        except Exception as e:
            raise Exception(f"谷歌翻译失败: {str(e)}")
    
    def translate_to_chinese(self, text: str) -> str:
        return self.translate(text, 'en', 'zh-CN')
    
    def translate_to_english(self, text: str) -> str:
        return self.translate(text, 'zh-CN', 'en')


class AITranslator(BaseTranslator):
    """AI翻译（支持OpenAI、DeepSeek、Qwen等）"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.ai_service = config.get('ai_service', 'openai')
        self.api_key = config.get('ai_api_key', '')
        self.api_base = config.get('ai_api_base', '')
    
    def translate_with_ai(self, text: str, target_lang: str) -> str:
        """使用AI模型翻译"""
        if not self.api_key and self.ai_service != 'qwen':
            raise ValueError("AI翻译需要API密钥")
        
        if self.ai_service == 'openai':
            return self._translate_with_openai(text, target_lang)
        elif self.ai_service == 'deepseek':
            return self._translate_with_deepseek(text, target_lang)
        elif self.ai_service == 'qwen':
            return self._translate_with_qwen(text, target_lang)
        else:
            raise ValueError(f"不支持的AI服务: {self.ai_service}")
    
    def _translate_with_openai(self, text: str, target_lang: str) -> str:
        """使用OpenAI API翻译"""
        import openai
        
        openai.api_key = self.api_key
        if self.api_base:
            openai.api_base = self.api_base
        
        prompt = f"请将以下文本翻译成{target_lang}，保持原意但使其更自然流畅：\n{text}"
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "你是一个专业的翻译助手。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"OpenAI翻译失败: {str(e)}")
    
    def _translate_with_deepseek(self, text: str, target_lang: str) -> str:
        """使用DeepSeek API翻译"""
        import openai
        
        openai.api_key = self.api_key
        openai.api_base = "https://api.deepseek.com"
        
        prompt = f"请将以下文本翻译成{target_lang}，保持原意但使其更自然流畅：\n{text}"
        
        try:
            response = openai.ChatCompletion.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是一个专业的翻译助手。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"DeepSeek翻译失败: {str(e)}")
    
    def _translate_with_qwen(self, text: str, target_lang: str) -> str:
        """使用通义千问API翻译（示例）"""
        # 这里需要安装DashScope SDK
        try:
            import dashscope
            dashscope.api_key = self.api_key
            
            prompt = f"请将以下文本翻译成{target_lang}，保持原意但使其更自然流畅：\n{text}"
            
            response = dashscope.Generation.call(
                model='qwen-max',
                prompt=prompt,
                max_tokens=1000
            )
            
            if response.status_code == 200:
                return response.output.text.strip()
            else:
                raise Exception(f"Qwen翻译失败: {response.message}")
        except ImportError:
            raise Exception("请安装dashscope: pip install dashscope")
        except Exception as e:
            raise Exception(f"Qwen翻译失败: {str(e)}")
    
    def translate_to_chinese(self, text: str) -> str:
        return self.translate_with_ai(text, "中文")
    
    def translate_to_english(self, text: str) -> str:
        return self.translate_with_ai(text, "英文")


class TranslatorManager:
    """翻译管理器"""
    
    @staticmethod
    def get_translator(service: str, config: dict) -> BaseTranslator:
        """获取翻译器实例"""
        if service == 'baidu':
            return BaiduTranslator(config)
        elif service == 'youdao':
            return YoudaoTranslator(config)
        elif service == 'google':
            return GoogleTranslator(config)
        elif service == 'tencent':
            return TencentSDKTranslator(config)  # 使用简单版本
        elif service in ['openai', 'deepseek', 'qwen']:
            config['ai_service'] = service
            return AITranslator(config)
        else:
            # 默认使用百度翻译
            return BaiduTranslator(config)