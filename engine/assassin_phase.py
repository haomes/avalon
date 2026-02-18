"""刺杀阶段 - 刺客尝试刺杀梅林"""

from models.game_state import GameState
from agents.agent import Agent
from utils.logger import GameLogger


def execute_assassin_phase(
    state: GameState,
    agents: dict[int, Agent],
    logger: GameLogger,
) -> dict:
    """
    执行刺杀阶段：刺客选择刺杀目标

    Args:
        state: 游戏状态
        agents: 所有Agent字典
        logger: 日志器

    Returns:
        dict: {"merlin_killed": bool, "assassin_id": int, "target_id": int, "morgana_advice": str|None}
    """
    logger.phase("刺杀阶段 - 刺客的最后一搏！")
    logger.system("正义阵营完成了三次任务，但邪恶阵营还有最后的机会...")

    # 找到刺客和梅林
    assassin = None
    merlin_id = None

    for player in state.players:
        if player.role.is_assassin:
            assassin = player
        if player.role.role_id == "merlin":
            merlin_id = player.player_id

    if assassin is None or merlin_id is None:
        logger.system("错误：找不到刺客或梅林！正义阵营获胜。")
        return {"merlin_killed": False, "assassin_id": -1, "target_id": -1, "morgana_advice": None}

    assassin_agent = agents[assassin.player_id]

    # 让邪恶阵营讨论（刺客和同伴）
    logger.system("邪恶阵营正在秘密讨论，分析谁是梅林...")

    morgana_advice_text = None

    # 先让莫甘娜给建议
    morgana = None
    for player in state.players:
        if player.role.role_id == "morgana":
            morgana = player
            break

    if morgana:
        morgana_agent = agents[morgana.player_id]
        morgana_context = (
            f"正义阵营完成了三次任务。现在你需要和刺客一起讨论，分析谁最可能是梅林。\n"
            f"回顾整场游戏中每个人的发言和行为，特别注意：\n"
            f"- 谁对坏人的身份似乎很有把握\n"
            f"- 谁的推理过于精准\n"
            f"- 谁在引导好人做出正确判断\n\n"
            f"游戏历史:\n{state.get_public_history()}\n\n"
            f"请给出你的分析和建议（你认为谁最可能是梅林？）"
        )
        logger.thinking_start(morgana.player_id, morgana.player_name, "analyzing Merlin's identity")
        morgana_advice = morgana_agent.speak(morgana_context)
        logger.thinking_end(morgana.player_id, morgana.player_name)
        morgana_advice_text = morgana_advice
        logger.evil(morgana.player_name, f"(私下对刺客说) {morgana_advice}")

        # 刺客看到莫甘娜的建议
        assassin_agent.observe(f"你的同伴{morgana.player_name}(莫甘娜)的分析: {morgana_advice}")

    # 刺客做出选择
    context = (
        f"游戏历史:\n{state.get_public_history()}\n\n"
        f"你需要从其他5名玩家中找出梅林。\n"
        f"仔细回忆每个人在游戏中的表现。"
    )

    logger.thinking_start(assassin.player_id, assassin.player_name, "choosing assassination target")
    target_id = assassin_agent.assassinate(context)
    logger.thinking_end(assassin.player_id, assassin.player_name)

    # 确保目标不是自己或同伴
    if target_id == assassin.player_id or (morgana and target_id == morgana.player_id):
        # 重新选
        import random
        candidates = [
            p.player_id for p in state.players
            if p.is_good
        ]
        target_id = random.choice(candidates)

    target = state.get_player(target_id)

    logger.system(f"刺客{assassin.player_name}选择刺杀 → {target.player_name}！")

    # 揭晓结果
    if target_id == merlin_id:
        logger.system(f"{target.player_name}就是梅林！刺杀成功！")
        return {
            "merlin_killed": True,
            "assassin_id": assassin.player_id,
            "target_id": target_id,
            "morgana_advice": morgana_advice_text,
        }
    else:
        logger.system(
            f"{target.player_name}的真实身份是{target.role_name_cn}，不是梅林！刺杀失败！"
        )
        logger.system(f"真正的梅林是玩家{merlin_id + 1}！")
        return {
            "merlin_killed": False,
            "assassin_id": assassin.player_id,
            "target_id": target_id,
            "morgana_advice": morgana_advice_text,
        }
