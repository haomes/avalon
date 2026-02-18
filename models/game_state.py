"""游戏状态管理"""

from dataclasses import dataclass, field
from models.player import Player


@dataclass
class MissionRecord:
    """单轮任务记录"""
    round_num: int                     # 第几轮 (1-5)
    team_leader_id: int                # 队长ID
    team_members: list[int]            # 队伍成员ID
    team_votes: dict[int, bool] = field(default_factory=dict)  # 组队投票 {player_id: approved}
    mission_votes: dict[int, bool] = field(default_factory=dict)  # 任务投票 {player_id: success}
    success: bool | None = None        # 任务是否成功
    speeches: dict[int, str] = field(default_factory=dict)  # 发言记录 {player_id: speech}

    def to_dict(self) -> dict:
        """转换为JSON可序列化的字典"""
        approve_count = sum(1 for v in self.team_votes.values() if v)
        reject_count = sum(1 for v in self.team_votes.values() if not v)
        return {
            "round_num": self.round_num,
            "team_leader_id": self.team_leader_id,
            "team_members": self.team_members,
            "team_votes": {str(k): v for k, v in self.team_votes.items()},
            "team_approved": approve_count > reject_count,
            "mission_votes": {str(k): v for k, v in self.mission_votes.items()},
            "success": self.success,
            "speeches": {str(k): v for k, v in self.speeches.items()},
        }


@dataclass
class GameState:
    """游戏全局状态"""
    players: list[Player] = field(default_factory=list)

    # 游戏进度
    current_round: int = 0             # 当前轮次 (0-4，对应任务1-5)
    current_leader_idx: int = 0        # 当前队长的玩家索引
    consecutive_rejects: int = 0       # 连续组队被否决次数

    # 任务结果
    mission_results: list[bool] = field(default_factory=list)  # True=成功, False=失败
    mission_records: list[MissionRecord] = field(default_factory=list)  # 详细记录

    # 当前轮次临时状态
    proposed_team: list[int] = field(default_factory=list)  # 当前提议的队伍

    # 游戏结束标志
    game_over: bool = False
    winner: str | None = None          # "good" or "evil"
    end_reason: str = ""

    @property
    def good_wins_count(self) -> int:
        return sum(1 for r in self.mission_results if r)

    @property
    def evil_wins_count(self) -> int:
        return sum(1 for r in self.mission_results if not r)

    @property
    def current_leader(self) -> Player:
        return self.players[self.current_leader_idx]

    def get_player(self, player_id: int) -> Player:
        return self.players[player_id]

    def next_leader(self):
        """轮转到下一个队长"""
        self.current_leader_idx = (self.current_leader_idx + 1) % len(self.players)
        # 更新 is_leader 标记
        for p in self.players:
            p.is_leader = (p.player_id == self.current_leader_idx)

    def to_dict(self) -> dict:
        """转换为JSON可序列化的字典"""
        return {
            "players": [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "role_id": p.role.role_id,
                    "role_name_cn": p.role.name_cn,
                    "team": p.role.team.value,
                    "known_evil": p.known_evil,
                    "known_merlin_or_morgana": p.known_merlin_or_morgana,
                    "known_allies": p.known_allies,
                }
                for p in self.players
            ],
            "mission_records": [r.to_dict() for r in self.mission_records],
            "mission_results": self.mission_results,
            "good_wins_count": self.good_wins_count,
            "evil_wins_count": self.evil_wins_count,
            "winner": self.winner,
            "end_reason": self.end_reason,
        }

    def get_public_history(self) -> str:
        """获取所有玩家可见的公开历史信息"""
        if not self.mission_records:
            return "这是游戏的第一轮，还没有历史记录。"

        lines = []
        for record in self.mission_records:
            leader_name = f"玩家{record.team_leader_id + 1}"
            team_names = [f"玩家{mid + 1}" for mid in record.team_members]
            lines.append(f"\n--- 第{record.round_num}轮任务 ---")
            lines.append(f"队长: {leader_name}")
            lines.append(f"队伍: {', '.join(team_names)}")

            # 组队投票结果（仅显示票数，不显示具体谁投了什么）
            approve_count = sum(1 for v in record.team_votes.values() if v)
            reject_count = sum(1 for v in record.team_votes.values() if not v)
            lines.append(f"组队投票: {approve_count}票同意, {reject_count}票反对")

            # 发言记录
            if record.speeches:
                lines.append("发言记录:")
                for pid, speech in record.speeches.items():
                    lines.append(f"  玩家{pid + 1}: {speech}")

            # 任务结果
            if record.success is not None:
                fail_count = sum(1 for v in record.mission_votes.values() if not v)
                lines.append(f"任务结果: {'成功' if record.success else '失败'}")
                if fail_count > 0:
                    lines.append(f"  (出现了{fail_count}张失败票)")
                else:
                    lines.append("  (全部为成功票)")
            else:
                lines.append("组队投票结果: 被否决，未执行任务")

        # 总比分
        lines.append(f"\n当前比分: 正义 {self.good_wins_count} : {self.evil_wins_count} 邪恶")
        return "\n".join(lines)

    def get_failed_team_history_for_round(self) -> str:
        """获取当前轮次中被否决的组队记录"""
        if self.consecutive_rejects == 0:
            return ""
        return f"本轮已经有{self.consecutive_rejects}次组队被否决。如果连续5次被否决，邪恶阵营将直接获胜。"
