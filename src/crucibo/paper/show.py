"""Loop a recorded trading show on the paper dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path

from crucibo.paper.dashboard import EventHub, _handle_http_client
from crucibo.paper.recording import ShowRecording, load_show


async def run_show_dashboard(
    *,
    recording: ShowRecording,
    host: str = "127.0.0.1",
    port: int = 8765,
    tick_delay: float = 1.0,
    loop_pause: float = 3.0,
    loop_forever: bool = True,
) -> None:
    if tick_delay < 0:
        raise ValueError("tick_delay must be >= 0")
    if loop_pause < 0:
        raise ValueError("loop_pause must be >= 0")
    if not recording.events:
        raise ValueError("recording has no events to play")

    hub = EventHub()
    server = await asyncio.start_server(
        lambda r, w: _handle_http_client(r, w, hub),
        host=host,
        port=port,
    )

    loop_index = 0
    try:
        while True:
            loop_index += 1
            session = dict(recording.session)
            session["type"] = "session"
            session["loop"] = loop_index
            session["dashboard_url"] = f"http://{host}:{port}/"
            session["message"] = (
                f"Show replay loop #{loop_index} for {session.get('show_day', 'session')} "
                f"({len(recording.events)} bars)."
            )
            await hub.publish(session)

            for event in recording.events:
                payload = dict(event)
                payload["loop"] = loop_index
                await hub.publish(payload)
                if tick_delay > 0:
                    await asyncio.sleep(tick_delay)

            await hub.publish(
                {
                    "type": "loop_done",
                    "loop": loop_index,
                    "tick_count": len(recording.events),
                    "message": f"loop #{loop_index} complete — restarting",
                }
            )
            if not loop_forever:
                break
            if loop_pause > 0:
                await asyncio.sleep(loop_pause)
    finally:
        server.close()
        await server.wait_closed()


async def run_show_from_file(
    *,
    recording_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    tick_delay: float = 1.0,
    loop_pause: float = 3.0,
    loop_forever: bool = True,
) -> None:
    recording = load_show(recording_path)
    await run_show_dashboard(
        recording=recording,
        host=host,
        port=port,
        tick_delay=tick_delay,
        loop_pause=loop_pause,
        loop_forever=loop_forever,
    )