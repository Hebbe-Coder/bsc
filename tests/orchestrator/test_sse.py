import asyncio

from app.orchestrator.contracts import EventType
from app.orchestrator.sse import SessionEventBus


async def _next(subscription):
    return await asyncio.wait_for(anext(subscription), timeout=0.2)


def test_replays_events_after_sequence():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        await bus.publish("s1", EventType.PIPELINE_STARTED, status="running")
        await bus.publish("s1", EventType.STAGE_STARTED, stage="planner", status="running")
        sub = bus.subscribe("s1", after=1)
        event = await _next(sub)
        await sub.aclose()
        assert event.seq == 2
        assert event.stage == "planner"

    asyncio.run(scenario())


def test_two_subscribers_receive_same_event():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        left = bus.subscribe("s1")
        right = bus.subscribe("s1")
        left_task = asyncio.create_task(_next(left))
        right_task = asyncio.create_task(_next(right))
        await asyncio.sleep(0)
        await bus.publish("s1", EventType.STAGE_STARTED, stage="sop", status="running")
        first, second = await asyncio.gather(left_task, right_task)
        await left.aclose()
        await right.aclose()
        assert first.seq == second.seq == 1

    asyncio.run(scenario())


def test_terminal_event_closes_subscription():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        await bus.publish(
            "s1",
            EventType.PIPELINE_COMPLETED,
            status="completed",
            terminal=True,
        )
        sub = bus.subscribe("s1")
        event = await _next(sub)
        assert event.terminal is True
        try:
            await _next(sub)
            assert False, "subscription must close after terminal event"
        except StopAsyncIteration:
            pass

    asyncio.run(scenario())


def test_subscription_after_terminal_cursor_closes_immediately():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        event = await bus.publish(
            "s1",
            EventType.PIPELINE_COMPLETED,
            status="completed",
            terminal=True,
        )
        sub = bus.subscribe("s1", after=event.seq)
        try:
            await _next(sub)
            assert False, "subscription must remain closed after terminal event"
        except StopAsyncIteration:
            pass

    asyncio.run(scenario())


def test_legacy_dict_publish_remains_compatible():
    async def scenario():
        bus = SessionEventBus(history_limit=8)
        event = await bus.publish(
            "s1",
            {"stage": "planner", "status": "running", "msg": "start"},
        )
        assert event.type == EventType.STAGE_STARTED
        assert event.message == "start"

    asyncio.run(scenario())
