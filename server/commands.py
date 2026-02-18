"""命令处理器 - 路由 WebSocket 客户端发来的 JSON 指令"""

import asyncio

from server.async_game_runner import AsyncGameRunner
from server.event_emitter import EventEmitter
from community.persistent_agent import PersistentAgentManager
from community.statistics import CommunityStatistics
from config import COMMUNITY_DATA_DIR


class CommandHandler:
    """处理来自前端的命令"""

    def __init__(
        self,
        runner: AsyncGameRunner,
        emitter: EventEmitter,
        agent_manager: PersistentAgentManager,
    ):
        self.runner = runner
        self.emitter = emitter
        self.agent_manager = agent_manager

    async def handle(self, cmd: str, params: dict) -> dict:
        """
        路由并执行一条命令。

        Args:
            cmd: 命令名
            params: 附加参数

        Returns:
            响应字典 {"ok": bool, ...}
        """
        handler = getattr(self, f"_cmd_{cmd}", None)
        if handler is None:
            return {"ok": False, "error": f"未知命令: {cmd}"}
        try:
            return await handler(params)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # start_game
    # ------------------------------------------------------------------

    async def _cmd_start_game(self, params: dict) -> dict:
        if self.runner.state not in ("idle", "finished"):
            return {"ok": False, "error": f"游戏正在运行中 (state={self.runner.state})"}

        num_games = int(params.get("num_games", 1))
        mode = params.get("mode", "single")
        step_mode = bool(params.get("step_mode", False))

        self.runner.step_mode = step_mode

        if mode == "community":
            continuous = bool(params.get("continuous", False))
            asyncio.ensure_future(
                self.runner.run_community_session(num_games, continuous=continuous)
            )
        else:
            asyncio.ensure_future(self.runner.run_single_game())

        return {"ok": True, "mode": mode, "num_games": num_games, "step_mode": step_mode}

    # ------------------------------------------------------------------
    # pause / resume / step / stop
    # ------------------------------------------------------------------

    async def _cmd_pause(self, params: dict) -> dict:
        self.runner.pause()
        return {"ok": True, "state": self.runner.state}

    async def _cmd_resume(self, params: dict) -> dict:
        self.runner.resume()
        return {"ok": True, "state": self.runner.state}

    async def _cmd_step(self, params: dict) -> dict:
        self.runner.step()
        return {"ok": True, "state": self.runner.state}

    async def _cmd_stop(self, params: dict) -> dict:
        self.runner.stop()
        return {"ok": True, "state": self.runner.state}

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def _cmd_get_agent_profile(self, params: dict) -> dict:
        agent_id = params.get("agent_id", "")
        data = self.agent_manager.agents_data.get(agent_id)
        if data is None:
            return {"ok": False, "error": f"未找到 agent: {agent_id}"}
        return {
            "ok": True,
            "profile": self.agent_manager._agent_data_to_dict(data),
        }

    async def _cmd_get_all_agents(self, params: dict) -> dict:
        agents = {}
        for agent_id, data in self.agent_manager.agents_data.items():
            agents[agent_id] = {
                "agent_id": data.agent_id,
                "display_name": data.display_name,
                "games_played": data.statistics.games_played,
                "wins_as_good": data.statistics.wins_as_good,
                "wins_as_evil": data.statistics.wins_as_evil,
            }
        return {"ok": True, "agents": agents}

    async def _cmd_get_stats(self, params: dict) -> dict:
        report = self.runner.statistics.generate_report()
        return {"ok": True, "stats": report}

    async def _cmd_set_config(self, params: dict) -> dict:
        """动态修改运行时配置（仅影响后续游戏）"""
        import config

        changed = {}
        for key, value in params.items():
            if key == "cmd":
                continue
            upper_key = key.upper()
            if hasattr(config, upper_key):
                old = getattr(config, upper_key)
                setattr(config, upper_key, type(old)(value))
                changed[upper_key] = value

        return {"ok": True, "changed": changed}
