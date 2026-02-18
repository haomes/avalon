"""玩家状态管理"""

from dataclasses import dataclass, field
from models.role import RoleInfo, Team


@dataclass
class Player:
    """玩家"""
    player_id: int            # 玩家编号 (0-5)
    player_name: str          # 公开名称 (玩家1-6)
    role: RoleInfo            # 角色信息
    is_leader: bool = False   # 是否为当前队长

    # 夜晚获得的私有信息
    known_evil: list[int] = field(default_factory=list)    # 已知的坏人ID（梅林可见）
    known_merlin_or_morgana: list[int] = field(default_factory=list)  # 已知梅林/莫甘娜ID（派西维尔可见）
    known_allies: list[int] = field(default_factory=list)  # 已知的同伴ID（坏人互认）

    @property
    def team(self) -> Team:
        return self.role.team

    @property
    def is_good(self) -> bool:
        return self.team == Team.GOOD

    @property
    def is_evil(self) -> bool:
        return self.team == Team.EVIL

    @property
    def role_name_cn(self) -> str:
        return self.role.name_cn

    def get_night_info(self) -> str:
        """获取夜晚信息的文字描述"""
        info_parts = []

        if self.role.can_see_evil and self.known_evil:
            evil_names = [f"玩家{eid + 1}" for eid in self.known_evil]
            info_parts.append(f"你看到以下玩家是邪恶阵营: {', '.join(evil_names)}")

        if self.role.can_see_merlin and self.known_merlin_or_morgana:
            mm_names = [f"玩家{mid + 1}" for mid in self.known_merlin_or_morgana]
            info_parts.append(
                f"你看到以下玩家中有梅林和莫甘娜（但你不知道谁是谁）: {', '.join(mm_names)}"
            )

        if self.is_evil and self.known_allies:
            ally_names = [f"玩家{aid + 1}" for aid in self.known_allies]
            info_parts.append(f"你的邪恶同伴是: {', '.join(ally_names)}")

        if not info_parts:
            info_parts.append("你在夜晚没有获得任何特殊信息。")

        return "\n".join(info_parts)
