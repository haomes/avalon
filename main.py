"""
阿瓦隆 - 多Agent沙盘模拟

运行模式:
  python main.py                # 单局游戏（原行为）
  python main.py --games 10     # 运行 10 局
  python main.py --continuous   # 持续模式（Ctrl+C 停止）
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.game_engine import GameEngine
from utils.logger import GameLogger


def parse_args():
    parser = argparse.ArgumentParser(description="阿瓦隆多Agent模拟")
    parser.add_argument(
        "--games", "-n",
        type=int,
        default=None,
        help="运行指定局数后停止",
    )
    parser.add_argument(
        "--continuous", "-c",
        action="store_true",
        help="持续运行模式（Ctrl+C 优雅停止）",
    )
    parser.add_argument(
        "--no-reflection",
        action="store_true",
        help="禁用反思阶段",
    )
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="禁用私聊阶段",
    )
    return parser.parse_args()


def run_single_game():
    """运行单局游戏（原有行为）"""
    print("""
    ╔══════════════════════════════════════════╗
    ║     阿瓦隆 - 多Agent沙盘模拟            ║
    ║     The Resistance: Avalon               ║
    ║                                          ║
    ║     6人标准局                             ║
    ║     正义: 梅林 派西维尔 忠臣x2           ║
    ║     邪恶: 莫甘娜 刺客                    ║
    ╚══════════════════════════════════════════╝
    """)

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    logger = GameLogger(log_dir=log_dir)
    engine = GameEngine(logger=logger)

    try:
        engine.run()
    except KeyboardInterrupt:
        logger.system("\n游戏被用户中断")
        print("\n游戏已中断。")
    except Exception as e:
        logger.system(f"\n游戏运行出错: {e}")
        raise
    finally:
        logger.close()

    print(f"\n游戏日志已保存至: {logger.log_file}")


def run_community_mode(args):
    """运行社区模式"""
    from community.community_runner import CommunityRunner
    import config

    print("""
    ╔══════════════════════════════════════════╗
    ║     阿瓦隆 - 持久化游戏社区              ║
    ║     The Resistance: Avalon Community     ║
    ╚══════════════════════════════════════════╝
    """)

    # 根据参数调整配置
    if args.no_reflection:
        config.REFLECTION_ENABLED = False
    if args.no_chat:
        config.PRIVATE_CHAT_ENABLED = False

    data_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        config.COMMUNITY_DATA_DIR,
    )
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

    runner = CommunityRunner(data_dir=data_dir, log_dir=log_dir)

    try:
        if args.games:
            print(f"将运行 {args.games} 局游戏...\n")
            runner.run_n_games(args.games)
        else:
            runner.run_continuous()

        # 打印最终报告
        runner.statistics.print_report()

    except Exception as e:
        print(f"\n运行出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    args = parse_args()

    if args.games or args.continuous:
        run_community_mode(args)
    else:
        run_single_game()


if __name__ == "__main__":
    main()
