"""游戏引擎 - 主控制流程"""

import json
import os
import random
from datetime import datetime

from models.role import ROLES, Team
from models.player import Player
from models.game_state import GameState, MissionRecord
from agents.agent import Agent
from config import (
    PLAYER_COUNT,
    ROLES_CONFIG,
    PLAYER_NAMES,
    MISSION_TEAM_SIZES,
    MAX_TEAM_VOTES,
    MODEL_CONFIG
)
from utils.logger import GameLogger
from engine.night_phase import execute_night_phase
from engine.team_phase import execute_team_phase
from engine.vote_phase import execute_discussion, execute_vote
from engine.mission_phase import execute_mission
from engine.assassin_phase import execute_assassin_phase


class GameEngine:
    """阿瓦隆游戏引擎"""

    def __init__(self, logger: GameLogger | None = None, persistent_data: dict | None = None):
        self.state = GameState()
        self.agents: dict[int, Agent] = {}
        self.logger = logger or GameLogger()
        self.assassin_phase_data: dict | None = None
        self.persistent_data = persistent_data

    def setup(self):
        """初始化游戏：分配角色、创建Agent"""
        self.logger.banner("游戏初始化")

        # 构建角色列表并随机分配
        role_ids = ROLES_CONFIG["good"] + ROLES_CONFIG["evil"]
        random.shuffle(role_ids)

        self.logger.system(f"6名玩家已就座，正在随机分配角色...")

        for i in range(PLAYER_COUNT):
            role_info = ROLES[role_ids[i]]
            player = Player(
                player_id=i,
                player_name=PLAYER_NAMES[i],
                role=role_info,
            )
            self.state.players.append(player)

        # 随机选择起始队长
        self.state.current_leader_idx = random.randint(0, PLAYER_COUNT - 1)
        self.state.players[self.state.current_leader_idx].is_leader = True

        self.logger.system(
            f"起始队长: {self.state.current_leader.player_name}"
        )

        # 创建Agent（在夜晚阶段之后，因为需要先设置夜晚信息）

    def _create_agents(self):
        """创建所有Agent（在夜晚阶段之后调用）"""
        for player in self.state.players:
            agent = Agent(player)

            # 社区模式：注入持久化记忆
            if self.persistent_data:
                self._inject_persistence(agent, player)

            self.agents[player.player_id] = agent

        # 显示阵营信息（仅日志文件）
        good_players = [p for p in self.state.players if p.is_good]
        evil_players = [p for p in self.state.players if p.is_evil]

        self.logger.system(f"正义阵营 ({len(good_players)}人) 使用模型: {MODEL_CONFIG['good']}")
        self.logger.system(f"邪恶阵营 ({len(evil_players)}人) 使用模型: {MODEL_CONFIG['evil']}")

    @staticmethod
    def _extract_player_num(pid: str) -> str:
        """从各种格式的玩家ID中提取数字部分
        
        支持: 'player_1', '1', '玩家1', 'Player 1', 'player1' 等
        """
        import re
        if "_" in pid:
            parts = pid.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                return parts[1]
        # 回退：提取字符串中的数字
        nums = re.findall(r'\d+', pid)
        if nums:
            return nums[0]
        return pid  # 无法解析时返回原始值

    def _inject_persistence(self, agent, player):
        """注入持久化记忆到 Agent（社区模式）"""
        agent_id = f"player_{player.player_id + 1}"
        pdata = self.persistent_data.get(agent_id)
        if not pdata:
            return

        # 1. 注入策略记忆到系统提示词
        strategy = ""
        if player.is_good and pdata.strategy_memory.good_strategy_summary:
            strategy = pdata.strategy_memory.good_strategy_summary
        elif player.is_evil and pdata.strategy_memory.evil_strategy_summary:
            strategy = pdata.strategy_memory.evil_strategy_summary

        if strategy:
            agent.system_prompt += f"\n\n### 你的历史策略总结：\n{strategy}"

        # 注入近期教训
        if pdata.strategy_memory.recent_lessons:
            lessons = "\n".join(
                [f"- {l['lesson']}" for l in pdata.strategy_memory.recent_lessons[-3:]]
            )
            agent.system_prompt += f"\n\n### 近期教训：\n{lessons}"

        # 2. 注入社交关系到初始记忆（包含原因和具体经历）
        context_parts = []
        for pid, relation in pdata.social_relations.items():
            player_num = self._extract_player_num(pid)
            # 细粒度信任描述
            if relation.trust > 0.7:
                trust_desc = "很信任"
            elif relation.trust > 0.55:
                trust_desc = "比较信任"
            elif relation.trust > 0.45:
                trust_desc = "中立"
            elif relation.trust > 0.3:
                trust_desc = "有些不信任"
            else:
                trust_desc = "很不信任"

            line = f"- 玩家{player_num}: {trust_desc}(信任{relation.trust:.2f}/友好{relation.friendliness:.2f})"
            # 附加关系备注（说明为什么信任/不信任）
            if relation.notes:
                line += f"\n  原因: {relation.notes}"
            # 附加最近一次互动
            if relation.recent_interactions:
                last = relation.recent_interactions[-1]
                line += f"\n  最近互动: {last.get('event', '')}"
            context_parts.append(line)

        # 注入从私聊中获得的策略收获
        strategy_from_chat = []
        for pid, relation in pdata.social_relations.items():
            player_num = self._extract_player_num(pid)
            if relation.strategy_insights:
                for insight in relation.strategy_insights[-2:]:
                    strategy_from_chat.append(f"- 从玩家{player_num}处学到: {insight}")

        # 注入玩家印象（行为画像）
        for pid, impression in pdata.player_impressions.items():
            player_num = self._extract_player_num(pid)
            imp_parts = []
            if impression.play_style:
                imp_parts.append(f"风格: {impression.play_style}")
            if impression.tells:
                imp_parts.append(f"特征: {impression.tells[-1]}")
            if imp_parts:
                context_parts.append(f"- 玩家{player_num}的画像: {'; '.join(imp_parts)}")

        if context_parts:
            memory_text = "[社区记忆] 你对其他玩家的了解：\n" + "\n".join(context_parts)
            if strategy_from_chat:
                memory_text += "\n\n从私聊中获得的策略收获：\n" + "\n".join(strategy_from_chat)
            agent.memory.add("user", memory_text)
            agent.memory.add("assistant", "好的，我会参考这些历史信息和策略收获来做决策。")

    def run(self):
        """运行完整的游戏流程"""
        # 1. 初始化
        self.setup()

        # 2. 夜晚阶段
        execute_night_phase(self.state, self.logger)

        # 3. 创建Agent（在夜晚信息设置完成后）
        self._create_agents()

        # 4. 任务阶段（最多5轮）
        for round_num in range(5):
            self.state.current_round = round_num

            self.logger.banner(
                f"第{round_num + 1}轮任务 "
                f"(需要{MISSION_TEAM_SIZES[round_num]}人)"
            )

            # 组队-投票循环
            team_approved = False
            self.state.consecutive_rejects = 0

            while not team_approved:
                # 组队
                team = execute_team_phase(
                    self.state, self.agents, self.logger
                )

                # 创建任务记录
                record = MissionRecord(
                    round_num=round_num + 1,
                    team_leader_id=self.state.current_leader_idx,
                    team_members=list(team),
                )

                # 讨论
                execute_discussion(
                    self.state, self.agents, self.logger, record
                )

                # 投票
                team_approved = execute_vote(
                    self.state, self.agents, self.logger, record
                )

                # 无论通过与否，都保存记录（被否决的组队信息也很重要）
                self.state.mission_records.append(record)

                if not team_approved:
                    self.state.consecutive_rejects += 1

                    # 检查是否连续5次被否决
                    if self.state.consecutive_rejects >= MAX_TEAM_VOTES:
                        self.state.game_over = True
                        self.state.winner = "evil"
                        self.state.end_reason = "连续5次组队被否决，邪恶阵营获胜！"
                        self.logger.result(self.state.end_reason, good_wins=False)
                        self._reveal_identities()
                        self._export_replay_json()
                        self.logger.close()
                        return

                    # 换队长
                    self.state.next_leader()
                    self.logger.system(
                        f"队长轮转至 {self.state.current_leader.player_name}"
                    )

            # 执行任务
            mission_success = execute_mission(
                self.state, self.agents, self.logger, record
            )

            # 检查胜负
            if self.state.good_wins_count >= 3:
                # 好人任务达成，进入刺杀阶段
                self.assassin_phase_data = execute_assassin_phase(
                    self.state, self.agents, self.logger
                )
                if self.assassin_phase_data["merlin_killed"]:
                    self.state.game_over = True
                    self.state.winner = "evil"
                    self.state.end_reason = "梅林被刺杀！邪恶阵营逆转获胜！"
                    self.logger.result(self.state.end_reason, good_wins=False)
                else:
                    self.state.game_over = True
                    self.state.winner = "good"
                    self.state.end_reason = "正义阵营完成三次任务且梅林存活！正义阵营获胜！"
                    self.logger.result(self.state.end_reason, good_wins=True)

                self._reveal_identities()
                self._export_replay_json()
                self.logger.close()
                return

            if self.state.evil_wins_count >= 3:
                self.state.game_over = True
                self.state.winner = "evil"
                self.state.end_reason = "三次任务失败！邪恶阵营获胜！"
                self.logger.result(self.state.end_reason, good_wins=False)
                self._reveal_identities()
                self._export_replay_json()
                self.logger.close()
                return

            # 下一轮，轮转队长
            self.state.next_leader()

        # 如果5轮都打完还没分出胜负（理论上不会到这里）
        self.logger.system("游戏异常结束")
        self._export_replay_json()
        self.logger.close()

    def _reveal_identities(self):
        """揭晓所有玩家的真实身份"""
        self.logger.phase("身份揭晓")
        for player in self.state.players:
            team_str = "正义" if player.is_good else "邪恶"
            self.logger.system(
                f"{player.player_name} → {player.role_name_cn} ({team_str}阵营)"
            )

    def _export_replay_json(self):
        """导出游戏回放JSON文件"""
        try:
            replay_data = self.state.to_dict()
            replay_data["game_config"] = {
                "player_count": PLAYER_COUNT,
                "mission_team_sizes": MISSION_TEAM_SIZES,
            }
            if self.assassin_phase_data:
                replay_data["assassin_phase"] = self.assassin_phase_data

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = self.logger.log_dir
            json_path = os.path.join(log_dir, f"replay_{timestamp}.json")

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(replay_data, f, ensure_ascii=False, indent=2)

            self.logger.system(f"回放文件已保存: {json_path}")
        except Exception as e:
            self.logger.system(f"导出回放文件失败: {e}")
