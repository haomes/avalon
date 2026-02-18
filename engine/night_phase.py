"""夜晚阶段 - 身份确认"""

from models.game_state import GameState
from models.role import Team
from utils.logger import GameLogger


def execute_night_phase(state: GameState, logger: GameLogger):
    """
    执行夜晚阶段：
    1. 梅林看到所有坏人
    2. 坏人互相辨认同伴
    3. 派西维尔看到梅林和莫甘娜
    """
    logger.phase("夜晚降临 - 所有人闭上眼睛...")

    # 收集各角色的ID
    merlin_id = None
    percival_id = None
    morgana_id = None
    evil_ids = []

    for player in state.players:
        if player.role.role_id == "merlin":
            merlin_id = player.player_id
        elif player.role.role_id == "percival":
            percival_id = player.player_id
        elif player.role.role_id == "morgana":
            morgana_id = player.player_id

        if player.is_evil:
            evil_ids.append(player.player_id)

    # 1. 梅林睁眼 - 看到所有坏人
    if merlin_id is not None:
        merlin = state.get_player(merlin_id)
        merlin.known_evil = list(evil_ids)
        evil_names = [f"玩家{eid + 1}" for eid in evil_ids]
        logger.system(f"梅林睁眼，看到了邪恶阵营的成员: {', '.join(evil_names)}")
        logger.secret(
            f"梅林(玩家{merlin_id + 1})看到坏人: {evil_names}"
        )

    # 2. 坏人互认
    for eid in evil_ids:
        evil_player = state.get_player(eid)
        evil_player.known_allies = [e for e in evil_ids if e != eid]

    evil_names = [f"玩家{eid + 1}" for eid in evil_ids]
    logger.system(f"邪恶阵营成员睁眼互认: {', '.join(evil_names)}")
    logger.secret(f"邪恶阵营: {evil_names}")

    # 3. 派西维尔睁眼 - 看到梅林和莫甘娜
    if percival_id is not None and merlin_id is not None and morgana_id is not None:
        percival = state.get_player(percival_id)
        percival.known_merlin_or_morgana = [merlin_id, morgana_id]
        mm_names = [f"玩家{mid + 1}" for mid in [merlin_id, morgana_id]]
        logger.system(
            f"派西维尔睁眼，看到了两个人举手（梅林和莫甘娜）: {', '.join(mm_names)}"
        )
        logger.secret(
            f"派西维尔(玩家{percival_id + 1})看到梅林/莫甘娜: {mm_names}"
        )

    logger.system("天亮了，所有人睁开眼睛。游戏开始！")
    logger.info("")

    # 记录真实身份到日志（仅文件）
    logger.secret("=" * 40)
    logger.secret("真实身份分配:")
    for player in state.players:
        logger.secret(
            f"  {player.player_name} = {player.role_name_cn} ({player.team.value})"
        )
    logger.secret("=" * 40)
