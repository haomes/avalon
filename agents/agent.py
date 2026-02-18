"""Agent - 每个玩家的LLM决策封装"""

import json
import random
import re

from models.player import Player
from models.role import Team
from config import MODEL_CONFIG, PLAYER_COUNT
from agents.memory import MemoryManager
import llm_client


# ==================== 基础规则提示词 ====================
GAME_RULES = """
## 阿瓦隆游戏规则

你正在参加一场6人阿瓦隆桌游。游戏分为正义阵营（4人）和邪恶阵营（2人）。

### 核心规则：
1. 游戏共5轮任务，每轮由队长选人组队
2. 每轮任务所需人数: 第1轮2人, 第2轮3人, 第3轮4人, 第4轮3人, 第5轮4人
3. 所有玩家投票决定是否同意队伍，超过半数同意则出发执行任务
4. 连续5次组队被否决，邪恶阵营直接获胜
5. 任务中：好人只能投成功票，坏人可以投成功或失败票
6. 出现1张失败票则任务失败
7. 3次任务成功则正义阵营获胜（但刺客还有机会刺杀梅林）
8. 3次任务失败则邪恶阵营获胜

### 角色说明：
- 梅林（正义）：知道所有坏人身份，但要隐藏自己
- 派西维尔（正义）：知道梅林和莫甘娜是谁，但不知道哪个是哪个
- 忠臣（正义）：无特殊能力，靠推理
- 莫甘娜（邪恶）：在派西维尔眼中与梅林外观相同
- 刺客（邪恶）：游戏结束时如果正义方赢了任务，有机会刺杀梅林翻盘
"""


def _build_system_prompt(player: Player) -> str:
    """构建角色专属的系统提示词"""
    prompt_parts = [
        f"你是{player.player_name}，你的真实身份是【{player.role_name_cn}】，"
        f"属于{'正义' if player.is_good else '邪恶'}阵营。",
        "",
        player.role.description,
        "",
        "### 你在夜晚获得的信息：",
        player.get_night_info(),
        "",
        GAME_RULES,
    ]

    # 阵营策略指导
    if player.is_good:
        prompt_parts.extend([
            "### 你的策略指导：",
            "- 你是好人，在任务中只能投【成功】票",
            "- 通过发言和投票行为分析谁可能是坏人",
            "- 如果你是梅林，要隐晦地引导好人，不能暴露你知道谁是坏人",
            "- 如果你是派西维尔，尝试辨别真假梅林并保护他",
            "- 保护梅林的身份不被暴露是非常重要的",
        ])
    else:
        prompt_parts.extend([
            "### 你的策略指导：",
            "- 你是坏人，要伪装成好人",
            "- 在任务中可以选择投【失败】票来破坏任务，但也可以战略性地投成功票",
            "- 在发言中要像好人一样分析和推理，不要暴露自己",
            "- 注意观察谁可能是梅林（表现得对坏人身份很确定的人）",
            "- 如果你是刺客，游戏结束时需要找出梅林",
            "- 如果你是莫甘娜，可以假装自己是梅林来误导派西维尔",
        ])

    prompt_parts.extend([
        "",
        "### 回复要求：",
        "- 用中文回复",
        "- 说话要有角色代入感，像真人玩家一样",
        "- 发言要简洁有力，不要太长（控制在100字以内）",
        "- 不要暴露自己的真实角色身份",
        "- 不要在对话中使用 * 或其他标记语法",
    ])

    return "\n".join(prompt_parts)


class Agent:
    """玩家Agent - 通过LLM进行游戏决策"""

    def __init__(self, player: Player):
        self.player = player
        self.model = MODEL_CONFIG[player.team.value]
        self.system_prompt = _build_system_prompt(player)
        self.memory = MemoryManager(
            player_name=player.player_name,
            model=self.model,
        )

    @property
    def player_id(self) -> int:
        return self.player.player_id

    @property
    def player_name(self) -> str:
        return self.player.player_name

    @property
    def team(self) -> Team:
        return self.player.team

    def _call_llm(self, prompt: str) -> str:
        """调用LLM并记录到记忆"""
        # 获取历史消息（摘要 + 近期原始消息）
        history = self.memory.get_messages_for_llm()
        response = llm_client.chat_with_history(
            model=self.model,
            system_prompt=self.system_prompt,
            history=history,
            user_message=prompt,
        )
        # 将问答对写入记忆
        self.memory.add("user", prompt)
        self.memory.add("assistant", response)
        return response

    def observe(self, event: str):
        """观察到公开事件（加入记忆但不需要回复）"""
        self.memory.add("user", f"[游戏事件] {event}")

    def speak(self, context: str) -> str:
        """
        在讨论阶段发言

        Args:
            context: 当前讨论的上下文信息

        Returns:
            发言内容
        """
        prompt = (
            f"{context}\n\n"
            f"现在轮到你发言。请根据你的身份和已知信息，对当前局势进行分析，"
            f"表达你对队伍组成的看法。注意不要暴露自己的真实身份。"
            f"请直接说出你的发言内容（100字以内）。"
        )
        return self._call_llm(prompt)

    def propose_team(self, team_size: int, context: str) -> list[int]:
        """
        作为队长选择队伍成员

        Args:
            team_size: 需要选择的人数
            context: 当前游戏状态

        Returns:
            选择的队员ID列表
        """
        all_ids = list(range(PLAYER_COUNT))
        prompt = (
            f"{context}\n\n"
            f"你是本轮的队长，需要选择{team_size}名玩家组成队伍（可以包含你自己）。\n"
            f"所有可选的玩家：{', '.join(f'玩家{i+1}' for i in all_ids)}\n"
            f"请仔细思考后选择队员。\n\n"
            f"请严格按照以下JSON格式回复，不要包含其他内容：\n"
            f'{{"team": [选中的玩家编号]}}\n'
            f'例如选择玩家1和玩家3: {{"team": [1, 3]}}'
        )
        response = self._call_llm(prompt)
        return self._parse_team(response, team_size)

    def vote_team(self, context: str) -> bool:
        """
        对队伍组成进行投票

        Args:
            context: 当前队伍信息和游戏状态

        Returns:
            True=同意, False=反对
        """
        prompt = (
            f"{context}\n\n"
            f"你需要对这个队伍进行投票。超过半数同意则队伍出发，否则换下一个队长组队。\n\n"
            f"请严格按照以下JSON格式回复，不要包含其他内容：\n"
            f'{{"vote": "approve"}} 表示同意\n'
            f'{{"vote": "reject"}} 表示反对'
        )
        response = self._call_llm(prompt)
        return self._parse_vote(response)

    def mission_action(self, context: str) -> bool:
        """
        执行任务时选择投成功还是失败

        Args:
            context: 任务相关信息

        Returns:
            True=成功, False=失败
        """
        # 好人只能投成功
        if self.player.is_good:
            self.memory.add("user", f"[任务执行] {context}\n你是好人，你投出了【成功】票。")
            return True

        # 坏人可以选择
        prompt = (
            f"{context}\n\n"
            f"你是邪恶阵营的成员，你可以选择投【成功】票（伪装）或【失败】票（破坏任务）。\n"
            f"请根据当前局势做出策略性选择。\n\n"
            f"请严格按照以下JSON格式回复，不要包含其他内容：\n"
            f'{{"action": "success"}} 投成功票\n'
            f'{{"action": "fail"}} 投失败票'
        )
        response = self._call_llm(prompt)
        return self._parse_mission(response)

    def assassinate(self, context: str) -> int:
        """
        刺客选择刺杀目标

        Args:
            context: 游戏信息

        Returns:
            目标玩家ID (0-5)
        """
        # 排除自己和已知同伴，只列出可能是好人的玩家
        exclude = {self.player_id} | set(self.player.known_allies)
        candidates = [p for p in range(PLAYER_COUNT) if p not in exclude]
        prompt = (
            f"{context}\n\n"
            f"正义阵营完成了三次任务，但你作为刺客有最后一次机会！\n"
            f"你需要从以下玩家中找出梅林并刺杀他：\n"
            f"{', '.join(f'玩家{pid+1}' for pid in candidates)}\n"
            f"回顾整场游戏的发言和行为，仔细分析谁最可能是梅林。\n\n"
            f"请严格按照以下JSON格式回复，不要包含其他内容：\n"
            f'{{"target": 玩家编号}}\n'
            f'例如刺杀玩家3: {{"target": 3}}'
        )
        response = self._call_llm(prompt)
        return self._parse_target(response)

    # ==================== 解析方法 ====================

    def _parse_team(self, response: str, team_size: int) -> list[int]:
        """解析队伍选择"""
        try:
            # 尝试提取JSON
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                team = data.get("team", [])
                # 将玩家编号转换为ID（玩家1=ID0）
                team = [int(t) - 1 for t in team]
                # 验证
                team = [t for t in team if 0 <= t < PLAYER_COUNT]
                team = list(set(team))  # 去重
                if len(team) == team_size:
                    return team
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        # 回退：尝试从文本中提取数字
        numbers = re.findall(r'玩家(\d+)', response)
        if not numbers:
            numbers = re.findall(r'\d+', response)
        team = list(set(int(n) - 1 for n in numbers if 1 <= int(n) <= PLAYER_COUNT))
        if len(team) >= team_size:
            return team[:team_size]

        # 最终回退：队长选自己加随机
        candidates = list(range(PLAYER_COUNT))
        team = [self.player_id]
        candidates.remove(self.player_id)
        while len(team) < team_size:
            choice = random.choice(candidates)
            team.append(choice)
            candidates.remove(choice)
        return team

    def _parse_vote(self, response: str) -> bool:
        """解析投票结果"""
        try:
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                vote = data.get("vote", "").lower()
                return vote == "approve"
        except (json.JSONDecodeError, ValueError):
            pass
        # 回退：从文本判断
        response_lower = response.lower()
        if "同意" in response or "approve" in response_lower:
            return True
        if "反对" in response or "reject" in response_lower:
            return False
        # 默认好人同意，坏人反对
        return self.player.is_good

    def _parse_mission(self, response: str) -> bool:
        """解析任务行动"""
        try:
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                action = data.get("action", "").lower()
                return action == "success"
        except (json.JSONDecodeError, ValueError):
            pass
        # 回退
        if "失败" in response or "fail" in response.lower():
            return False
        return True

    def _parse_target(self, response: str) -> int:
        """解析刺杀目标"""
        try:
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                target = int(data.get("target", 0))
                target_id = target - 1
                if 0 <= target_id < PLAYER_COUNT and target_id != self.player_id:
                    return target_id
        except (json.JSONDecodeError, ValueError):
            pass
        # 回退：提取数字
        numbers = re.findall(r'玩家(\d+)', response)
        if not numbers:
            numbers = re.findall(r'\d+', response)
        for n in numbers:
            target_id = int(n) - 1
            if 0 <= target_id < PLAYER_COUNT and target_id != self.player_id:
                return target_id
        # 最终回退：随机选一个非队友
        exclude = {self.player_id} | set(self.player.known_allies)
        candidates = [i for i in range(PLAYER_COUNT) if i not in exclude]
        return random.choice(candidates)
