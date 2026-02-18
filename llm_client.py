"""LLM 客户端封装，统一管理模型调用"""

import json
import os
import re
import time
from openai import OpenAI

from config import API_BASE_URL, LLM_TEMPERATURE, LLM_MAX_TOKENS

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def _build_client() -> OpenAI:
    """构建 OpenAI 兼容客户端"""
    api_key = os.getenv("API_KEY", "")

    # 如果配置了蓝鲸平台认证，使用自定义 header
    bk_app_code = os.getenv("BK_APP_CODE", "")
    bk_app_secret = os.getenv("BK_APP_SECRET", "")
    headers = {}
    if bk_app_code and bk_app_secret:
        headers["X-Bkapi-Authorization"] = json.dumps(
            {
                "bk_app_code": bk_app_code,
                "bk_app_secret": bk_app_secret,
            }
        )

    return OpenAI(
        api_key=api_key or "empty",
        base_url=API_BASE_URL,
        default_headers=headers if headers else None,
        timeout=60.0,  # 60秒超时，防止LLM调用无限挂起
    )


# 全局客户端实例
_client = _build_client()


def _clean_response(content: str) -> str:
    """清理模型返回内容（去除 think 标签等）"""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def _call_with_retry(messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
    """带重试的 LLM 调用"""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            # 防御性检查：choices 可能为空，content 可能为 None
            if not response.choices:
                raise ValueError("API返回的choices为空")
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("API返回的content为None")
            content = content.strip()
            if not content:
                raise ValueError("API返回了空字符串")
            return _clean_response(content)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  [LLM重试] 第{attempt + 1}次调用失败: {e}，{wait}秒后重试...")
                time.sleep(wait)

    return f"[LLM调用失败(重试{MAX_RETRIES}次): {last_error}]"


def chat(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
) -> str:
    """
    调用 LLM 进行对话

    Args:
        model: 模型名称 (hunyuan2 / kimi-25)
        system_prompt: 系统提示词
        user_message: 用户消息
        temperature: 温度参数
        max_tokens: 最大生成token数

    Returns:
        模型的回复文本
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return _call_with_retry(messages, model, temperature, max_tokens)


def chat_with_history(
    model: str,
    system_prompt: str,
    history: list[dict],
    user_message: str,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS,
) -> str:
    """
    带历史上下文的 LLM 对话

    Args:
        model: 模型名称
        system_prompt: 系统提示词
        history: 历史消息列表 [{"role": "user/assistant", "content": "..."}]
        user_message: 当前用户消息
        temperature: 温度参数
        max_tokens: 最大生成token数

    Returns:
        模型的回复文本
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return _call_with_retry(messages, model, temperature, max_tokens)
