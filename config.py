"""阿瓦隆游戏配置"""

import os

# ==================== 游戏人数配置 ====================
PLAYER_COUNT = 6

# 每轮任务所需队伍人数 (第1-5轮)
MISSION_TEAM_SIZES = [2, 3, 4, 3, 4]

# 需要多少张失败票才算任务失败 (6人局所有轮次都是1张)
MISSION_FAIL_REQUIRED = [1, 1, 1, 1, 1]

# 最大连续组队失败次数（第5次为强制轮，若仍不通过坏人直接获胜）
MAX_TEAM_VOTES = 5

# ==================== 角色配置 ====================
# 6人标准配置: 梅林、派西维尔、忠臣x2 vs 莫甘娜、刺客
ROLES_CONFIG = {
    "good": ["merlin", "percival", "loyal_servant_1", "loyal_servant_2"],
    "evil": ["morgana", "assassin"],
}

# 角色中文名映射
ROLE_NAMES_CN = {
    "merlin": "梅林",
    "percival": "派西维尔",
    "loyal_servant_1": "忠臣亚瑟",
    "loyal_servant_2": "忠臣凯",
    "morgana": "莫甘娜",
    "assassin": "刺客",
}

# 角色代号（游戏中使用的公开名称，不暴露身份）
PLAYER_NAMES = {
    0: "玩家1",
    1: "玩家2",
    2: "玩家3",
    3: "玩家4",
    4: "玩家5",
    5: "玩家6",
}

# ==================== 模型配置 ====================
MODEL_CONFIG = {
    "good": "dsv32",
    "evil": "dsv32",
}

# LLM参数
LLM_TEMPERATURE = 0.8
LLM_MAX_TOKENS = 1024

# ==================== Memory 配置 ====================
# 记忆总条数上限，超过此值触发压缩
MEMORY_COMPRESS_THRESHOLD = 30

# 压缩时保留最近多少条原始记忆不压缩
MEMORY_KEEP_RECENT = 10

# 摘要调用使用的模型（用较快的模型节省开销）
MEMORY_SUMMARY_MODEL = "dsv32"

# 摘要最大 token 数
MEMORY_SUMMARY_MAX_TOKENS = 512

# ==================== API配置 ====================
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1/")

# ==================== 社区模式配置 ====================

# 数据存储目录
COMMUNITY_DATA_DIR = "data/agents"

# 反思系统配置
REFLECTION_ENABLED = True
REFLECTION_MODEL = "dsv32"
REFLECTION_MAX_LESSONS = 10  # 保留的最大教训数

# 私聊系统配置
PRIVATE_CHAT_ENABLED = True
PRIVATE_CHAT_MAX_PAIRS = 3   # 每局最多私聊对数
PRIVATE_CHAT_MAX_TURNS = 3   # 每次私聊最大轮数
PRIVATE_CHAT_TEMPERATURE = 0.9

# 社交关系配置
TRUST_INITIAL = 0.5
FRIENDLINESS_INITIAL = 0.5
TRUST_CHANGE_RATE = 0.05
FRIENDLINESS_CHANGE_RATE = 0.05

# 统计配置
STATS_REPORT_INTERVAL = 10  # 每多少局打印一次中间报告
