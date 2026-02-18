"""社区运行器 - 管理多局游戏的主循环

游戏流程：
  加载持久化数据 → 运行游戏 → 更新统计 → 反思学习 → 私聊交流 → 保存数据
"""

import signal
import sys
from datetime import datetime

from engine.game_engine import GameEngine
from utils.logger import GameLogger
from community.persistent_agent import PersistentAgentManager
from community.reflection import ReflectionSystem
from community.private_chat import PrivateChatSystem
from community.statistics import CommunityStatistics
from config import STATS_REPORT_INTERVAL


class CommunityRunner:
    """持久化游戏社区运行器"""

    def __init__(self, data_dir: str = "data/agents", log_dir: str = "logs"):
        self.data_dir = data_dir
        self.log_dir = log_dir
        self.agent_manager = PersistentAgentManager(data_dir)
        self.reflection_system = ReflectionSystem()
        self.private_chat_system = PrivateChatSystem()
        self.statistics = CommunityStatistics()
        self._running = False
        self._interrupted = False

    # ==================== 运行模式 ====================

    def run_n_games(self, n: int):
        """运行 N 局游戏后自动停止"""
        self._setup_signal_handler()
        self._running = True

        for i in range(n):
            if self._interrupted:
                print(f"\n收到中断信号，已完成 {i}/{n} 局。")
                break

            self._print_game_header(i + 1, n)
            self._run_single_game_cycle()

            # 定期打印中间报告
            if (i + 1) % STATS_REPORT_INTERVAL == 0 and i + 1 < n:
                print("\n--- 中间统计报告 ---")
                self.statistics.print_report()

        self._running = False

    def run_continuous(self):
        """持续运行模式，Ctrl+C 优雅停止"""
        self._setup_signal_handler()
        self._running = True
        game_count = 0

        print("持续运行模式启动，按 Ctrl+C 在当前局结束后停止...\n")

        while not self._interrupted:
            game_count += 1
            self._print_game_header(game_count)
            self._run_single_game_cycle()

            # 定期打印中间报告
            if game_count % STATS_REPORT_INTERVAL == 0:
                print("\n--- 中间统计报告 ---")
                self.statistics.print_report()

        self._running = False
        print(f"\n已完成 {game_count} 局游戏。")

    # ==================== 信号处理 ====================

    def _setup_signal_handler(self):
        """设置 Ctrl+C 信号处理"""
        def handler(signum, frame):
            if self._running:
                print("\n\n[信号] 收到中断请求，将在当前游戏结束后停止...")
                self._interrupted = True
            else:
                sys.exit(0)

        signal.signal(signal.SIGINT, handler)

    # ==================== 核心循环 ====================

    def _run_single_game_cycle(self):
        """
        运行单局游戏的完整周期：
        1. 加载持久化 Agent 数据
        2. 运行游戏
        3. 更新统计
        4. 反思学习
        5. 私聊交流
        6. 保存数据
        """
        # 1. 加载持久化数据
        agents_data = self.agent_manager.load_all_agents()

        # 2. 运行游戏（传入持久化数据，run() 内部流程不变）
        logger = GameLogger(log_dir=self.log_dir)
        engine = GameEngine(logger=logger, persistent_data=agents_data)

        try:
            engine.run()
        except Exception as e:
            print(f"\n游戏运行出错: {e}")
            logger.close()
            return

        # 3. 提取结果并更新统计
        game_result = self._extract_game_result(engine)
        self.statistics.update(game_result)

        # 更新每个 Agent 的个人统计
        for player in engine.state.players:
            self.agent_manager.update_agent_statistics(
                player.player_name, game_result
            )

        # 4. 反思学习阶段
        self._do_reflection_phase(engine, game_result)

        # 5. 私聊交流阶段
        self._do_private_chat_phase(engine, game_result)

        # 6. 保存所有数据
        self.agent_manager.save_all_agents()

        logger.close()

    # ==================== 游戏结果提取 ====================

    def _extract_game_result(self, engine: GameEngine) -> dict:
        """从游戏引擎提取结果"""
        return {
            "game_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "winner": engine.state.winner,
            "end_reason": engine.state.end_reason,
            "players": [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "role": p.role.role_id,
                    "role_name_cn": p.role_name_cn,
                    "team": p.team.value,
                }
                for p in engine.state.players
            ],
            "mission_records": [
                r.to_dict() for r in engine.state.mission_records
            ],
            "assassin_phase": engine.assassin_phase_data,
        }

    # ==================== 反思阶段 ====================

    def _do_reflection_phase(self, engine: GameEngine, game_result: dict):
        """反思学习阶段"""
        print("\n--- 反思学习阶段 ---\n")

        for player_id, agent in engine.agents.items():
            player = engine.state.get_player(player_id)
            persistent_data = self.agent_manager.get_agent_data(player.player_name)

            reflection = self.reflection_system.reflect(
                agent=agent,
                game_result=game_result,
                persistent_data=persistent_data,
                agent_memory=agent.memory,
            )

            # 更新持久化数据
            self.agent_manager.update_agent_reflection(
                player.player_name, reflection
            )

    # ==================== 私聊阶段 ====================

    def _do_private_chat_phase(self, engine: GameEngine, game_result: dict):
        """私聊交流阶段"""
        print("\n--- 私聊交流阶段 ---\n")

        # 选择配对
        chat_pairs = self.private_chat_system.select_chat_pairs(
            list(engine.agents.keys()),
            game_result,
        )

        if not chat_pairs:
            print("  本轮无私聊。")
            return

        for player_a_id, player_b_id in chat_pairs:
            agent_a = engine.agents[player_a_id]
            agent_b = engine.agents[player_b_id]

            chat_result = self.private_chat_system.conduct_chat(
                agent_a, agent_b, game_result
            )

            # 更新社交关系
            self.agent_manager.update_social_relation(
                agent_a.player_name,
                agent_b.player_name,
                chat_result,
            )

            # 记录私聊历史
            topic = chat_result.get("topic", "")
            summary = chat_result.get("summary", "")
            self.agent_manager.add_private_chat_record(
                agent_a.player_name, agent_b.player_name, topic, summary,
            )
            self.agent_manager.add_private_chat_record(
                agent_b.player_name, agent_a.player_name, topic, summary,
            )

    # ==================== 辅助 ====================

    def _print_game_header(self, game_num: int, total: int | None = None):
        """打印游戏开始横幅"""
        print(f"\n{'=' * 60}")
        if total:
            print(f"  第 {game_num}/{total} 局游戏")
        else:
            print(f"  第 {game_num} 局游戏 (持续模式)")
        print(f"{'=' * 60}\n")
