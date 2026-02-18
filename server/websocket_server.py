"""WebSocket 服务器 - aiohttp 实现

启动方式:
    python -m server.websocket_server          (从 avalon/ 目录)
    python server/websocket_server.py          (从 avalon/ 目录)
"""

import json
import os
import sys

# 确保 avalon 包可被导入（无论从哪个工作目录启动）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_AVALON_ROOT = os.path.dirname(_THIS_DIR)
if _AVALON_ROOT not in sys.path:
    sys.path.insert(0, _AVALON_ROOT)

from aiohttp import web

from server.event_emitter import EventEmitter
from server.async_game_runner import AsyncGameRunner
from server.commands import CommandHandler
from community.persistent_agent import PersistentAgentManager
from config import COMMUNITY_DATA_DIR


# ------------------------------------------------------------------
# WebSocket 处理
# ------------------------------------------------------------------

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """处理一个 WebSocket 连接的完整生命周期"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    emitter: EventEmitter = request.app["emitter"]
    cmd_handler: CommandHandler = request.app["cmd_handler"]

    emitter.add_client(ws)
    print(f"[WS] 客户端已连接 (当前 {len(emitter.clients)} 个)")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                    cmd = payload.get("cmd", "")
                    params = payload.get("params", {})
                    if not cmd:
                        cmd = payload.pop("cmd", "")
                        params = payload

                    response = await cmd_handler.handle(cmd, params)
                    await ws.send_json({"type": "response", "cmd": cmd, "data": response})
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "data": {"error": "JSON 解析失败"}})
            elif msg.type == web.WSMsgType.ERROR:
                print(f"[WS] 连接异常: {ws.exception()}")
    finally:
        emitter.remove_client(ws)
        print(f"[WS] 客户端已断开 (剩余 {len(emitter.clients)} 个)")

    return ws


# ------------------------------------------------------------------
# HTTP 路由
# ------------------------------------------------------------------

async def index_handler(request: web.Request) -> web.Response:
    """GET / → 重定向到 dashboard.html"""
    raise web.HTTPFound("/dashboard.html")


# ------------------------------------------------------------------
# 应用工厂
# ------------------------------------------------------------------

def create_app() -> web.Application:
    """创建并配置 aiohttp 应用"""
    app = web.Application()

    # 共享组件
    emitter = EventEmitter()
    runner = AsyncGameRunner(emitter)
    agent_manager = PersistentAgentManager(COMMUNITY_DATA_DIR)
    agent_manager.load_all_agents()
    cmd_handler = CommandHandler(runner, emitter, agent_manager)

    app["emitter"] = emitter
    app["runner"] = runner
    app["agent_manager"] = agent_manager
    app["cmd_handler"] = cmd_handler

    # 路由
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)

    # 静态文件: viewer/ 目录
    viewer_dir = os.path.join(_AVALON_ROOT, "viewer")
    if os.path.isdir(viewer_dir):
        app.router.add_static("/", viewer_dir, show_index=False)

    return app


def start_server(host: str = None, port: int = None):
    """启动服务器"""
    host = host or os.getenv("AVALON_HOST", "0.0.0.0")
    port = port or int(os.getenv("AVALON_PORT", "8080"))
    app = create_app()
    print(f"[Server] 启动 Avalon WebSocket 服务器: http://{host}:{port}")
    print(f"[Server] WebSocket 端点: ws://{host}:{port}/ws")
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    start_server()
