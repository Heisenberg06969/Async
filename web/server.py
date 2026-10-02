"""
High-Performance WebSocket & HTTP Room Simulator Server for Async.
Streams real-time audio FFT bars, dynamic single-bulb RGB glow, and beat metrics
to browser clients at 60 FPS with sub-10ms browser rendering latency.
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Set, Callable, Optional, Any, Dict
from aiohttp import web

logger = logging.getLogger("Async.WebServer")

WEB_DIR = Path(__file__).parent

class AsyncWebServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 5050, on_command: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.host = host
        self.port = port
        self.on_command = on_command
        self.clients: Set[web.WebSocketResponse] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/ws", self._handle_ws)

    async def _handle_index(self, request: web.Request) -> web.Response:
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                return web.Response(text=f.read(), content_type="text/html")
        return web.Response(text="Async Room Visualizer index.html not found", status=404)

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.clients.add(ws)
        logger.info(f"Browser client connected (Total: {len(self.clients)})")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if self.on_command:
                            self.on_command(data)
                    except Exception as e:
                        logger.error(f"Error handling browser command: {e}")
                elif msg.type == web.WSMsgType.ERROR:
                    logger.debug(f"WebSocket error: {ws.exception()}")
        finally:
            self.clients.discard(ws)
            logger.info(f"Browser client disconnected (Remaining: {len(self.clients)})")

        return ws

    def broadcast(self, payload: dict):
        """Thread-safe non-blocking broadcast to all connected browsers."""
        if not self.clients or not self.loop or not self.loop.is_running():
            return

        json_str = json.dumps(payload)
        asyncio.run_coroutine_threadsafe(self._async_broadcast(json_str), self.loop)

    async def _async_broadcast(self, msg: str):
        if not self.clients:
            return
        dead_clients = set()
        for ws in self.clients:
            try:
                await ws.send_str(msg)
            except Exception:
                dead_clients.add(ws)
        if dead_clients:
            self.clients.difference_update(dead_clients)

    def _run_server(self):
        asyncio.set_event_loop(self.loop)
        self.runner = web.AppRunner(self.app)
        self.loop.run_until_complete(self.runner.setup())
        for p in range(self.port, self.port + 10):
            try:
                site = web.TCPSite(self.runner, self.host, p)
                self.loop.run_until_complete(site.start())
                self.port = p
                logger.info(f"Async Web Server running at http://{self.host}:{self.port}")
                break
            except OSError:
                continue
        self.loop.run_forever()

    def start(self):
        """Starts web server in a daemon background thread."""
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
