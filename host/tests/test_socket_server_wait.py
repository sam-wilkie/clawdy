"""SocketServer reply path: a message with "wait": true keeps its connection
open so the daemon can answer it; every other message behaves as before."""

import asyncio
import json
import tempfile

import pytest

from clawd_tank_daemon.socket_server import SocketServer
from tests.test_socket_server import _connect, _ingress_path


async def _send_line(path, msg):
    reader, writer = await _connect(path)
    writer.write(json.dumps(msg).encode() + b"\n")
    await writer.drain()
    return reader, writer


@pytest.mark.asyncio
async def test_wait_message_gets_the_reply_on_the_same_connection():
    async def on_message(msg, reply=None):
        assert reply is not None
        assert await reply.send({"decision": "allow"}) is True

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "permission", "wait": True})
        line = await asyncio.wait_for(reader.readline(), timeout=2)
        assert json.loads(line) == {"decision": "allow"}
        writer.close()
        await server.stop()


@pytest.mark.asyncio
async def test_connection_closes_once_the_handler_returns():
    async def on_message(msg, reply=None):
        await reply.send({"decision": "none"})

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "permission", "wait": True})
        assert json.loads(await asyncio.wait_for(reader.readline(), 2)) == {"decision": "none"}
        assert await asyncio.wait_for(reader.read(), 2) == b""  # EOF
        writer.close()
        await server.stop()


@pytest.mark.asyncio
async def test_handler_can_wait_longer_than_the_five_second_read_timeout():
    """The 5 s limit is for the first line only; an answered wait may take longer."""
    release = asyncio.Event()

    async def on_message(msg, reply=None):
        await release.wait()
        await reply.send({"decision": "deny"})

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "permission", "wait": True})
        await asyncio.sleep(0.2)
        assert not reader.at_eof()
        release.set()
        assert json.loads(await asyncio.wait_for(reader.readline(), 2)) == {"decision": "deny"}
        writer.close()
        await server.stop()


@pytest.mark.asyncio
async def test_non_wait_message_is_unchanged():
    """No reply object, one-argument callback, connection closed without a reply."""
    calls = []

    async def on_message(*args):
        calls.append(args)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "tool_use", "session_id": "s"})
        assert await asyncio.wait_for(reader.read(), 2) == b""
        assert calls == [({"event": "tool_use", "session_id": "s"},)]
        # "wait" must be the boolean true, not merely truthy.
        reader, writer = await _send_line(path, {"event": "permission", "wait": "yes"})
        assert await asyncio.wait_for(reader.read(), 2) == b""
        assert len(calls[1]) == 1
        writer.close()
        await server.stop()


@pytest.mark.asyncio
async def test_client_eof_while_waiting_is_reported_to_the_handler():
    seen = []

    async def on_message(msg, reply=None):
        await asyncio.wait_for(reply.disconnected.wait(), timeout=2)
        seen.append("eof")
        assert await reply.send({"decision": "allow"}) is False  # nobody listening

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "permission", "wait": True})
        await asyncio.sleep(0.1)
        assert seen == []
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.3)
        assert seen == ["eof"]
        await server.stop()


@pytest.mark.asyncio
async def test_handler_exception_closes_the_connection_without_a_reply():
    async def on_message(msg, reply=None):
        raise RuntimeError("boom")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=path)
        await server.start()
        reader, writer = await _send_line(path, {"event": "permission", "wait": True})
        assert await asyncio.wait_for(reader.read(), 2) == b""
        writer.close()
        await server.stop()
