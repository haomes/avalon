"""统计和报告系统"""

from dataclasses import dataclass, field


@dataclass
class CommunityStatistics:
    """社区统计数据"""

    total_games: int = 0
    good_wins: int = 0
    evil_wins: int = 0
    assassinations_attempted: int = 0
    assassinations_successful: int = 0

    # 每个玩家的统计
    player_stats: dict[str, dict] = field(default_factory=dict)

    # 最近游戏记录
    recent_games: list[dict] = field(default_factory=list)

    def update(self, game_result: dict):
        """更新统计数据"""
        self.total_games += 1

        if game_result["winner"] == "good":
            self.good_wins += 1
        else:
            self.evil_wins += 1

        # 刺杀统计
        assassin_data = game_result.get("assassin_phase")
        if assassin_data:
            self.assassinations_attempted += 1
            if assassin_data.get("merlin_killed"):
                self.assassinations_successful += 1

        # 更新玩家统计
        for player in game_result["players"]:
            pid = f"player_{player['player_id'] + 1}"
            if pid not in self.player_stats:
                self.player_stats[pid] = {
                    "games": 0,
                    "wins": 0,
                    "as_good": 0,
                    "as_evil": 0,
                    "wins_as_good": 0,
                    "wins_as_evil": 0,
                }

            stats = self.player_stats[pid]
            stats["games"] += 1

            is_good = player["team"] == "good"
            won = (game_result["winner"] == "good") == is_good

            if is_good:
                stats["as_good"] += 1
                if won:
                    stats["wins_as_good"] += 1
            else:
                stats["as_evil"] += 1
                if won:
                    stats["wins_as_evil"] += 1

            if won:
                stats["wins"] += 1

        # 记录最近游戏
        self.recent_games.append({
            "game_id": game_result["game_id"],
            "winner": game_result["winner"],
            "end_reason": game_result["end_reason"],
        })
        self.recent_games = self.recent_games[-20:]

    def generate_report(self) -> dict:
        """生成统计报告"""
        return {
            "summary": {
                "total_games": self.total_games,
                "good_win_rate": (
                    f"{self.good_wins / self.total_games * 100:.1f}%"
                    if self.total_games > 0
                    else "N/A"
                ),
                "evil_win_rate": (
                    f"{self.evil_wins / self.total_games * 100:.1f}%"
                    if self.total_games > 0
                    else "N/A"
                ),
                "assassination_rate": (
                    f"{self.assassinations_successful / self.assassinations_attempted * 100:.1f}%"
                    if self.assassinations_attempted > 0
                    else "N/A"
                ),
            },
            "player_rankings": self._get_player_rankings(),
            "recent_games": self.recent_games[-10:],
        }

    def _get_player_rankings(self) -> list[dict]:
        """获取玩家胜率排名"""
        rankings = []
        for pid, stats in self.player_stats.items():
            if stats["games"] > 0:
                rankings.append({
                    "player": pid,
                    "games": stats["games"],
                    "win_rate": f"{stats['wins'] / stats['games'] * 100:.1f}%",
                    "good_win_rate": (
                        f"{stats['wins_as_good'] / stats['as_good'] * 100:.1f}%"
                        if stats["as_good"] > 0
                        else "N/A"
                    ),
                    "evil_win_rate": (
                        f"{stats['wins_as_evil'] / stats['as_evil'] * 100:.1f}%"
                        if stats["as_evil"] > 0
                        else "N/A"
                    ),
                })

        rankings.sort(
            key=lambda x: float(x["win_rate"].rstrip("%")) if x["win_rate"] != "N/A" else 0,
            reverse=True,
        )
        return rankings

    def print_report(self):
        """打印可读报告"""
        report = self.generate_report()

        print("\n" + "=" * 60)
        print("  阿瓦隆社区统计报告")
        print("=" * 60)

        s = report["summary"]
        print(f"\n总场次: {s['total_games']}")
        print(f"正义阵营胜率: {s['good_win_rate']}")
        print(f"邪恶阵营胜率: {s['evil_win_rate']}")
        print(f"刺杀成功率: {s['assassination_rate']}")

        print("\n玩家排名 (按胜率):")
        for i, player in enumerate(report["player_rankings"], 1):
            print(
                f"  {i}. {player['player']} - "
                f"胜率 {player['win_rate']} ({player['games']}场) "
                f"[好人 {player['good_win_rate']} / 坏人 {player['evil_win_rate']}]"
            )

        if report["recent_games"]:
            print(f"\n最近 {len(report['recent_games'])} 场:")
            for g in report["recent_games"][-5:]:
                winner_cn = "正义" if g["winner"] == "good" else "邪恶"
                print(f"  [{g['game_id']}] {winner_cn}胜 - {g['end_reason']}")

        print("\n" + "=" * 60)
