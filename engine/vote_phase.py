"""投票阶段 - 讨论 + 投票"""

from models.game_state import GameState, MissionRecord
from agents.agent import Agent
from utils.logger import GameLogger


def execute_discussion(
    state: GameState,
    agents: dict[int, Agent],
    logger: GameLogger,
    record: MissionRecord,
):
    """
    执行讨论阶段：所有玩家依次发言

    Args:
        state: 游戏状态
        agents: 所有Agent字典
        logger: 日志器
        record: 当前轮次记录
    """
    logger.phase("讨论阶段 - 玩家依次发言")

    team_names = [f"玩家{t + 1}" for t in state.proposed_team]
    leader_name = state.current_leader.player_name

    # 从队长的下一位开始发言，队长最后发言
    leader_idx = state.current_leader_idx
    speaking_order = []
    for i in range(1, len(state.players)):
        idx = (leader_idx + i) % len(state.players)
        speaking_order.append(idx)
    speaking_order.append(leader_idx)  # 队长最后发言

    all_speeches = []

    for pid in speaking_order:
        player = state.get_player(pid)
        agent = agents[pid]

        # 构建发言上下文
        context_parts = [
            f"当前是第{state.current_round + 1}轮任务。",
            f"队长{leader_name}提议的队伍是: {', '.join(team_names)}",
            "",
            state.get_public_history(),
        ]

        if all_speeches:
            context_parts.append("\n已有玩家的发言:")
            for name, speech in all_speeches:
                context_parts.append(f"  {name}: {speech}")

        context = "\n".join(context_parts)

        # 获取发言
        logger.thinking_start(pid, player.player_name, "speaking")
        speech = agent.speak(context)
        logger.thinking_end(pid, player.player_name)
        all_speeches.append((player.player_name, speech))
        record.speeches[pid] = speech

        # 输出发言
        logger.speech(player.player_name, player.team.value, speech, player_id=pid)

        # 让其他Agent观察到这次发言
        event = f"{player.player_name}发言: {speech}"
        for other_agent in agents.values():
            if other_agent.player_id != pid:
                other_agent.observe(event)


def execute_vote(
    state: GameState,
    agents: dict[int, Agent],
    logger: GameLogger,
    record: MissionRecord,
) -> bool:
    """
    执行投票阶段

    Args:
        state: 游戏状态
        agents: 所有Agent字典
        logger: 日志器
        record: 当前轮次记录

    Returns:
        True=队伍通过, False=队伍被否决
    """
    logger.phase("投票阶段 - 是否同意该队伍出发")

    team_names = [f"玩家{t + 1}" for t in state.proposed_team]
    leader_name = state.current_leader.player_name

    approve_count = 0
    reject_count = 0

    for pid in range(len(state.players)):
        player = state.get_player(pid)
        agent = agents[pid]

        # 构建投票上下文
        context_parts = [
            f"第{state.current_round + 1}轮任务。",
            f"队长{leader_name}提议的队伍: {', '.join(team_names)}",
            "",
            state.get_public_history(),
        ]

        # 添加本轮发言记录
        if record.speeches:
            context_parts.append("\n本轮讨论中的发言:")
            for spid, speech in record.speeches.items():
                context_parts.append(f"  玩家{spid + 1}: {speech}")

        failed_info = state.get_failed_team_history_for_round()
        if failed_info:
            context_parts.append(f"\n重要提醒: {failed_info}")

        # 强制轮提醒
        if state.consecutive_rejects >= 4:
            context_parts.append(
                "\n【紧急！】这是第5次投票（强制轮），如果这次投票仍不通过，邪恶阵营将直接获胜！"
            )

        context = "\n".join(context_parts)

        # 获取投票
        logger.thinking_start(pid, player.player_name, "voting")
        voted = agent.vote_team(context)
        logger.thinking_end(pid, player.player_name)
        record.team_votes[pid] = voted

        if voted:
            approve_count += 1
        else:
            reject_count += 1

        logger.vote(player.player_name, voted, player_id=pid)

    # 判断结果
    approved = approve_count > reject_count
    if approved:
        logger.system(
            f"投票通过！({approve_count}票同意, {reject_count}票反对) 队伍出发执行任务！"
        )
    else:
        logger.system(
            f"投票未通过！({approve_count}票同意, {reject_count}票反对) 换下一个队长组队。"
        )

    # 通知所有Agent
    result_text = "通过" if approved else "未通过"
    event = (
        f"组队投票结果: {result_text} ({approve_count}同意/{reject_count}反对)。"
        f"队伍: {', '.join(team_names)}"
    )
    for agent in agents.values():
        agent.observe(event)

    return approved
