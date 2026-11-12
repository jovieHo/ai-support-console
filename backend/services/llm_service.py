"""
LLM 调用服务
封装 OpenAI 兼容协议的模型调用，支持同步对话、流式输出以及未配置 API Key 时的本地降级。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx
from langchain_core.runnables import RunnableLambda

from core.config import get_settings


# LangChain 消息类型 -> OpenAI 协议 role 的映射
_ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant"}


class LLMService:

    def __init__(self) -> None:
        self.settings = get_settings()

    def as_runnable(self) -> RunnableLambda:
        """把裸 httpx 的 chat() 包装成 LCEL 可组合的 Runnable。

        分类链、知识问答链都以 prompt | self.llm.as_runnable() | parser
        的方式接入。LLMService 本身不继承 LangChain 的 BaseChatModel：
        十行适配层换来链的可组合性，不必引入 SDK 依赖。
        """
        return RunnableLambda(self._from_prompt_value)

    async def _from_prompt_value(self, prompt_value) -> str:
        """RunnableLambda 适配层：LangChain 消息对象转成 chat() 的 dict 消息。"""
        messages = [
            {"role": _ROLE_MAP.get(message.type, message.type), "content": message.content}
            for message in prompt_value.to_messages()
        ]
        return await self.chat(messages)

    async def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        """
        非流式对话：发送完整消息列表，一次性返回模型回复。

        参数:
            messages: 消息列表，每条为 {"role": "system|user|assistant", "content": "..."}
            temperature: 采样温度，为 None 时使用配置默认值

        返回:
            str: 模型生成的回复文本

        异常:
            RuntimeError: LLM 接口返回非 2xx 状态码时抛出
        """
        if not self.settings.llm_api_key:
            return self._fallback_answer(messages)

        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.llm_temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500]
                raise RuntimeError(f"大模型接口调用失败：{detail}") from exc
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        """
        流式对话：通过 SSE 逐块返回模型回复，适用于需要实时打字机效果的场景。

        参数:
            messages: 消息列表，格式同 chat()

        产出:
            AsyncGenerator[str, None]: 逐块产出模型回复文本片段

        异常:
            RuntimeError: 流式接口返回非 2xx 时抛出
        """
        # 未配置 API Key 时整段返回本地降级文本，不做模拟流式
        if not self.settings.llm_api_key:
            yield self._fallback_answer(messages)
            return

        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        # 使用 httpx stream 模式，无超时限制（连接可能长期保持）
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text[:500]
                    raise RuntimeError(f"大模型流式接口调用失败：{detail}") from exc
                # SSE 协议每行以 "data: " 开头
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line.removeprefix("data: ").strip()
                    # "[DONE]" 标记流结束
                    if chunk == "[DONE]":
                        break
                    data = json.loads(chunk)
                    content = data["choices"][0].get("delta", {}).get("content")
                    if content:
                        yield content

    def _fallback_answer(self, messages: list[dict[str, str]]) -> str:
        """
        当未配置 LLM API Key 时，生成一个本地兜底回复。

        参数:
            messages: 消息列表，取最后一条用户消息作为问题上下文

        返回:
            str: 本地生成的降级回复文本
        """
        question = messages[-1]["content"] if messages else ""
        return (
            "这是本地降级 AI 回复：已收到您的商务问题。"
            f"围绕「{question[:80]}」，建议先确认业务背景、服务范围、交付时限和责任人；"
            "如涉及合同、价格或合规事项，请交由对应业务负责人复核。"
        )
