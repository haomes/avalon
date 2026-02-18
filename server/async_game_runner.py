"""异步游戏运行器 - 将同步游戏引擎包装为可暂停/步进的异步流程

复刻 GameEngine.run() 和 CommunityRunner._run_single_game_cycle() 的完整逻辑，
但在每个关键步骤间插入 checkpoint 以支持暂停、单步和实时事件推送。
"""

import asyncio
import time
from datetime import datetime
from functools import partial

from server.event_emitter import EventEmitter

from engine.game_engine import GameEngine
from engine.night_phase import execute_night_phase
from engine.team_phase import execute_team_phase
from engine.vote_phase import execute_discussion, execute_vote
from engine.mission_phase import execute_mission
from engine.assassin_phase import execute_assassin_phase
from utils.logger import GameLogger
from models.game_state import MissionRecord
from community.persistent_agent import PersistentAgentManager, PersistentAgentData
from community.reflection import ReflectionSystem
from community.private_chat import PrivateChatSystem
from community.statistics import CommunityStatistics
from config import (
    PLAYER_COUNT,
    MISSION_TEAM_SIZES,
    MISSION_FAIL_REQUIRED,
    MAX_TEAM_VOTES,
    COMMUNITY_DATA_DIR,
    STATS_REPORT_INTERVAL,
)


class AsyncGameRunner:
    """可暂停 / 单步执行的异步游戏运行器"""

    # 状态机常量
    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_FINISHED = "finished"

    def __init__(self, emitter: EventEmitter, log_dir: str = "logs"):
        self.emitter = emitter
        self.log_dir = log_dir

        # 控制信号
        self._pause_event = asyncio.Event()  # clear → 暂停, set → 运行
        self._pause_event.set()  # 默认不暂停
        self._stop_requested = False

        self.state = self.STATE_IDLE
        self.step_mode = False

        # 当前引擎引用（用于查询）
        self.engine: GameEngine | None = None
        self.statistics = CommunityStatistics()

    # ------------------------------------------------------------------
    # 控制方法
    # ------------------------------------------------------------------

    def pause(self):
        """暂停游戏"""
        if self.state == self.STATE_RUNNING:
            self._pause_event.clear()
            self.state = self.STATE_PAUSED

    def resume(self):
        """恢复游戏"""
        if self.state == self.STATE_PAUSED:
            self.step_mode = False
            self.state = self.STATE_RUNNING
            self._pause_event.set()

    def step(self):
        """单步执行：恢复一个 checkpoint 后自动暂停"""
        if self.state == self.STATE_PAUSED:
            self.step_mode = True
            self.state = self.STATE_RUNNING
            self._pause_event.set()

    def stop(self):
        """停止当前游戏"""
        self._stop_requested = True
        # 如果正在暂停状态，需要先唤醒以便循环检测到 stop
        if self.state == self.STATE_PAUSED:
            self._pause_event.set()

    # ------------------------------------------------------------------
    # checkpoint
    # ------------------------------------------------------------------

    async def _checkpoint(self):
        """
        在每个关键步骤之间调用。
        - 如果 step_mode 为 True，自动暂停
        - 如果处于暂停状态，等待 resume / step 信号
        - 如果收到 stop 信号，抛出 _StopGame
        """
        if self._stop_requested:
            raise _StopGame()

        if self.step_mode:
            self._pause_event.clear()
            self.state = self.STATE_PAUSED
            await self.emitter.emit("runner_paused", {"reason": "step"})

        await self._pause_event.wait()

        if self._stop_requested:
            raise _StopGame()

    # ------------------------------------------------------------------
    # 社区模式入口
    # ------------------------------------------------------------------

    async def run_community_session(self, num_games: int, continuous: bool = False):
        """运行社区模式：多局游戏 + 反思 + 私聊"""
        self.state = self.STATE_RUNNING
        self._stop_requested = False
        self._pause_event.set()

        agent_manager = PersistentAgentManager(COMMUNITY_DATA_DIR)

        game_count = 0

        try:
            while True:
                if not continuous and game_count >= num_games:
                    break
                if self._stop_requested:
                    break

                game_count += 1
                await self._checkpoint()

                agents_data = agent_manager.load_all_agents()
                await self.emitter.emit(
                    "community_game_start",
                    {
                        "game_num": game_count,
                        "total": num_games if not continuous else None,
                    },
                )

                # 运行单局
                engine = await self.run_single_game(persistent_data=agents_data)

                if engine is None or engine.state.winner is None:
                    continue

                # 提取结果
                game_result = self._extract_game_result(engine)
                self.statistics.update(game_result)

                # 更新每个 Agent 的统计
                for player in engine.state.players:
                    agent_manager.update_agent_statistics(
                        player.player_name, game_result
                    )

                # 反思阶段
                await self._run_reflection_phase(engine, game_result, agent_manager)

                # 私聊阶段
                await self._run_private_chat_phase(engine, game_result, agent_manager)

                # 保存
                agent_manager.save_all_agents()

                stats_report = self.statistics.generate_report()
                await self.emitter.emit("stats_update", stats_report)

                # 定期打印
                if game_count % STATS_REPORT_INTERVAL == 0:
                    self.statistics.print_report()

        except _StopGame:
            await self.emitter.emit("session_stopped", {"games_completed": game_count})
        finally:
            self.state = self.STATE_FINISHED
            await self.emitter.emit(
                "session_ended",
                {"games_completed": game_count, "stats": self.statistics.generate_report()},
            )

    # ------------------------------------------------------------------
    # 单局游戏入口
    # ------------------------------------------------------------------

    async def run_single_game(self, persistent_data=None) -> GameEngine | None:
        """运行单局完整游戏，返回 GameEngine（供上层提取结果）。"""

        if self.state != self.STATE_RUNNING and self.state != self.STATE_PAUSED:
            self.state = self.STATE_RUNNING
            self._stop_requested = False
            self._pause_event.set()

        loop = asyncio.get_event_loop()

        logger = GameLogger(log_dir=self.log_dir)
        engine = GameEngine(logger=logger, persistent_data=persistent_data)
        self.engine = engine
        self._current_persistent_data = persistent_data  # 保存引用供 profile 使用

        try:
            # 1. 初始化
            await loop.run_in_executor(None, engine.setup)

            # 2. 夜晚阶段
            await self._run_night_phase(engine, loop)

            # 3. 创建 Agent
            engine._create_agents()

            # 通知: 游戏开始
            players_info = [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "role_id": p.role.role_id,
                    "role_name_cn": p.role_name_cn,
                    "team": p.team.value,
                }
                for p in engine.state.players
            ]
            await self.emitter.emit(
                "game_started",
                {
                    "players": players_info,
                    "leader_idx": engine.state.current_leader_idx,
                },
            )

            # 发送所有 Agent profile 到前端 AGENTS 面板
            await self._emit_all_agents(engine, persistent_data)

            # 4. 任务轮次 (最多 5 轮)
            for round_num in range(5):
                engine.state.current_round = round_num
                await self._checkpoint()

                round_result = await self._run_round(engine, round_num, loop)
                if round_result is None:
                    # stop 请求
                    break

                # 检查胜负
                if engine.state.game_over:
                    break

            # 5. 游戏结束
            if engine.state.winner:
                await self.emitter.emit(
                    "game_ended",
                    {
                        "winner": engine.state.winner,
                        "reason": engine.state.end_reason,
                        "players": players_info,
                    },
                )

            logger.close()
            return engine

        except _StopGame:
            await self.emitter.emit(
                "game_stopped",
                {"reason": "用户终止"},
            )
            logger.close()
            return engine

    # ------------------------------------------------------------------
    # 夜晚阶段
    # ------------------------------------------------------------------

    async def _run_night_phase(self, engine: GameEngine, loop: asyncio.AbstractEventLoop):
        await self.emitter.emit("phase_started", {"phase": "night"})
        await loop.run_in_executor(
            None, execute_night_phase, engine.state, engine.logger
        )
        await self.emitter.emit("phase_completed", {"phase": "night"})

    # ------------------------------------------------------------------
    # 单轮: 组队 → 讨论 → 投票 → 任务
    # ------------------------------------------------------------------

    async def _run_round(
        self, engine: GameEngine, round_num: int, loop: asyncio.AbstractEventLoop
    ):
        """运行一轮完整的 组队→讨论→投票→(任务) 循环，处理否决重试。"""

        team_size = MISSION_TEAM_SIZES[round_num]

        await self.emitter.emit(
            "round_started",
            {
                "round": round_num + 1,
                "team_size": team_size,
                "leader_id": engine.state.current_leader_idx,
            },
        )

        engine.state.consecutive_rejects = 0
        team_approved = False

        while not team_approved:
            await self._checkpoint()

            leader_idx = engine.state.current_leader_idx
            leader_name = engine.state.current_leader.player_name

            # ---- 组队 ----
            await self.emitter.emit(
                "phase_started",
                {
                    "phase": "team_proposal",
                    "round": round_num + 1,
                    "leader_id": leader_idx,
                },
            )

            await self.emitter.emit(
                "agent_thinking",
                {"player_id": leader_idx, "action": "proposing_team"},
            )

            team = await loop.run_in_executor(
                None, execute_team_phase, engine.state, engine.agents, engine.logger
            )

            await self.emitter.emit(
                "team_proposed",
                {
                    "leader_id": leader_idx,
                    "team": list(team),
                    "round": round_num + 1,
                },
            )

            # 创建任务记录
            record = MissionRecord(
                round_num=round_num + 1,
                team_leader_id=leader_idx,
                team_members=list(team),
            )

            # ---- 讨论 ----
            await self._run_discussion(engine, record, round_num, loop)

            # ---- 投票 ----
            approved = await self._run_vote(engine, record, round_num, loop)

            # 保存记录
            engine.state.mission_records.append(record)

            if not approved:
                engine.state.consecutive_rejects += 1

                # 5 次否决 → 邪恶获胜
                if engine.state.consecutive_rejects >= MAX_TEAM_VOTES:
                    engine.state.game_over = True
                    engine.state.winner = "evil"
                    engine.state.end_reason = "连续5次组队被否决，邪恶阵营获胜！"
                    engine.logger.result(engine.state.end_reason, good_wins=False)
                    engine._reveal_identities()
                    engine._export_replay_json()

                    await self.emitter.emit(
                        "game_ended",
                        {
                            "winner": "evil",
                            "reason": engine.state.end_reason,
                            "players": self._players_info(engine),
                        },
                    )
                    return None

                # 换队长
                engine.state.next_leader()
                engine.logger.system(
                    f"队长轮转至 {engine.state.current_leader.player_name}"
                )
                await self.emitter.emit(
                    "leader_changed",
                    {"new_leader_id": engine.state.current_leader_idx},
                )
            else:
                team_approved = True

        # ---- 执行任务 ----
        await self._run_mission(engine, record, round_num, loop)

        # 检查胜负
        if engine.state.good_wins_count >= 3:
            # 进入刺杀阶段
            assassin_result = await self._run_assassin_phase(engine, loop)
            engine.assassin_phase_data = assassin_result

            if assassin_result["merlin_killed"]:
                engine.state.game_over = True
                engine.state.winner = "evil"
                engine.state.end_reason = "梅林被刺杀！邪恶阵营逆转获胜！"
                engine.logger.result(engine.state.end_reason, good_wins=False)
            else:
                engine.state.game_over = True
                engine.state.winner = "good"
                engine.state.end_reason = "正义阵营完成三次任务且梅林存活！正义阵营获胜！"
                engine.logger.result(engine.state.end_reason, good_wins=True)

            engine._reveal_identities()
            engine._export_replay_json()
            return True

        if engine.state.evil_wins_count >= 3:
            engine.state.game_over = True
            engine.state.winner = "evil"
            engine.state.end_reason = "三次任务失败！邪恶阵营获胜！"
            engine.logger.result(engine.state.end_reason, good_wins=False)
            engine._reveal_identities()
            engine._export_replay_json()
            return True

        # 下一轮，轮转队长
        engine.state.next_leader()
        return True

    # ------------------------------------------------------------------
    # 讨论阶段（逐人发言）
    # ------------------------------------------------------------------

    async def _run_discussion(
        self,
        engine: GameEngine,
        record: MissionRecord,
        round_num: int,
        loop: asyncio.AbstractEventLoop,
    ):
        await self.emitter.emit(
            "phase_started",
            {"phase": "discussion", "round": round_num + 1},
        )

        engine.logger.phase("讨论阶段 - 玩家依次发言")

        team_names = [f"玩家{t + 1}" for t in engine.state.proposed_team]
        leader_name = engine.state.current_leader.player_name
        leader_idx = engine.state.current_leader_idx

        # 从队长的下一位开始，队长最后发言
        speaking_order = []
        for i in range(1, len(engine.state.players)):
            idx = (leader_idx + i) % len(engine.state.players)
            speaking_order.append(idx)
        speaking_order.append(leader_idx)

        all_speeches: list[tuple[str, str]] = []

        for pid in speaking_order:
            await self._checkpoint()

            player = engine.state.get_player(pid)
            agent = engine.agents[pid]

            await self.emitter.emit(
                "agent_thinking",
                {"player_id": pid, "action": "speaking"},
            )

            # 构建发言上下文（与 vote_phase.py 中的 execute_discussion 一致）
            context_parts = [
                f"当前是第{round_num + 1}轮任务。",
                f"队长{leader_name}提议的队伍是: {', '.join(team_names)}",
                "",
                engine.state.get_public_history(),
            ]
            if all_speeches:
                context_parts.append("\n已有玩家的发言:")
                for name, speech in all_speeches:
                    context_parts.append(f"  {name}: {speech}")
            context = "\n".join(context_parts)

            speech = await loop.run_in_executor(None, agent.speak, context)
            all_speeches.append((player.player_name, speech))
            record.speeches[pid] = speech

            # 日志
            engine.logger.speech(player.player_name, player.team.value, speech)

            # 通知其他 Agent 观察到发言
            event_text = f"{player.player_name}发言: {speech}"
            for other_agent in engine.agents.values():
                if other_agent.player_id != pid:
                    other_agent.observe(event_text)

            await self.emitter.emit(
                "agent_speech",
                {
                    "player_id": pid,
                    "player_name": player.player_name,
                    "text": speech,
                    "round": round_num + 1,
                },
            )

    # ------------------------------------------------------------------
    # 投票阶段（逐人投票）
    # ------------------------------------------------------------------

    async def _run_vote(
        self,
        engine: GameEngine,
        record: MissionRecord,
        round_num: int,
        loop: asyncio.AbstractEventLoop,
    ) -> bool:
        await self.emitter.emit(
            "phase_started",
            {"phase": "vote", "round": round_num + 1},
        )

        engine.logger.phase("投票阶段 - 是否同意该队伍出发")

        team_names = [f"玩家{t + 1}" for t in engine.state.proposed_team]
        leader_name = engine.state.current_leader.player_name

        approve_count = 0
        reject_count = 0

        for pid in range(len(engine.state.players)):
            await self._checkpoint()

            player = engine.state.get_player(pid)
            agent = engine.agents[pid]

            await self.emitter.emit(
                "agent_thinking",
                {"player_id": pid, "action": "voting"},
            )

            # 构建投票上下文（与 vote_phase.py 中的 execute_vote 一致）
            context_parts = [
                f"第{round_num + 1}轮任务。",
                f"队长{leader_name}提议的队伍: {', '.join(team_names)}",
                "",
                engine.state.get_public_history(),
            ]
            if record.speeches:
                context_parts.append("\n本轮讨论中的发言:")
                for spid, speech in record.speeches.items():
                    context_parts.append(f"  玩家{spid + 1}: {speech}")

            failed_info = engine.state.get_failed_team_history_for_round()
            if failed_info:
                context_parts.append(f"\n重要提醒: {failed_info}")

            if engine.state.consecutive_rejects >= 4:
                context_parts.append(
                    "\n【紧急！】这是第5次投票（强制轮），如果这次投票仍不通过，邪恶阵营将直接获胜！"
                )

            context = "\n".join(context_parts)

            voted = await loop.run_in_executor(None, agent.vote_team, context)
            record.team_votes[pid] = voted

            if voted:
                approve_count += 1
            else:
                reject_count += 1

            engine.logger.vote(player.player_name, voted)

            await self.emitter.emit(
                "agent_vote",
                {
                    "player_id": pid,
                    "player_name": player.player_name,
                    "approved": voted,
                },
            )

        # 判定
        approved = approve_count > reject_count

        if approved:
            engine.logger.system(
                f"投票通过！({approve_count}票同意, {reject_count}票反对) 队伍出发执行任务！"
            )
        else:
            engine.logger.system(
                f"投票未通过！({approve_count}票同意, {reject_count}票反对) 换下一个队长组队。"
            )

        # 通知所有 Agent
        result_text = "通过" if approved else "未通过"
        event_text = (
            f"组队投票结果: {result_text} ({approve_count}同意/{reject_count}反对)。"
            f"队伍: {', '.join(team_names)}"
        )
        for agent in engine.agents.values():
            agent.observe(event_text)

        votes_detail = {
            str(pid): v for pid, v in record.team_votes.items()
        }
        await self.emitter.emit(
            "vote_result",
            {
                "approved": approved,
                "approve_count": approve_count,
                "reject_count": reject_count,
                "votes": votes_detail,
                "round": round_num + 1,
            },
        )

        return approved

    # ------------------------------------------------------------------
    # 任务执行阶段
    # ------------------------------------------------------------------

    async def _run_mission(
        self,
        engine: GameEngine,
        record: MissionRecord,
        round_num: int,
        loop: asyncio.AbstractEventLoop,
    ):
        await self.emitter.emit(
            "phase_started",
            {"phase": "mission", "round": round_num + 1},
        )

        engine.logger.phase(f"任务执行阶段 - 第{round_num + 1}轮")

        team_names = [f"玩家{t + 1}" for t in engine.state.proposed_team]
        engine.logger.system(f"执行任务的队伍: {', '.join(team_names)}")

        fail_required = MISSION_FAIL_REQUIRED[round_num]
        success_count = 0
        fail_count = 0

        for pid in engine.state.proposed_team:
            await self._checkpoint()

            agent = engine.agents[pid]
            player = engine.state.get_player(pid)

            if player.is_good:
                # 好人只能投成功
                record.mission_votes[pid] = True
                success_count += 1
                engine.logger.secret(
                    f"玩家{pid + 1}({player.role_name_cn}) 投了 [成功] 票"
                )
            else:
                await self.emitter.emit(
                    "agent_thinking",
                    {"player_id": pid, "action": "mission_vote"},
                )

                # 构建任务上下文（与 mission_phase.py 一致）
                context_parts = [
                    f"你正在执行第{round_num + 1}轮任务。",
                    f"队伍成员: {', '.join(team_names)}",
                    f"当前比分: 正义 {engine.state.good_wins_count} : {engine.state.evil_wins_count} 邪恶",
                ]
                if engine.state.mission_records:
                    context_parts.append("\n历史:")
                    context_parts.append(engine.state.get_public_history())
                context = "\n".join(context_parts)

                action_success = await loop.run_in_executor(
                    None, agent.mission_action, context
                )
                record.mission_votes[pid] = action_success

                if action_success:
                    success_count += 1
                else:
                    fail_count += 1

                action_text = "成功" if action_success else "失败"
                engine.logger.secret(
                    f"玩家{pid + 1}({player.role_name_cn}) 投了 [{action_text}] 票"
                )

                await self.emitter.emit(
                    "agent_mission_vote",
                    {"player_id": pid, "success": action_success},
                )

        # 判定
        mission_success = fail_count < fail_required
        record.success = mission_success

        engine.logger.system(
            f"任务卡翻开: {success_count}张成功票, {fail_count}张失败票"
        )
        engine.logger.mission(mission_success)
        engine.state.mission_results.append(mission_success)
        engine.logger.score(engine.state.good_wins_count, engine.state.evil_wins_count)

        # 通知所有 Agent
        event_text = (
            f"第{round_num + 1}轮任务{'成功' if mission_success else '失败'}！"
            f"({success_count}张成功票, {fail_count}张失败票) "
            f"当前比分: 正义 {engine.state.good_wins_count} : {engine.state.evil_wins_count} 邪恶"
        )
        for agent in engine.agents.values():
            agent.observe(event_text)

        await self.emitter.emit(
            "mission_result",
            {
                "success": mission_success,
                "success_count": success_count,
                "fail_count": fail_count,
                "round": round_num + 1,
            },
        )
        await self.emitter.emit(
            "score_update",
            {
                "good_wins": engine.state.good_wins_count,
                "evil_wins": engine.state.evil_wins_count,
            },
        )

    # ------------------------------------------------------------------
    # 刺杀阶段
    # ------------------------------------------------------------------

    async def _run_assassin_phase(
        self, engine: GameEngine, loop: asyncio.AbstractEventLoop
    ) -> dict:
        await self._checkpoint()
        await self.emitter.emit("phase_started", {"phase": "assassin"})

        result = await loop.run_in_executor(
            None,
            execute_assassin_phase,
            engine.state,
            engine.agents,
            engine.logger,
        )

        await self.emitter.emit(
            "assassin_result",
            {
                "merlin_killed": result["merlin_killed"],
                "assassin_id": result["assassin_id"],
                "target_id": result["target_id"],
            },
        )
        return result

    # ------------------------------------------------------------------
    # 反思阶段（社区模式）
    # ------------------------------------------------------------------

    async def _run_reflection_phase(
        self,
        engine: GameEngine,
        game_result: dict,
        agent_manager: PersistentAgentManager,
    ):
        await self.emitter.emit("phase_started", {"phase": "reflection"})

        loop = asyncio.get_event_loop()
        reflection_system = ReflectionSystem()

        for player_id, agent in engine.agents.items():
            await self._checkpoint()

            player = engine.state.get_player(player_id)
            persistent_data = agent_manager.get_agent_data(player.player_name)

            await self.emitter.emit(
                "agent_thinking",
                {"player_id": player_id, "action": "reflecting"},
            )

            try:
                reflection = await loop.run_in_executor(
                    None,
                    reflection_system.reflect,
                    agent,
                    game_result,
                    persistent_data,
                    agent.memory,
                )
            except Exception as e:
                print(f"  [反思] {player.player_name} 反思异常: {e}")
                reflection = {"lesson": "反思过程出错", "strategy_update": ""}

            agent_manager.update_agent_reflection(player.player_name, reflection)

            await self.emitter.emit(
                "agent_reflection",
                {
                    "player_id": player_id,
                    "player_name": player.player_name,
                    "lesson": reflection.get("lesson", ""),
                    "strategy_update": reflection.get("strategy_update", ""),
                },
            )

            # 反思后更新该 Agent 的 profile 卡片
            updated_data = agent_manager.get_agent_data(player.player_name)
            await self.emitter.emit(
                "agent_profile",
                self._build_agent_profile(player, updated_data),
            )

        await self.emitter.emit("phase_completed", {"phase": "reflection"})

    # ------------------------------------------------------------------
    # 私聊阶段（社区模式）
    # ------------------------------------------------------------------

    async def _run_private_chat_phase(
        self,
        engine: GameEngine,
        game_result: dict,
        agent_manager: PersistentAgentManager,
    ):
        await self.emitter.emit("phase_started", {"phase": "private_chat"})

        loop = asyncio.get_event_loop()
        chat_system = PrivateChatSystem()

        chat_pairs = chat_system.select_chat_pairs(
            list(engine.agents.keys()), game_result
        )

        if not chat_pairs:
            await self.emitter.emit("phase_completed", {"phase": "private_chat", "pairs": 0})
            return

        for player_a_id, player_b_id in chat_pairs:
            await self._checkpoint()

            agent_a = engine.agents[player_a_id]
            agent_b = engine.agents[player_b_id]

            await self.emitter.emit(
                "private_chat_start",
                {
                    "from_id": player_a_id,
                    "from_name": agent_a.player_name,
                    "to_id": player_b_id,
                    "to_name": agent_b.player_name,
                    "message": f"{agent_a.player_name} 与 {agent_b.player_name} 开始私聊",
                },
            )

            try:
                chat_result = await loop.run_in_executor(
                    None, chat_system.conduct_chat, agent_a, agent_b, game_result
                )
            except Exception as e:
                print(f"  [私聊] 执行异常: {e}")
                chat_result = {
                    "summary": "私聊异常中断", "topic": "",
                    "trust_delta_a": 0, "trust_delta_b": 0,
                    "friendliness_delta_a": 0, "friendliness_delta_b": 0,
                    "chat_log": [], "relation_note_a": "", "relation_note_b": "",
                    "strategy_insight_a": "", "strategy_insight_b": "",
                }

            # 更新社交关系
            agent_manager.update_social_relation(
                agent_a.player_name, agent_b.player_name, chat_result
            )
            topic = chat_result.get("topic", "")
            summary = chat_result.get("summary", "")
            agent_manager.add_private_chat_record(
                agent_a.player_name, agent_b.player_name, topic, summary
            )
            agent_manager.add_private_chat_record(
                agent_b.player_name, agent_a.player_name, topic, summary
            )

            # 发送每条对话消息到前端
            for speaker_name, msg in chat_result.get("chat_log", []):
                # 确定发送者和接收者
                if speaker_name == agent_a.player_name:
                    from_id, from_name = player_a_id, agent_a.player_name
                    to_id, to_name = player_b_id, agent_b.player_name
                else:
                    from_id, from_name = player_b_id, agent_b.player_name
                    to_id, to_name = player_a_id, agent_a.player_name

                await self.emitter.emit(
                    "private_chat_message",
                    {
                        "from_id": from_id,
                        "from_name": from_name,
                        "to_id": to_id,
                        "to_name": to_name,
                        "message": msg,
                    },
                )

            await self.emitter.emit(
                "private_chat_end",
                {
                    "player_a_id": player_a_id,
                    "player_b_id": player_b_id,
                    "player_a_name": agent_a.player_name,
                    "player_b_name": agent_b.player_name,
                    "summary": summary,
                    "analysis": summary,
                },
            )

        # 私聊结束后，刷新所有 Agent profile（社交关系已更新）
        await self._emit_all_agents(engine, agent_manager.agents_data)

        await self.emitter.emit("phase_completed", {"phase": "private_chat"})

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _players_info(self, engine: GameEngine) -> list[dict]:
        return [
            {
                "player_id": p.player_id,
                "player_name": p.player_name,
                "role_id": p.role.role_id,
                "role_name_cn": p.role_name_cn,
                "team": p.team.value,
            }
            for p in engine.state.players
        ]

    def _build_agent_profile(
        self,
        player,
        persistent_data: PersistentAgentData | None,
    ) -> dict:
        """构建单个 Agent 的前端 profile 数据，供 renderAgentProfile 使用。

        参数:
            player: models.player.Player 对象
            persistent_data: 该玩家的持久化数据（可为 None）
        """
        stats = {}
        strategy = ""
        social_relations = []
        lessons = []

        if persistent_data:
            s = persistent_data.statistics
            total_wins = s.wins_as_good + s.wins_as_evil

            # 角色分布字符串
            role_parts = []
            if s.times_as_merlin:
                role_parts.append(f"梅林 ×{s.times_as_merlin}")
            if s.games_as_good - s.times_as_merlin > 0:
                role_parts.append(f"其他好人 ×{s.games_as_good - s.times_as_merlin}")
            if s.times_correct_assassination:
                role_parts.append(f"刺客(命中) ×{s.times_correct_assassination}")
            if s.games_as_evil:
                role_parts.append(f"邪恶 ×{s.games_as_evil}")
            roles_str = ", ".join(role_parts) if role_parts else "—"

            stats = {
                "games": s.games_played,
                "wins": total_wins,
                "roles": roles_str,
            }

            # 策略：优先显示当前阵营的策略
            sm = persistent_data.strategy_memory
            if player.is_good:
                strategy = sm.good_strategy_summary or sm.evil_strategy_summary
            else:
                strategy = sm.evil_strategy_summary or sm.good_strategy_summary

            # 社交关系：转换为前端 [{name, player_id, trust, friendliness}]
            for other_id, rel in persistent_data.social_relations.items():
                # other_id 格式为 "player_X"
                try:
                    other_num = int(other_id.split("_")[1])
                except (IndexError, ValueError):
                    continue
                social_relations.append({
                    "name": f"玩家{other_num}",
                    "player_id": other_num - 1,  # 前端使用 0-based index
                    "trust": rel.trust,
                    "friendliness": rel.friendliness,
                })

            # 最近教训：提取字符串列表
            for item in sm.recent_lessons[-3:]:
                lesson_text = item.get("lesson", "") if isinstance(item, dict) else str(item)
                if lesson_text:
                    lessons.append(lesson_text)

        return {
            "player_id": player.player_id,
            "player_name": player.player_name,
            "role_id": player.role.role_id,
            "role_name_cn": player.role_name_cn,
            "team": player.team.value,
            "stats": stats,
            "strategy": strategy,
            "social_relations": social_relations,
            "lessons": lessons,
        }

    async def _emit_all_agents(
        self,
        engine: GameEngine,
        agents_data: dict[str, PersistentAgentData] | None = None,
    ):
        """发送所有 Agent 的 profile 到前端（all_agents 事件）。"""
        profiles = []
        for player in engine.state.players:
            persistent = None
            if agents_data:
                persistent = agents_data.get(f"player_{player.player_id + 1}")
            profiles.append(self._build_agent_profile(player, persistent))
        await self.emitter.emit("all_agents", {"agents": profiles})

    def _extract_game_result(self, engine: GameEngine) -> dict:
        """与 CommunityRunner._extract_game_result 保持一致"""
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


class _StopGame(Exception):
    """内部异常：用于中断游戏循环"""
    pass
