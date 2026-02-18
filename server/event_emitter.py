"""事件广播器 - 向所有 WebSocket 客户端推送游戏事件"""

import json
import time
import asyncio

from aiohttp import web


class EventEmitter:
    """向所有已连接的 WebSocket 客户端广播游戏事件"""

    def __init__(self):
        self.clients: set[web.WebSocketResponse] = set()

    def add_client(self, ws: web.WebSocketResponse):
        """注册新的 WebSocket 客户端"""
        self.clients.add(ws)

    def remove_client(self, ws: web.WebSocketResponse):
        """移除已断开的 WebSocket 客户端"""
        self.clients.discard(ws)

    async def emit(self, event_type: str, data: dict):
        """
        向所有客户端广播一条事件消息。

        消息格式:
            {"type": event_type, "data": data, "timestamp": <unix_ts>}
        """
        message = json.dumps(
            {"type": event_type, "data": data, "timestamp": time.time()},
            ensure_ascii=False,
        )

        dead_clients: list[web.WebSocketResponse] = []

        for ws in self.clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead_clients.append(ws)

        # 清理已失效的连接
        for ws in dead_clients:
            self.clients.discard(ws)
