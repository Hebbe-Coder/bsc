import asyncio
import sqlite3

from app.orchestrator.contracts import EventType
from app.orchestrator.sse import SessionEventBus


def test_persistent_event_store_replays_terminal_history_after_restart(tmp_path):
    from app.orchestrator.event_store import SQLiteEventStore

    connection = sqlite3.connect(str(tmp_path / "events.db"), check_same_thread=False)
    connection.row_factory = sqlite3.Row

    async def scenario():
        first = SessionEventBus(event_store=SQLiteEventStore(connection))
        await first.publish("persisted-1", EventType.PIPELINE_STARTED, status="running")
        await first.publish(
            "persisted-1",
            EventType.PIPELINE_COMPLETED,
            status="completed",
            terminal=True,
        )

        restarted = SessionEventBus(event_store=SQLiteEventStore(connection))
        return [event async for event in restarted.subscribe("persisted-1", after=0)]

    replay = asyncio.run(scenario())
    connection.close()

    assert [event.seq for event in replay] == [1, 2]
    assert replay[-1].type == EventType.PIPELINE_COMPLETED
    assert replay[-1].terminal is True


def test_persistent_event_store_continues_sequence_after_restart(tmp_path):
    from app.orchestrator.event_store import SQLiteEventStore

    connection = sqlite3.connect(str(tmp_path / "events.db"), check_same_thread=False)
    connection.row_factory = sqlite3.Row

    async def scenario():
        first = SessionEventBus(event_store=SQLiteEventStore(connection))
        await first.publish("persisted-2", EventType.PIPELINE_STARTED, status="running")

        restarted = SessionEventBus(event_store=SQLiteEventStore(connection))
        return await restarted.publish(
            "persisted-2",
            EventType.STAGE_STARTED,
            stage="planner",
            status="running",
        )

    event = asyncio.run(scenario())
    connection.close()

    assert event.seq == 2


def test_api_event_bus_uses_configured_sqlite_connection(tmp_path, monkeypatch):
    from app.api import orchestrate as orchestrate_api

    connection = sqlite3.connect(str(tmp_path / "api-events.db"), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    monkeypatch.setattr(orchestrate_api, "get_db", lambda: connection)

    async def scenario():
        bus = orchestrate_api.build_event_bus()
        return await bus.publish(
            "api-persisted-1",
            EventType.PIPELINE_STARTED,
            status="running",
        )

    event = asyncio.run(scenario())
    row = connection.execute(
        "SELECT seq, event_type FROM orchestrator_events WHERE session_id = ?",
        ("api-persisted-1",),
    ).fetchone()
    connection.close()

    assert row["seq"] == event.seq == 1
    assert row["event_type"] == EventType.PIPELINE_STARTED.value
