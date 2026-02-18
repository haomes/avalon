"""角色定义"""

from enum import Enum
from dataclasses import dataclass


class Team(Enum):
    GOOD = "good"
    EVIL = "evil"


@dataclass
class RoleInfo:
    """角色信息"""
    role_id: str          # 角色标识
    name_cn: str          # 中文名
    team: Team            # 阵营
    description: str      # 能力描述
    can_see_evil: bool = False      # 能否看到坏人（梅林）
    can_see_merlin: bool = False    # 能否看到梅林和莫甘娜（派西维尔）
    is_visible_to_merlin: bool = True  # 是否对梅林可见（莫德雷德不可见，但本局无此角色）
    is_assassin: bool = False       # 是否为刺客


# 角色定义
ROLES = {
    "merlin": RoleInfo(
        role_id="merlin",
        name_cn="梅林",
        team=Team.GOOD,
        description="你是梅林，正义阵营的先知。你能在夜晚阶段看到所有邪恶阵营成员的身份。"
                    "你的核心任务是引导好人完成任务，但必须小心隐藏自己的身份——"
                    "如果游戏结束时被刺客识别出来，正义阵营将功亏一篑。",
        can_see_evil=True,
    ),
    "percival": RoleInfo(
        role_id="percival",
        name_cn="派西维尔",
        team=Team.GOOD,
        description="你是派西维尔，梅林的守护者。你能在夜晚阶段看到梅林和莫甘娜，"
                    "但无法分辨谁是真正的梅林、谁是伪装的莫甘娜。"
                    "你的任务是辨别真假梅林，保护真正的梅林不被刺客发现。",
        can_see_merlin=True,
    ),
    "loyal_servant_1": RoleInfo(
        role_id="loyal_servant_1",
        name_cn="忠臣亚瑟",
        team=Team.GOOD,
        description="你是亚瑟的忠臣，正义阵营的一员。你没有特殊能力，"
                    "需要通过观察发言、投票行为和逻辑推理来辨别谁是坏人。"
                    "同时你要保护梅林的身份不被暴露。",
    ),
    "loyal_servant_2": RoleInfo(
        role_id="loyal_servant_2",
        name_cn="忠臣凯",
        team=Team.GOOD,
        description="你是亚瑟的忠臣，正义阵营的一员。你没有特殊能力，"
                    "需要通过观察发言、投票行为和逻辑推理来辨别谁是坏人。"
                    "同时你要保护梅林的身份不被暴露。",
    ),
    "morgana": RoleInfo(
        role_id="morgana",
        name_cn="莫甘娜",
        team=Team.EVIL,
        description="你是莫甘娜，邪恶阵营的女巫。在派西维尔的视野中，"
                    "你和梅林的外观相同，这是你最大的优势。"
                    "你的任务是假扮梅林误导好人，让任务失败，"
                    "并帮助刺客在最后找到真正的梅林。",
        is_visible_to_merlin=True,
    ),
    "assassin": RoleInfo(
        role_id="assassin",
        name_cn="刺客",
        team=Team.EVIL,
        description="你是刺客，邪恶阵营的杀手。你在夜晚能看到同伴莫甘娜。"
                    "在游戏过程中要伪装成好人，破坏任务。"
                    "如果正义方完成了三次任务，你将获得最后一次机会——"
                    "刺杀梅林。只要你能找出并刺杀真正的梅林，邪恶阵营就能逆转获胜。",
        is_visible_to_merlin=True,
        is_assassin=True,
    ),
}


def get_role(role_id: str) -> RoleInfo:
    """根据角色ID获取角色信息"""
    return ROLES[role_id]


def get_team_roles(team: Team) -> list[RoleInfo]:
    """获取某个阵营的所有角色"""
    return [r for r in ROLES.values() if r.team == team]
