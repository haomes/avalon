"""游戏日志系统 - 终端彩色输出 + 文件记录"""

import os
import sys
from datetime import datetime
from typing import Callable, Optional

# ANSI 颜色码
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "blue": "\033[94m",      # 好人阵营
    "red": "\033[91m",       # 坏人阵营
    "green": "\033[92m",     # 成功/通过
    "yellow": "\033[93m",    # 警告/投票
    "cyan": "\033[96m",      # 系统信息
    "magenta": "\033[95m",   # 阶段标题
    "gray": "\033[90m",      # 次要信息
    "white": "\033[97m",     # 普通文本
}


class GameLogger:
    """游戏日志管理器"""

    def __init__(self, log_dir: str = "logs", event_callback: Optional[Callable] = None):
        self.log_dir = log_dir
        self.event_callback = event_callback
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, f"game_{timestamp}.log")
        self._file = open(self.log_file, "w", encoding="utf-8")

        self.banner("阿瓦隆 - 多Agent沙盘模拟")
        self.system(f"日志文件: {self.log_file}")

    def _write_file(self, text: str):
        """写入文件（不含颜色码）"""
        self._file.write(text + "\n")
        self._file.flush()

    def _print(self, colored_text: str, plain_text: str):
        """同时输出到终端和文件"""
        print(colored_text)
        sys.stdout.flush()
        self._write_file(plain_text)

    def _emit_event(self, event_type: str, data: dict):
        """触发事件回调（如果已设置）"""
        if self.event_callback:
            self.event_callback(event_type, data)

    # ==================== 思考状态方法 ====================

    def thinking_start(self, player_id: int, player_name: str, action: str):
        """标记玩家开始思考（LLM调用开始）"""
        colored = f"{_COLORS['gray']}[思考中] {player_name}正在{action}...{_COLORS['reset']}"
        plain = f"[思考中] {player_name}正在{action}..."
        self._print(colored, plain)
        self._emit_event("agent_thinking", {
            "player_id": player_id,
            "player_name": player_name,
            "action": action,
        })

    def thinking_end(self, player_id: int, player_name: str):
        """标记玩家思考结束（LLM调用结束）"""
        self._emit_event("agent_thinking_end", {
            "player_id": player_id,
            "player_name": player_name,
        })

    # ==================== 输出方法 ====================

    def banner(self, text: str):
        """大标题横幅"""
        line = "=" * 60
        colored = (
            f"\n{_COLORS['magenta']}{_COLORS['bold']}{line}\n"
            f"  {text}\n"
            f"{line}{_COLORS['reset']}\n"
        )
        plain = f"\n{line}\n  {text}\n{line}\n"
        self._print(colored, plain)
        self._emit_event("banner", {"text": text})

    def phase(self, text: str):
        """阶段标题"""
        line = "-" * 50
        colored = (
            f"\n{_COLORS['magenta']}{_COLORS['bold']}"
            f">>> {text}\n{line}{_COLORS['reset']}"
        )
        plain = f"\n>>> {text}\n{line}"
        self._print(colored, plain)
        self._emit_event("phase", {"text": text})

    def system(self, text: str):
        """系统消息"""
        colored = f"{_COLORS['cyan']}[系统] {text}{_COLORS['reset']}"
        plain = f"[系统] {text}"
        self._print(colored, plain)

    def good(self, player_name: str, text: str):
        """好人阵营发言"""
        colored = (
            f"{_COLORS['blue']}[{player_name}] {text}{_COLORS['reset']}"
        )
        plain = f"[{player_name}] {text}"
        self._print(colored, plain)

    def evil(self, player_name: str, text: str):
        """坏人阵营发言"""
        colored = (
            f"{_COLORS['red']}[{player_name}] {text}{_COLORS['reset']}"
        )
        plain = f"[{player_name}] {text}"
        self._print(colored, plain)

    def speech(self, player_name: str, team: str, text: str, player_id: int = None):
        """玩家发言（根据阵营自动着色）"""
        if team == "good":
            self.good(player_name, text)
        else:
            self.evil(player_name, text)
        self._emit_event("agent_speech", {
            "player_id": player_id,
            "player_name": player_name,
            "team": team,
            "text": text,
        })

    def vote(self, player_name: str, approved: bool, player_id: int = None):
        """投票结果"""
        result = "同意" if approved else "反对"
        color = _COLORS["green"] if approved else _COLORS["red"]
        colored = f"{_COLORS['yellow']}[投票] {_COLORS['reset']}{player_name}: {color}{result}{_COLORS['reset']}"
        plain = f"[投票] {player_name}: {result}"
        self._print(colored, plain)
        self._emit_event("agent_vote", {
            "player_id": player_id,
            "player_name": player_name,
            "approved": approved,
        })

    def mission(self, success: bool):
        """任务结果"""
        if success:
            colored = f"\n{_COLORS['green']}{_COLORS['bold']}★ 任务成功！★{_COLORS['reset']}\n"
            plain = "\n★ 任务成功！★\n"
        else:
            colored = f"\n{_COLORS['red']}{_COLORS['bold']}✗ 任务失败！✗{_COLORS['reset']}\n"
            plain = "\n✗ 任务失败！✗\n"
        self._print(colored, plain)
        self._emit_event("mission_result", {"success": success})

    def score(self, good_wins: int, evil_wins: int):
        """当前比分"""
        colored = (
            f"{_COLORS['bold']}[比分] "
            f"{_COLORS['blue']}正义 {good_wins} "
            f"{_COLORS['white']}: "
            f"{_COLORS['red']}{evil_wins} 邪恶"
            f"{_COLORS['reset']}"
        )
        plain = f"[比分] 正义 {good_wins} : {evil_wins} 邪恶"
        self._print(colored, plain)
        self._emit_event("score", {"good_wins": good_wins, "evil_wins": evil_wins})

    def result(self, text: str, good_wins: bool):
        """最终结果"""
        line = "=" * 60
        color = _COLORS["blue"] if good_wins else _COLORS["red"]
        colored = (
            f"\n{color}{_COLORS['bold']}{line}\n"
            f"  {text}\n"
            f"{line}{_COLORS['reset']}\n"
        )
        plain = f"\n{line}\n  {text}\n{line}\n"
        self._print(colored, plain)
        self._emit_event("game_result", {"text": text, "good_wins": good_wins})

    def info(self, text: str):
        """普通信息"""
        colored = f"{_COLORS['gray']}{text}{_COLORS['reset']}"
        plain = text
        self._print(colored, plain)

    def secret(self, text: str):
        """秘密信息（仅写入日志文件，不在终端显示全部细节）"""
        self._write_file(f"[秘密] {text}")

    def close(self):
        """关闭日志文件"""
        if not self._file.closed:
            self._file.close()
