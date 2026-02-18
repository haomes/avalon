"""反思系统 - 游戏结束后的深度学习

每局游戏结束后，每个 Agent 基于完整的游戏行为记录进行反思：
- 回顾自己的发言、投票、任务行动
- 在旧策略基础上迭代修订（而非从零总结）
- 分析其他玩家的具体行为特征
- 提炼可操作的教训
"""

import json
import re

import llm_client
from config import REFLECTION_MODEL, REFLECTION_ENABLED


REFLECTION_SYSTEM_PROMPT = """\
你是一个阿瓦隆游戏的策略教练。你的任务是帮助玩家在游戏结束后进行深度反思。

你需要：
1. 基于玩家本局的**具体行为**（发言内容、投票选择、任务行动）进行分析
2. 找出具体的决策失误或精彩操作，引用实际发生的事件
3. 如果有历史策略，在其基础上**修订和完善**，而非推翻重写
4. 分析其他玩家的行为模式，提供可用于未来博弈的识别线索

回复要求：
- 用中文
- 策略建议必须具体可操作（"注意第X轮..."而非"多观察"）
- 教训要引用本局具体事件
- 严格按照要求的 JSON 格式返回
"""


class ReflectionSystem:
    """游戏反思系统"""

    def reflect(self, agent, game_result: dict, persistent_data, agent_memory=None) -> dict:
        """
        让 Agent 对本局游戏进行深度反思

        Args:
            agent: 本局游戏的 Agent 实例
            game_result: 游戏结果数据（含 mission_records 的 speeches/votes）
            persistent_data: Agent 的持久化数据（PersistentAgentData）
            agent_memory: Agent 的 MemoryManager，可提取游戏记忆摘要

        Returns:
            反思结果字典
        """
        if not REFLECTION_ENABLED:
            return {}

        player = agent.player

        # 构建反思上下文
        context = self._build_reflection_context(
            player, game_result, persistent_data, agent_memory
        )

        reflection_prompt = f"""{context}

请进行以下深度分析并以 JSON 格式返回：

1. **策略修订**：基于本局表现和历史策略（如果有），修订你作为{player.role_name_cn}的策略要点。
   - 如果有历史策略，请在其基础上补充或调整，保留仍然有效的部分
   - 如果没有历史策略，则总结本局经验
   - 80字以内

2. **本局教训**：引用本局中一个具体事件，说明你学到了什么（40字以内）

3. **玩家分析**：分析2-3个值得关注的玩家的行为特征，重点描述：
   - 他们的投票和发言规律
   - 可用于未来识别其阵营的线索

返回格式：
{{
  "strategy_update": "修订后的策略要点",
  "lesson": "基于具体事件的教训",
  "player_impressions": {{
    "player_X": {{
      "play_style": "该玩家的游戏风格（基于本局行为总结）",
      "notable_behavior": "本局具体的行为特征和可识别线索"
    }}
  }}
}}
"""

        try:
            response = llm_client.chat(
                model=REFLECTION_MODEL,
                system_prompt=REFLECTION_SYSTEM_PROMPT,
                user_message=reflection_prompt,
                temperature=0.5,
                max_tokens=800,
            )

            result = self._parse_reflection(response)
        except Exception as e:
            print(f"  [反思] {player.player_name} 反思失败: {e}")
            result = {}

        result["game_id"] = game_result["game_id"]
        result["was_good"] = player.is_good

        lesson = result.get("lesson", "无")
        print(f"  [反思] {player.player_name} ({player.role_name_cn}): {lesson}")

        return result

    def _build_reflection_context(
        self, player, game_result: dict, persistent_data, agent_memory=None
    ) -> str:
        """构建包含完整行为记录的反思上下文"""
        parts = []

        # 基本信息
        team_cn = "正义" if player.is_good else "邪恶"
        parts.append(f"你是{player.player_name}，本局扮演{player.role_name_cn}（{team_cn}阵营）。")

        # 游戏结果
        winner = "正义" if game_result["winner"] == "good" else "邪恶"
        won = (game_result["winner"] == "good") == player.is_good
        parts.append(f"本局{winner}阵营获胜，你{'赢了' if won else '输了'}。")
        parts.append(f"结束原因：{game_result['end_reason']}")

        # ====== 核心改进：注入本局完整行为记录 ======
        player_id_str = str(player.player_id)

        parts.append("\n=== 你本局的行为记录 ===")

        my_speeches = []
        my_votes = []
        my_mission_actions = []

        for record in game_result.get("mission_records", []):
            round_num = record.get("round_num", "?")

            # 自己的发言
            speeches = record.get("speeches", {})
            if player_id_str in speeches:
                my_speeches.append(f"第{round_num}轮: \"{speeches[player_id_str]}\"")

            # 自己的组队投票
            team_votes = record.get("team_votes", {})
            if player_id_str in team_votes:
                vote = "同意" if team_votes[player_id_str] else "反对"
                leader_id = record.get("team_leader_id", -1)
                members = record.get("team_members", [])
                member_names = [f"玩家{m+1}" for m in members]
                my_votes.append(
                    f"第{round_num}轮: 队长玩家{leader_id+1}选了{','.join(member_names)} → 你投了{vote}"
                )

            # 自己的任务行动
            mission_votes = record.get("mission_votes", {})
            if player_id_str in mission_votes:
                action = "成功票" if mission_votes[player_id_str] else "失败票"
                my_mission_actions.append(f"第{round_num}轮任务: 你投了{action}")

        if my_speeches:
            parts.append("\n你的发言：")
            for s in my_speeches:
                parts.append(f"  {s}")

        if my_votes:
            parts.append("\n你的投票：")
            for v in my_votes:
                parts.append(f"  {v}")

        if my_mission_actions:
            parts.append("\n你的任务行动：")
            for a in my_mission_actions:
                parts.append(f"  {a}")

        # ====== 其他玩家的关键行为 ======
        parts.append("\n=== 其他玩家的关键行为 ===")

        for record in game_result.get("mission_records", []):
            round_num = record.get("round_num", "?")
            speeches = record.get("speeches", {})
            team_votes = record.get("team_votes", {})
            success = record.get("success")

            # 其他人的发言摘要
            other_speeches = []
            for pid, speech in speeches.items():
                if pid != player_id_str:
                    other_speeches.append(f"玩家{int(pid)+1}: \"{speech[:60]}\"")

            if other_speeches:
                parts.append(f"\n第{round_num}轮发言：")
                for s in other_speeches:
                    parts.append(f"  {s}")

            # 投票结果
            if team_votes:
                approve = [f"玩家{int(k)+1}" for k, v in team_votes.items() if v and k != player_id_str]
                reject = [f"玩家{int(k)+1}" for k, v in team_votes.items() if not v and k != player_id_str]
                vote_summary = []
                if approve:
                    vote_summary.append(f"同意: {','.join(approve)}")
                if reject:
                    vote_summary.append(f"反对: {','.join(reject)}")
                if vote_summary:
                    parts.append(f"  第{round_num}轮投票 — {'; '.join(vote_summary)}")

            # 任务结果
            if success is not None:
                mission_votes = record.get("mission_votes", {})
                fail_count = sum(1 for v in mission_votes.values() if not v)
                result_str = "成功" if success else f"失败（{fail_count}张失败票）"
                parts.append(f"  第{round_num}轮任务结果: {result_str}")

        # 刺杀信息
        assassin_data = game_result.get("assassin_phase")
        if assassin_data:
            killed = "成功" if assassin_data.get("merlin_killed") else "失败"
            target_id = assassin_data.get("target_id", -1)
            parts.append(f"\n刺杀阶段：刺客选择了玩家{target_id+1}，刺杀{killed}")

        # ====== 核心改进：注入 Agent 的游戏记忆摘要 ======
        if agent_memory and agent_memory.summary:
            parts.append(f"\n=== 你的游戏记忆摘要 ===\n{agent_memory.summary}")

        # ====== 核心改进：历史策略（用于迭代修订） ======
        if persistent_data:
            sm = persistent_data.strategy_memory
            has_history = False

            if player.is_good and sm.good_strategy_summary:
                parts.append(f"\n=== 你之前积累的好人策略（请在此基础上修订） ===\n{sm.good_strategy_summary}")
                has_history = True
            elif player.is_evil and sm.evil_strategy_summary:
                parts.append(f"\n=== 你之前积累的坏人策略（请在此基础上修订） ===\n{sm.evil_strategy_summary}")
                has_history = True

            if not has_history:
                parts.append("\n（这是你的第一次反思，请从零开始总结策略。）")

            # 近期教训
            if sm.recent_lessons:
                parts.append("\n你近期的教训：")
                for lesson in sm.recent_lessons[-3:]:
                    parts.append(f"  - {lesson['lesson']}")

        # 揭示真实身份（反思时可以看到）
        parts.append("\n=== 本局真实身份揭示 ===")
        for p_info in game_result.get("players", []):
            parts.append(f"  {p_info['player_name']}: {p_info['role_name_cn']}（{p_info['team']}）")

        return "\n".join(parts)

    def _parse_reflection(self, response: str) -> dict:
        """解析 LLM 的反思响应"""
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

        # 解析失败，尝试从文本中提取信息
        result = {}
        if "策略" in response or "总结" in response or "教训" in response:
            lines = response.strip().split("\n")
            for line in lines:
                line = line.strip()
                if line and len(line) < 80 and not line.startswith("{"):
                    result["lesson"] = line
                    break

        return result
