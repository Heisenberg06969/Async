"""
Windows 11 Global System Media Transport Controls (SMTC) integration for Async.
Extracts live now-playing metadata (Title, Artist, Album, Cover Art Thumbnail, Timeline)
and allows bi-directional media playback control (Play/Pause, Next, Previous).
"""

import asyncio
import base64
import threading
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Async.MediaSession")

try:
    import winsdk.windows.media.control as wmc
    import winsdk.windows.storage.streams as streams
    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False


class WindowsMediaSession:
    def __init__(self):
        self.enabled = HAS_WINSDK
        self.lock = threading.Lock()
        self.current_media: Dict[str, Any] = {
            "has_media": False,
            "title": "No Media Playing",
            "artist": "Async Room Light",
            "album": "",
            "thumbnail": None, # base64 data URI
            "position": 0.0,
            "duration": 0.0,
            "is_playing": False,
            "app_id": ""
        }
        self._last_title = ""
        self._last_artist = ""
        self._cached_thumb_b64: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_manager = None

    def start(self):
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="AsyncMediaSession")
        self._thread.start()

    def stop(self):
        self._running = False

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._worker())

    async def _worker(self):
        try:
            self._session_manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        except Exception as e:
            logger.debug(f"Failed to get session manager: {e}")
            return

        while self._running:
            try:
                await self._update_media_state()
            except Exception:
                pass
            await asyncio.sleep(0.4) # Poll every 400ms for timeline updates

    async def _update_media_state(self):
        if not self._session_manager:
            return

        session = self._session_manager.get_current_session()
        if not session:
            sessions = self._session_manager.get_sessions()
            if sessions and len(sessions) > 0:
                session = sessions[0]

        if not session:
            with self.lock:
                self.current_media["has_media"] = False
                self.current_media["title"] = "No Media Playing"
                self.current_media["artist"] = "Waiting for audio..."
                self.current_media["is_playing"] = False
                self.current_media["thumbnail"] = None
            return

        # 1. Timeline & Playback Info
        pos = 0.0
        duration = 0.0
        is_playing = False
        try:
            tl = session.get_timeline_properties()
            if tl:
                if tl.position:
                    pos = tl.position.total_seconds()
                if tl.end_time:
                    duration = tl.end_time.total_seconds()
        except Exception:
            pass

        try:
            info = session.get_playback_info()
            if info:
                # 4 = Playing, 5 = Paused
                is_playing = (info.playback_status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
        except Exception:
            pass

        # 2. Track & Cover Art Metadata
        try:
            props = await session.try_get_media_properties_async()
            title = props.title or "Unknown Title"
            artist = props.artist or ""
            album = props.album_title or ""

            # Check if track changed before re-reading stream bytes
            if title != self._last_title or artist != self._last_artist:
                self._last_title = title
                self._last_artist = artist

                if props.thumbnail:
                    try:
                        stream = await props.thumbnail.open_read_async()
                        size = stream.size
                        if size > 0:
                            reader = streams.DataReader(stream.get_input_stream_at(0))
                            await reader.load_async(size)
                            buf = bytearray(size)
                            reader.read_bytes(buf)
                            self._cached_thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
                    except Exception:
                        self._cached_thumb_b64 = None
                else:
                    self._cached_thumb_b64 = None

            with self.lock:
                self.current_media = {
                    "has_media": True,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "thumbnail": self._cached_thumb_b64,
                    "position": round(pos, 1),
                    "duration": round(duration, 1),
                    "is_playing": is_playing,
                    "app_id": session.source_app_user_model_id or ""
                }
        except Exception:
            pass

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.current_media)

    # Control Commands
    def toggle_play_pause(self):
        if self._loop and self._session_manager:
            asyncio.run_coroutine_threadsafe(self._do_toggle_play_pause(), self._loop)

    async def _do_toggle_play_pause(self):
        try:
            session = self._session_manager.get_current_session()
            if not session:
                sessions = self._session_manager.get_sessions()
                session = sessions[0] if sessions else None
            if session:
                await session.try_toggle_play_pause_async()
        except Exception:
            pass

    def next_track(self):
        if self._loop and self._session_manager:
            asyncio.run_coroutine_threadsafe(self._do_next_track(), self._loop)

    async def _do_next_track(self):
        try:
            session = self._session_manager.get_current_session()
            if not session:
                sessions = self._session_manager.get_sessions()
                session = sessions[0] if sessions else None
            if session:
                await session.try_skip_next_async()
        except Exception:
            pass

    def previous_track(self):
        if self._loop and self._session_manager:
            asyncio.run_coroutine_threadsafe(self._do_previous_track(), self._loop)

    async def _do_previous_track(self):
        try:
            session = self._session_manager.get_current_session()
            if not session:
                sessions = self._session_manager.get_sessions()
                session = sessions[0] if sessions else None
            if session:
                await session.try_skip_previous_async()
        except Exception:
            pass
