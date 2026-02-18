"""
Memory Manager - Agent 记忆管理模块

采用分层压缩架构：

┌──────────────────────────────────────────────┐
│                  Memory                      │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  summary (str)                         │  │
│  │  早期记忆的 LLM 摘要，一段结构化文本    │  │
│  │  包含：关键事件、各玩家行为画像、       │  │
│  │        怀疑/信任关系、自己的决策记录     │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  recent: list[dict]                    │  │
│  │  近期原始消息，保留完整上下文           │  │
│  │  格式: [{"role": "user/assistant",     │  │
│  │          "content": "..."}]            │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘

压缩触发条件：recent 长度超过 MEMORY_COMPRESS_THRESHOLD
压缩过程：
  1. 将 recent 中较旧的消息（保留最近 MEMORY_KEEP_RECENT 条）提取出来
  2. 连同现有 summary 一起发送给 LLM，生成新的合并摘要
  3. 用新摘要替换旧摘要，只保留近期消息
"""

import llm_client
from config import (
    MEMORY_COMPRESS_THRESHOLD,
    MEMORY_KEEP_RECENT,
    MEMORY_SUMMARY_MODEL,
    MEMORY_SUMMARY_MAX_TOKENS,
)


# 摘要生成的系统提示词
_SUMMARY_SYSTEM_PROMPT = """\
你是一个阿瓦隆桌游的记忆助手。你的任务是将游戏过程中的对话记录压缩成一份结构化摘要。

摘要必须包含以下信息（如果存在的话）：

1. **关键事件**：每轮的队长、队伍组成、投票结果（通过/否决）、任务结果（成功/失败及票数）
2. **玩家行为画像**：每个玩家的发言立场、投票倾向、可疑或可信的行为
3. **社交关系推断**：谁怀疑谁、谁信任谁、谁和谁观点一致/冲突
4. **我的决策记录**：我（当前玩家）做了哪些决策、说了什么、投了什么票

要求：
- 用中文
- 简洁精炼，突出对后续决策有价值的信息
- 不要遗漏任何玩家的关键行为
- 不要编造没有出现过的事件
- 控制在300字以内
"""


class MemoryManager:
    """Agent 记忆管理器"""

    def __init__(self, player_name: str, model: str):
        """
        Args:
            player_name: 当前玩家名称（用于摘要中标识"我"）
            model: 当前 Agent 使用的模型（摘要也用同模型，可配置覆盖）
        """
        self.player_name = player_name
        self.summary_model = MEMORY_SUMMARY_MODEL or model

        # 分层存储
        self.summary: str = ""           # 早期记忆的压缩摘要
        self.recent: list[dict] = []     # 近期原始消息

        # 统计
        self.compress_count: int = 0     # 压缩次数

    def add(self, role: str, content: str):
        """
        添加一条消息到记忆

        Args:
            role: "user" 或 "assistant"
            content: 消息内容
        """
        self.recent.append({"role": role, "content": content})

        # 检查是否需要压缩
        if len(self.recent) >= MEMORY_COMPRESS_THRESHOLD:
            self._compress()

    def get_messages_for_llm(self) -> list[dict]:
        """
        构建发送给 LLM 的历史消息列表（不含 system prompt 和当前 user message）

        Returns:
            消息列表，格式: [{"role": "user/assistant", "content": "..."}]
        """
        messages = []

        # 如果有摘要，作为第一条上下文注入
        if self.summary:
            messages.append({
                "role": "user",
                "content": f"[历史记忆摘要]\n{self.summary}",
            })
            messages.append({
                "role": "assistant",
                "content": "好的，我已了解之前的游戏经过，会基于这些信息继续参与游戏。",
            })

        # 然后拼接近期原始消息
        messages.extend(self.recent)

        return messages

    def _compress(self):
        """
        执行记忆压缩：
        1. 提取需要压缩的旧消息
        2. 调用 LLM 生成摘要
        3. 更新 summary，只保留近期消息
        """
        # 划分：旧消息需要压缩，新消息保留
        keep_count = MEMORY_KEEP_RECENT
        old_messages = self.recent[:-keep_count]
        new_messages = self.recent[-keep_count:]

        # 构建要压缩的文本
        text_to_compress = self._format_messages_for_summary(old_messages)

        if not text_to_compress.strip():
            # 没有实质内容需要压缩
            self.recent = new_messages
            return

        # 构建摘要请求
        if self.summary:
            user_message = (
                f"以下是之前的记忆摘要：\n"
                f"---\n{self.summary}\n---\n\n"
                f"以下是新增的游戏记录（来自{self.player_name}的视角）：\n"
                f"---\n{text_to_compress}\n---\n\n"
                f"请将旧摘要和新记录合并，生成一份更新的摘要。"
            )
        else:
            user_message = (
                f"以下是游戏记录（来自{self.player_name}的视角）：\n"
                f"---\n{text_to_compress}\n---\n\n"
                f"请生成一份结构化摘要。"
            )

        # 调用 LLM 生成摘要
        new_summary = llm_client.chat(
            model=self.summary_model,
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.3,  # 摘要用低温度，保证准确
            max_tokens=MEMORY_SUMMARY_MAX_TOKENS,
        )

        # 检查摘要是否有效（LLM调用失败时返回错误字符串）
        if new_summary.startswith("[LLM调用失败"):
            # 摘要失败，退化为硬截断
            self.recent = new_messages
            return

        # 更新状态
        self.summary = new_summary
        self.recent = new_messages
        self.compress_count += 1

    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """
        将消息列表格式化为可读文本，用于摘要生成

        Args:
            messages: 消息列表

        Returns:
            格式化后的文本
        """
        lines = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                if content.startswith("[游戏事件]"):
                    lines.append(content)
                elif content.startswith("[任务执行]"):
                    lines.append(content)
                else:
                    # 来自游戏引擎的决策请求，简化处理
                    # 提取关键信息，去掉冗长的规则和JSON格式说明
                    simplified = self._simplify_prompt(content)
                    if simplified:
                        lines.append(f"[决策请求] {simplified}")
            elif role == "assistant":
                lines.append(f"[{self.player_name}的回复] {content}")

        return "\n".join(lines)

    def _simplify_prompt(self, prompt: str) -> str:
        """简化决策请求 prompt，去掉模板化的指令部分，只保留上下文"""
        # 去掉 JSON 格式说明部分
        lines = prompt.split("\n")
        useful_lines = []
        skip = False
        for line in lines:
            # 跳过 JSON 格式说明和重复的规则
            if "请严格按照以下JSON格式" in line:
                skip = True
                continue
            if "请直接说出你的发言内容" in line:
                continue
            if "注意不要暴露自己的真实身份" in line:
                continue
            if skip:
                # JSON 示例行一般以 { 或 例如 开头
                if line.strip().startswith("{") or line.strip().startswith("例如"):
                    continue
                else:
                    skip = False

            stripped = line.strip()
            if stripped:
                useful_lines.append(stripped)

        return " ".join(useful_lines[:5])  # 只保留前5行核心信息

    def get_stats(self) -> dict:
        """获取记忆统计信息"""
        return {
            "summary_length": len(self.summary),
            "recent_count": len(self.recent),
            "compress_count": self.compress_count,
            "has_summary": bool(self.summary),
        }
