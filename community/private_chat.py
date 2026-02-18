"""私聊系统 - 游戏间的社交互动与策略交流

游戏结束后，随机选择 2-3 对 Agent 进行私下交流：
- 对话内容围绕本局游戏的具体事件展开
- 双方可以坦诚交流策略心得（游戏外身份已揭晓）
- LLM 分析对话内容，判断信任度/友好度变化和策略收获
"""

import json
import random
import re

import llm_client
from config import (
    PRIVATE_CHAT_ENABLED,
    PRIVATE_CHAT_MAX_PAIRS,
    PRIVATE_CHAT_MAX_TURNS,
    PRIVATE_CHAT_TEMPERATURE,
    REFLECTION_MODEL,
)


PRIVATE_CHAT_SYSTEM_PROMPT = """\
你正在与另一位阿瓦隆玩家进行赛后交流。游戏已经结束，双方身份已经公开。

你们可以：
- 坦诚讨论刚才那局的策略得失
- 分享自己的决策思路（为什么那样投票、发言）
- 交流识别好人/坏人的技巧
- 讨论对方的某个操作让你印象深刻或困惑

要求：
- 用中文
- 保持自然的对话风格，像朋友复盘棋局一样
- 每次发言控制在60字以内
- 可以分享真实想法和策略心得
- 聊天应该有实质内容，不要只是寒暄
"""


CHAT_ANALYSIS_PROMPT = """\
你是一个社交关系分析师。请分析以下两位阿瓦隆玩家的赛后对话，评估这次交流对双方关系和策略学习的影响。

{context}

对话记录：
{chat_log}

请分析并以 JSON 格式返回：

{{
  "trust_delta_a": 信任度变化(-0.15到+0.15的浮点数，{player_a}对{player_b}的信任变化),
  "trust_delta_b": 信任度变化(-0.15到+0.15的浮点数，{player_b}对{player_a}的信任变化),
  "friendliness_delta_a": 友好度变化(-0.10到+0.10的浮点数),
  "friendliness_delta_b": 友好度变化(-0.10到+0.10的浮点数),
  "relation_note_a": "{player_a}对{player_b}的关系备注（15字以内，如'上局他坦诚分享了刺杀思路'）",
  "relation_note_b": "{player_b}对{player_a}的关系备注（15字以内）",
  "strategy_insight_a": "{player_a}从这次对话中获得的策略收获（如果有，30字以内；如果没有，留空字符串）",
  "strategy_insight_b": "{player_b}从这次对话中获得的策略收获（如果有，30字以内；如果没有，留空字符串）"
}}

判断依据：
- 如果双方坦诚交流有价值的策略，信任度和友好度应提升较多
- 如果一方回避或敷衍，对方的信任度可能下降
- 如果双方上局是对手（不同阵营），坦诚复盘后信任可以恢复
- 如果一方表达了不满或指责，友好度应下降
- strategy_insight 只填写有实际价值的策略收获，不要填泛泛而谈的内容
"""


class PrivateChatSystem:
    """私聊系统"""

    def select_chat_pairs(
        self,
        player_ids: list[int],
        game_result: dict,
    ) -> list[tuple[int, int]]:
        """
        选择进行私聊的玩家配对

        Args:
            player_ids: 所有玩家ID列表
            game_result: 游戏结果

        Returns:
            配对列表 [(player_a_id, player_b_id), ...]
        """
        if not PRIVATE_CHAT_ENABLED:
            return []

        pairs = []
        used = set()

        # 1. 如果有刺杀阶段，刺客和目标大概率私聊
        assassin_data = game_result.get("assassin_phase")
        if assassin_data and random.random() < 0.7:
            a_id = assassin_data["assassin_id"]
            t_id = assassin_data["target_id"]
            pairs.append((a_id, t_id))
            used.add(a_id)
            used.add(t_id)

        # 2. 优先配对不同阵营的玩家（跨阵营交流更有学习价值）
        players_info = game_result.get("players", [])
        good_remaining = [p["player_id"] for p in players_info if p["team"] == "good" and p["player_id"] not in used]
        evil_remaining = [p["player_id"] for p in players_info if p["team"] == "evil" and p["player_id"] not in used]

        random.shuffle(good_remaining)
        random.shuffle(evil_remaining)

        # 尝试跨阵营配对
        while good_remaining and evil_remaining and len(pairs) < PRIVATE_CHAT_MAX_PAIRS:
            g = good_remaining.pop()
            e = evil_remaining.pop()
            pairs.append((g, e))
            used.add(g)
            used.add(e)

        # 3. 剩余的同阵营配对
        remaining = [p for p in player_ids if p not in used]
        random.shuffle(remaining)
        for i in range(0, len(remaining) - 1, 2):
            if len(pairs) >= PRIVATE_CHAT_MAX_PAIRS:
                break
            pairs.append((remaining[i], remaining[i + 1]))

        return pairs[:PRIVATE_CHAT_MAX_PAIRS]

    def conduct_chat(
        self,
        agent_a,
        agent_b,
        game_result: dict,
    ) -> dict:
        """
        执行一次私聊

        Args:
            agent_a: 玩家 A 的 Agent
            agent_b: 玩家 B 的 Agent
            game_result: 游戏结果

        Returns:
            私聊结果字典（含 LLM 分析的信任/友好度变化和策略收获）
        """
        if not PRIVATE_CHAT_ENABLED:
            return {
                "summary": "", "trust_delta_a": 0, "trust_delta_b": 0,
                "friendliness_delta_a": 0, "friendliness_delta_b": 0,
                "chat_log": [], "relation_note_a": "", "relation_note_b": "",
                "strategy_insight_a": "", "strategy_insight_b": "",
            }

        player_a = agent_a.player
        player_b = agent_b.player

        print(f"\n  [私聊] {player_a.player_name}({player_a.role_name_cn}) <-> {player_b.player_name}({player_b.role_name_cn})")

        # 生成话题（基于具体游戏事件）
        topic = self._generate_topic(player_a, player_b, game_result)

        # 对话历史
        chat_history = []

        # A 先开始
        context_a = self._build_chat_context(
            player_a, player_b, game_result, topic, chat_history
        )
        response_a = self._get_chat_response(agent_a, context_a)
        chat_history.append((player_a.player_name, response_a))
        print(f"    {player_a.player_name}: {response_a}")

        # 交替对话
        for turn in range(PRIVATE_CHAT_MAX_TURNS):
            # B 回复
            context_b = self._build_chat_context(
                player_b, player_a, game_result, topic, chat_history
            )
            response_b = self._get_chat_response(agent_b, context_b)
            chat_history.append((player_b.player_name, response_b))
            print(f"    {player_b.player_name}: {response_b}")

            if turn < PRIVATE_CHAT_MAX_TURNS - 1:
                # A 继续
                context_a = self._build_chat_context(
                    player_a, player_b, game_result, topic, chat_history
                )
                response_a = self._get_chat_response(agent_a, context_a)
                chat_history.append((player_a.player_name, response_a))
                print(f"    {player_a.player_name}: {response_a}")

        # LLM 分析对话结果
        result = self._analyze_chat_result(chat_history, player_a, player_b, game_result)
        result["topic"] = topic
        return result

    def _generate_topic(self, player_a, player_b, game_result: dict) -> str:
        """生成基于具体游戏事件的聊天话题"""
        topics = []

        # 基于玩家角色组合生成针对性话题
        same_team = player_a.is_good == player_b.is_good

        if not same_team:
            # 跨阵营：复盘对抗
            topics.append(f"你们分属不同阵营，聊聊这局中对方的哪些操作骗到了你")
            topics.append("互相分享一下你在游戏中是怎么判断对方阵营的")
        else:
            topics.append("讨论一下这局中你们在判断上的分歧点")

        if player_a.role.is_assassin or player_b.role.is_assassin:
            topics.append("刺客来聊聊你是怎么锁定刺杀目标的，以及梅林可以怎么更好地隐藏")

        if player_a.role.role_id == "merlin" or player_b.role.role_id == "merlin":
            topics.append("梅林来复盘一下你是怎么暗中引导好人的，有没有暴露的风险点")

        if player_a.role.role_id == "percival" or player_b.role.role_id == "percival":
            topics.append("派西维尔来聊聊你是怎么分辨梅林和莫甘娜的")

        # 基于游戏结果
        if game_result["winner"] == "good":
            topics.append("正义阵营获胜的关键转折点是什么")
        else:
            topics.append("邪恶阵营是怎么赢的，好人哪里判断失误了")

        # 基于任务记录找具体事件
        for record in game_result.get("mission_records", []):
            if record.get("success") is False:
                fail_count = sum(1 for v in record.get("mission_votes", {}).values() if not v)
                topics.append(f"第{record['round_num']}轮任务出了{fail_count}张失败票，聊聊当时的情况")
                break

        return random.choice(topics)

    def _build_chat_context(
        self,
        speaker,
        listener,
        game_result: dict,
        topic: str,
        chat_history: list,
    ) -> str:
        """构建包含角色信息的私聊上下文"""
        same_team = speaker.is_good == listener.is_good
        team_relation = "同阵营队友" if same_team else "对手"

        parts = [
            f"游戏已结束，身份已公开。你是{speaker.player_name}（{speaker.role_name_cn}），"
            f"对方是{listener.player_name}（{listener.role_name_cn}），你们是{team_relation}。",
            f"游戏结果：{'正义' if game_result['winner'] == 'good' else '邪恶'}阵营获胜。",
            f"聊天话题：{topic}",
        ]

        if chat_history:
            parts.append("\n对话记录：")
            for name, msg in chat_history[-6:]:
                parts.append(f"  {name}: {msg}")

        parts.append("\n请继续对话（60字以内，分享有价值的策略心得）：")

        return "\n".join(parts)

    def _get_chat_response(self, agent, context: str) -> str:
        """获取私聊回复"""
        try:
            response = llm_client.chat(
                model=agent.model,
                system_prompt=PRIVATE_CHAT_SYSTEM_PROMPT,
                user_message=context,
                temperature=PRIVATE_CHAT_TEMPERATURE,
                max_tokens=128,
            )
            # 清理过长的回复
            response = response.strip()
            if len(response) > 120:
                response = response[:120] + "..."
            return response
        except Exception as e:
            return f"（通信故障：{e}）"

    def _analyze_chat_result(
        self,
        chat_history: list,
        player_a,
        player_b,
        game_result: dict,
    ) -> dict:
        """用 LLM 分析私聊结果，判断信任度/友好度变化和策略收获"""
        same_team = player_a.is_good == player_b.is_good
        context = (
            f"{player_a.player_name}是{player_a.role_name_cn}（{'正义' if player_a.is_good else '邪恶'}阵营），"
            f"{player_b.player_name}是{player_b.role_name_cn}（{'正义' if player_b.is_good else '邪恶'}阵营）。\n"
            f"他们是{'同阵营' if same_team else '不同阵营'}的。\n"
            f"本局{'正义' if game_result['winner'] == 'good' else '邪恶'}阵营获胜。"
        )

        chat_log_text = "\n".join(f"  {name}: {msg}" for name, msg in chat_history)

        analysis_prompt = CHAT_ANALYSIS_PROMPT.format(
            context=context,
            chat_log=chat_log_text,
            player_a=player_a.player_name,
            player_b=player_b.player_name,
        )

        try:
            response = llm_client.chat(
                model=REFLECTION_MODEL,
                system_prompt="你是一个社交关系分析师，请严格按照JSON格式返回分析结果。",
                user_message=analysis_prompt,
                temperature=0.3,
                max_tokens=400,
            )

            result = self._parse_analysis(response, player_a, player_b, chat_history)
        except Exception as e:
            print(f"  [私聊分析] 分析失败: {e}，使用默认值")
            result = self._fallback_analysis(player_a, player_b, chat_history)

        return result

    def _parse_analysis(self, response: str, player_a, player_b, chat_history: list) -> dict:
        """解析 LLM 的对话分析结果"""
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())

                # 提取并裁剪数值到合理范围
                def clamp(v, lo, hi):
                    try:
                        return max(lo, min(hi, float(v)))
                    except (TypeError, ValueError):
                        return 0.0

                summary = self._make_summary(chat_history)

                return {
                    "summary": summary,
                    "trust_delta_a": clamp(data.get("trust_delta_a", 0), -0.15, 0.15),
                    "trust_delta_b": clamp(data.get("trust_delta_b", 0), -0.15, 0.15),
                    "friendliness_delta_a": clamp(data.get("friendliness_delta_a", 0), -0.10, 0.10),
                    "friendliness_delta_b": clamp(data.get("friendliness_delta_b", 0), -0.10, 0.10),
                    "chat_log": chat_history,
                    "relation_note_a": str(data.get("relation_note_a", ""))[:30],
                    "relation_note_b": str(data.get("relation_note_b", ""))[:30],
                    "strategy_insight_a": str(data.get("strategy_insight_a", ""))[:60],
                    "strategy_insight_b": str(data.get("strategy_insight_b", ""))[:60],
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # JSON 解析失败，使用回退逻辑
        return self._fallback_analysis(player_a, player_b, chat_history)

    def _fallback_analysis(self, player_a, player_b, chat_history: list) -> dict:
        """LLM 分析失败时的回退逻辑（保留基础规则）"""
        same_team = player_a.is_good == player_b.is_good
        friendliness_delta = 0.04 if same_team else 0.02
        trust_delta = 0.02 if len(chat_history) >= 4 else 0.01

        return {
            "summary": self._make_summary(chat_history),
            "trust_delta_a": trust_delta,
            "trust_delta_b": trust_delta,
            "friendliness_delta_a": friendliness_delta,
            "friendliness_delta_b": friendliness_delta,
            "chat_log": chat_history,
            "relation_note_a": "",
            "relation_note_b": "",
            "strategy_insight_a": "",
            "strategy_insight_b": "",
        }

    def _make_summary(self, chat_history: list) -> str:
        """生成对话摘要"""
        topic_parts = []
        for name, msg in chat_history[:2]:
            topic_parts.append(f"{name}说{msg[:25]}")
        return "；".join(topic_parts) if topic_parts else "进行了友好交流"
