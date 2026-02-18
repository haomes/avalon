"""组队阶段 - 队长选人"""

from models.game_state import GameState
from agents.agent import Agent
from config import MISSION_TEAM_SIZES
from utils.logger import GameLogger


def execute_team_phase(
    state: GameState,
    agents: dict[int, Agent],
    logger: GameLogger,
) -> list[int]:
    """
    执行组队阶段：
    1. 队长选择队伍成员
    2. 公告队伍

    Args:
        state: 游戏状态
        agents: 所有Agent字典
        logger: 日志器

    Returns:
        提议的队伍成员ID列表
    """
    leader = state.current_leader
    leader_agent = agents[leader.player_id]
    team_size = MISSION_TEAM_SIZES[state.current_round]

    logger.phase(
        f"第{state.current_round + 1}轮任务 - 组队阶段 "
        f"(需要{team_size}人, 队长: {leader.player_name})"
    )

    # 构建上下文
    context_parts = [
        f"当前是第{state.current_round + 1}轮任务，需要选择{team_size}名队员。",
        f"你（{leader.player_name}）是本轮队长。",
        "",
        "历史信息:",
        state.get_public_history(),
    ]

    failed_info = state.get_failed_team_history_for_round()
    if failed_info:
        context_parts.append(f"\n警告: {failed_info}")

    context = "\n".join(context_parts)

    # 队长选人
    logger.system(f"{leader.player_name}（队长）正在思考队伍人选...")
    logger.thinking_start(leader.player_id, leader.player_name, "proposing team")
    team = leader_agent.propose_team(team_size, context)
    logger.thinking_end(leader.player_id, leader.player_name)

    # 保证队伍合法
    team = [t for t in team if 0 <= t < 6]
    team = list(dict.fromkeys(team))  # 去重保序
    if len(team) != team_size:
        # 补全
        import random
        candidates = [i for i in range(6) if i not in team]
        while len(team) < team_size:
            choice = random.choice(candidates)
            team.append(choice)
            candidates.remove(choice)

    state.proposed_team = team
    team_names = [f"玩家{t + 1}" for t in team]
    logger.system(f"{leader.player_name}提议的队伍: {', '.join(team_names)}")

    # 通知所有Agent
    event = f"队长{leader.player_name}提议了队伍: {', '.join(team_names)}（第{state.current_round + 1}轮任务，需要{team_size}人）"
    for agent in agents.values():
        agent.observe(event)

    return team
