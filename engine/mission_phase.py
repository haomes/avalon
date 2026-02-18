"""任务执行阶段"""

from models.game_state import GameState, MissionRecord
from agents.agent import Agent
from config import MISSION_FAIL_REQUIRED
from utils.logger import GameLogger


def execute_mission(
    state: GameState,
    agents: dict[int, Agent],
    logger: GameLogger,
    record: MissionRecord,
) -> bool:
    """
    执行任务阶段：队伍成员秘密投票

    Args:
        state: 游戏状态
        agents: 所有Agent字典
        logger: 日志器
        record: 当前轮次记录

    Returns:
        True=任务成功, False=任务失败
    """
    logger.phase(f"任务执行阶段 - 第{state.current_round + 1}轮")

    team_names = [f"玩家{t + 1}" for t in state.proposed_team]
    logger.system(f"执行任务的队伍: {', '.join(team_names)}")

    # 需要多少张失败票才算失败
    fail_required = MISSION_FAIL_REQUIRED[state.current_round]

    success_count = 0
    fail_count = 0

    for pid in state.proposed_team:
        agent = agents[pid]
        player = state.get_player(pid)

        # 构建任务上下文
        context_parts = [
            f"你正在执行第{state.current_round + 1}轮任务。",
            f"队伍成员: {', '.join(team_names)}",
            f"当前比分: 正义 {state.good_wins_count} : {state.evil_wins_count} 邪恶",
        ]

        if state.mission_records:
            context_parts.append("\n历史:")
            context_parts.append(state.get_public_history())

        context = "\n".join(context_parts)

        # 获取行动
        logger.thinking_start(pid, player.player_name, "deciding mission action")
        action_success = agent.mission_action(context)
        logger.thinking_end(pid, player.player_name)
        record.mission_votes[pid] = action_success

        if action_success:
            success_count += 1
        else:
            fail_count += 1

        # 秘密信息写入日志
        action_text = "成功" if action_success else "失败"
        logger.secret(
            f"玩家{pid + 1}({player.role_name_cn}) 投了 [{action_text}] 票"
        )

    # 判定任务结果
    mission_success = fail_count < fail_required
    record.success = mission_success

    # 公布结果（不公布具体谁投了什么）
    logger.system(f"任务卡翻开: {success_count}张成功票, {fail_count}张失败票")
    logger.mission(mission_success)

    # 记录到游戏状态
    state.mission_results.append(mission_success)

    # 显示比分
    logger.score(state.good_wins_count, state.evil_wins_count)

    # 通知所有Agent
    event = (
        f"第{state.current_round + 1}轮任务{'成功' if mission_success else '失败'}！"
        f"({success_count}张成功票, {fail_count}张失败票) "
        f"当前比分: 正义 {state.good_wins_count} : {state.evil_wins_count} 邪恶"
    )
    for agent in agents.values():
        agent.observe(event)

    return mission_success
