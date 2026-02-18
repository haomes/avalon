"""持久化 Agent 数据管理

每个 Agent 的长期记忆、策略、社交关系都以 JSON 文件形式存储在 data/agents/ 目录下。
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 数据类定义 ====================

@dataclass
class AgentStatistics:
    """Agent 统计数据"""
    games_played: int = 0
    games_as_good: int = 0
    games_as_evil: int = 0
    wins_as_good: int = 0
    wins_as_evil: int = 0
    times_as_merlin: int = 0
    times_assassinated: int = 0
    times_correct_assassination: int = 0
    last_game_timestamp: str = ""


@dataclass
class StrategyMemory:
    """策略记忆"""
    good_strategy_summary: str = ""
    evil_strategy_summary: str = ""
    merlin_play_style: str = ""
    assassin_tactics: str = ""
    recent_lessons: list[dict] = field(default_factory=list)


@dataclass
class SocialRelation:
    """与另一个玩家的社交关系"""
    trust: float = 0.5
    friendliness: float = 0.5
    notes: str = ""
    recent_interactions: list[dict] = field(default_factory=list)
    strategy_insights: list[str] = field(default_factory=list)  # 从私聊中获得的策略收获


@dataclass
class PlayerImpression:
    """对其他玩家的印象"""
    play_style: str = ""
    tells: list[str] = field(default_factory=list)
    suspected_evil_accuracy: float = 0.5


@dataclass
class PersistentAgentData:
    """完整的持久化 Agent 数据"""
    agent_id: str
    display_name: str
    statistics: AgentStatistics = field(default_factory=AgentStatistics)
    strategy_memory: StrategyMemory = field(default_factory=StrategyMemory)
    social_relations: dict[str, SocialRelation] = field(default_factory=dict)
    player_impressions: dict[str, PlayerImpression] = field(default_factory=dict)
    private_chat_history: list[dict] = field(default_factory=list)


# ==================== 管理器 ====================

class PersistentAgentManager:
    """管理所有 Agent 的持久化数据"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.agents_data: dict[str, PersistentAgentData] = {}

    # ---------- 加载/保存 ----------

    def load_all_agents(self) -> dict[str, PersistentAgentData]:
        """加载所有 Agent 数据"""
        from config import PLAYER_COUNT
        for i in range(1, PLAYER_COUNT + 1):
            agent_id = f"player_{i}"
            self.agents_data[agent_id] = self._load_agent(agent_id)
        return self.agents_data

    @staticmethod
    def _normalize_player_key(key: str) -> str:
        """将各种格式的玩家ID规范化为 player_X 格式
        
        支持: 'player_1', '1', '玩家1', 'Player 1', 'player1' 等
        返回: 'player_X' 或空字符串（无法解析时）
        """
        import re
        # 已经是标准格式
        if re.match(r'^player_\d+$', key):
            return key
        # 提取数字部分
        nums = re.findall(r'\d+', key)
        if nums:
            return f"player_{nums[0]}"
        return ""

    def _load_agent(self, agent_id: str) -> PersistentAgentData:
        """加载单个 Agent 数据"""
        file_path = os.path.join(self.data_dir, f"{agent_id}.json")

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return self._dict_to_agent_data(data)

        # 新建 Agent
        num = agent_id.split("_")[1]
        return PersistentAgentData(
            agent_id=agent_id,
            display_name=f"玩家{num}",
        )

    def save_all_agents(self):
        """保存所有 Agent 数据"""
        for agent_id, data in self.agents_data.items():
            self._save_agent(agent_id, data)

    def _save_agent(self, agent_id: str, data: PersistentAgentData):
        """保存单个 Agent 数据"""
        file_path = os.path.join(self.data_dir, f"{agent_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self._agent_data_to_dict(data), f, ensure_ascii=False, indent=2)

    # ---------- 查询 ----------

    def get_agent_data(self, player_name: str) -> PersistentAgentData | None:
        """根据玩家名获取数据（如 '玩家1' -> 'player_1'）"""
        # 从名称中提取数字
        num = "".join(filter(str.isdigit, player_name))
        if not num:
            return None
        agent_id = f"player_{num}"
        return self.agents_data.get(agent_id)

    # ---------- 更新 ----------

    def update_agent_statistics(self, player_name: str, game_result: dict):
        """更新 Agent 的游戏统计"""
        data = self.get_agent_data(player_name)
        if not data:
            return

        # 找到该玩家的游戏数据
        player_info = None
        for p in game_result["players"]:
            pid = f"player_{p['player_id'] + 1}"
            if pid == data.agent_id:
                player_info = p
                break

        if not player_info:
            return

        stats = data.statistics
        stats.games_played += 1
        stats.last_game_timestamp = datetime.now().isoformat()

        is_good = player_info["team"] == "good"
        won = (game_result["winner"] == "good") == is_good

        if is_good:
            stats.games_as_good += 1
            if won:
                stats.wins_as_good += 1
        else:
            stats.games_as_evil += 1
            if won:
                stats.wins_as_evil += 1

        # 角色特殊统计
        role = player_info["role"]
        if role == "merlin":
            stats.times_as_merlin += 1

        assassin_data = game_result.get("assassin_phase")
        if assassin_data:
            if assassin_data.get("target_id") == player_info["player_id"] and role == "merlin":
                stats.times_assassinated += 1
            if assassin_data.get("assassin_id") == player_info["player_id"] and assassin_data.get("merlin_killed"):
                stats.times_correct_assassination += 1

    def update_agent_reflection(self, player_name: str, reflection: dict):
        """更新 Agent 的反思结果"""
        data = self.get_agent_data(player_name)
        if not data:
            return

        # 更新策略记忆
        if "strategy_update" in reflection and reflection["strategy_update"]:
            if reflection.get("was_good"):
                data.strategy_memory.good_strategy_summary = reflection["strategy_update"]
            else:
                data.strategy_memory.evil_strategy_summary = reflection["strategy_update"]

        # 添加教训
        if "lesson" in reflection and reflection["lesson"]:
            data.strategy_memory.recent_lessons.append({
                "game_id": reflection.get("game_id", ""),
                "lesson": reflection["lesson"],
            })
            # 只保留最近 10 条
            from config import REFLECTION_MAX_LESSONS
            data.strategy_memory.recent_lessons = data.strategy_memory.recent_lessons[-REFLECTION_MAX_LESSONS:]

        # 更新对其他玩家的印象
        if "player_impressions" in reflection and reflection["player_impressions"]:
            for player_id, impression in reflection["player_impressions"].items():
                # 规范化键名为 player_X 格式（LLM 可能返回 "1", "玩家1" 等格式）
                normalized_id = self._normalize_player_key(player_id)
                if not normalized_id:
                    continue
                if normalized_id not in data.player_impressions:
                    data.player_impressions[normalized_id] = PlayerImpression()
                pi = data.player_impressions[normalized_id]
                if impression.get("play_style"):
                    pi.play_style = impression["play_style"]
                if impression.get("notable_behavior"):
                    # 添加到 tells 列表
                    pi.tells.append(impression["notable_behavior"])
                    pi.tells = pi.tells[-5:]  # 保留最近 5 条

    def update_social_relation(
        self,
        player_a_name: str,
        player_b_name: str,
        chat_result: dict,
    ):
        """根据私聊结果更新双方社交关系"""
        data_a = self.get_agent_data(player_a_name)
        data_b = self.get_agent_data(player_b_name)
        if not data_a or not data_b:
            return

        interaction_record = {
            "timestamp": datetime.now().isoformat(),
            "event": chat_result.get("summary", ""),
        }

        # 更新 A 对 B 的关系
        if data_b.agent_id not in data_a.social_relations:
            data_a.social_relations[data_b.agent_id] = SocialRelation()
        rel_a = data_a.social_relations[data_b.agent_id]
        rel_a.trust = max(0.0, min(1.0, rel_a.trust + chat_result.get("trust_delta_a", 0)))
        rel_a.friendliness = max(0.0, min(1.0, rel_a.friendliness + chat_result.get("friendliness_delta_a", 0)))
        rel_a.recent_interactions.append(interaction_record)
        rel_a.recent_interactions = rel_a.recent_interactions[-5:]
        # 更新关系备注
        note_a = chat_result.get("relation_note_a", "")
        if note_a:
            rel_a.notes = note_a
        # 记录策略收获
        insight_a = chat_result.get("strategy_insight_a", "")
        if insight_a:
            rel_a.strategy_insights.append(insight_a)
            rel_a.strategy_insights = rel_a.strategy_insights[-5:]  # 保留最近 5 条

        # 更新 B 对 A 的关系
        if data_a.agent_id not in data_b.social_relations:
            data_b.social_relations[data_a.agent_id] = SocialRelation()
        rel_b = data_b.social_relations[data_a.agent_id]
        rel_b.trust = max(0.0, min(1.0, rel_b.trust + chat_result.get("trust_delta_b", 0)))
        rel_b.friendliness = max(0.0, min(1.0, rel_b.friendliness + chat_result.get("friendliness_delta_b", 0)))
        rel_b.recent_interactions.append(interaction_record)
        rel_b.recent_interactions = rel_b.recent_interactions[-5:]
        # 更新关系备注
        note_b = chat_result.get("relation_note_b", "")
        if note_b:
            rel_b.notes = note_b
        # 记录策略收获
        insight_b = chat_result.get("strategy_insight_b", "")
        if insight_b:
            rel_b.strategy_insights.append(insight_b)
            rel_b.strategy_insights = rel_b.strategy_insights[-5:]

    def add_private_chat_record(
        self,
        player_name: str,
        partner_name: str,
        topic: str,
        summary: str,
    ):
        """添加私聊历史记录"""
        data = self.get_agent_data(player_name)
        if not data:
            return
        data.private_chat_history.append({
            "timestamp": datetime.now().isoformat(),
            "partner": partner_name,
            "topic": topic,
            "summary": summary,
        })
        data.private_chat_history = data.private_chat_history[-20:]  # 保留最近 20 条

    # ---------- 序列化/反序列化 ----------

    def _agent_data_to_dict(self, data: PersistentAgentData) -> dict:
        """数据类转字典（用于 JSON 写入）"""
        return {
            "agent_id": data.agent_id,
            "display_name": data.display_name,
            "statistics": {
                "games_played": data.statistics.games_played,
                "games_as_good": data.statistics.games_as_good,
                "games_as_evil": data.statistics.games_as_evil,
                "wins_as_good": data.statistics.wins_as_good,
                "wins_as_evil": data.statistics.wins_as_evil,
                "times_as_merlin": data.statistics.times_as_merlin,
                "times_assassinated": data.statistics.times_assassinated,
                "times_correct_assassination": data.statistics.times_correct_assassination,
                "last_game_timestamp": data.statistics.last_game_timestamp,
            },
            "strategy_memory": {
                "good_strategy_summary": data.strategy_memory.good_strategy_summary,
                "evil_strategy_summary": data.strategy_memory.evil_strategy_summary,
                "merlin_play_style": data.strategy_memory.merlin_play_style,
                "assassin_tactics": data.strategy_memory.assassin_tactics,
                "recent_lessons": data.strategy_memory.recent_lessons,
            },
            "social_relations": {
                k: {
                    "trust": v.trust,
                    "friendliness": v.friendliness,
                    "notes": v.notes,
                    "recent_interactions": v.recent_interactions,
                    "strategy_insights": v.strategy_insights,
                }
                for k, v in data.social_relations.items()
            },
            "player_impressions": {
                k: {
                    "play_style": v.play_style,
                    "tells": v.tells,
                    "suspected_evil_accuracy": v.suspected_evil_accuracy,
                }
                for k, v in data.player_impressions.items()
            },
            "private_chat_history": data.private_chat_history,
        }

    def _dict_to_agent_data(self, d: dict) -> PersistentAgentData:
        """字典转数据类（用于 JSON 读取）"""
        # 统计
        stats_d = d.get("statistics", {})
        statistics = AgentStatistics(
            games_played=stats_d.get("games_played", 0),
            games_as_good=stats_d.get("games_as_good", 0),
            games_as_evil=stats_d.get("games_as_evil", 0),
            wins_as_good=stats_d.get("wins_as_good", 0),
            wins_as_evil=stats_d.get("wins_as_evil", 0),
            times_as_merlin=stats_d.get("times_as_merlin", 0),
            times_assassinated=stats_d.get("times_assassinated", 0),
            times_correct_assassination=stats_d.get("times_correct_assassination", 0),
            last_game_timestamp=stats_d.get("last_game_timestamp", ""),
        )

        # 策略记忆
        strat_d = d.get("strategy_memory", {})
        strategy_memory = StrategyMemory(
            good_strategy_summary=strat_d.get("good_strategy_summary", ""),
            evil_strategy_summary=strat_d.get("evil_strategy_summary", ""),
            merlin_play_style=strat_d.get("merlin_play_style", ""),
            assassin_tactics=strat_d.get("assassin_tactics", ""),
            recent_lessons=strat_d.get("recent_lessons", []),
        )

        # 社交关系
        social_d = d.get("social_relations", {})
        social_relations = {}
        for k, v in social_d.items():
            social_relations[k] = SocialRelation(
                trust=v.get("trust", 0.5),
                friendliness=v.get("friendliness", 0.5),
                notes=v.get("notes", ""),
                recent_interactions=v.get("recent_interactions", []),
                strategy_insights=v.get("strategy_insights", []),
            )

        # 玩家印象
        imp_d = d.get("player_impressions", {})
        player_impressions = {}
        for k, v in imp_d.items():
            player_impressions[k] = PlayerImpression(
                play_style=v.get("play_style", ""),
                tells=v.get("tells", []),
                suspected_evil_accuracy=v.get("suspected_evil_accuracy", 0.5),
            )

        return PersistentAgentData(
            agent_id=d.get("agent_id", ""),
            display_name=d.get("display_name", ""),
            statistics=statistics,
            strategy_memory=strategy_memory,
            social_relations=social_relations,
            player_impressions=player_impressions,
            private_chat_history=d.get("private_chat_history", []),
        )
