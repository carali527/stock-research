import asyncio
import json
from unittest.mock import AsyncMock, patch

from fugle_streaming import FugleStreaming, retry_delay


def test_retry_delay_is_bounded_and_increases():
    with patch('fugle_streaming.random.random', return_value=0):
        assert [retry_delay(n) for n in (0, 1, 2, 1000)] == [2, 4, 8, 60]


def test_shared_subscription_and_snapshot_replay():
    async def check():
        stream = FugleStreaming('test')
        stream.authenticated = True
        stream.upstream = AsyncMock()
        first, second = asyncio.Queue(), asyncio.Queue()
        await stream.subscribe(first, '2330')
        stream.candles['2330'] = {'2026-10-27T13:30:00': {'date': '2026-10-27T13:30:00', 'close': 100}}
        await stream.subscribe(second, '2330')
        stream.upstream.send.assert_awaited_once()
        assert (await second.get())['event'] == 'snapshot'
        stream.publish({'event': 'data'}, '2317')
        assert first.empty() and second.empty()
        stream.clients.clear()
        assert '2330' in stream.symbols
    asyncio.run(check())


def test_start_authenticate_resubscribe_and_wait_without_trades():
    async def check():
        stream = FugleStreaming('test', ['2330'])
        queue = asyncio.Queue()
        stream.clients[queue] = '2330'
        upstream = AsyncMock()
        messages = asyncio.Queue()
        for event in ('authenticated', 'heartbeat', 'heartbeat'):
            messages.put_nowait(json.dumps({'event': event}))
        upstream.recv.side_effect = messages.get
        connection = AsyncMock()
        connection.__aenter__.return_value = upstream
        with patch('fugle_streaming.websockets.connect', return_value=connection):
            await stream.start()
            assert (await asyncio.wait_for(queue.get(), 1))['event'] == 'authenticated'
            assert (await asyncio.wait_for(queue.get(), 1))['event'] == 'heartbeat'
            assert (await asyncio.wait_for(queue.get(), 1))['event'] == 'heartbeat'
            assert not stream.task.done()
            sent = [json.loads(call.args[0]) for call in upstream.send.await_args_list]
            assert sent[0]['event'] == 'auth'
            assert sent[1]['data']['symbols'] == ['2330']
            await stream.stop()
    asyncio.run(check())


def test_connection_failures_back_off():
    async def check():
        stream = FugleStreaming('test')
        connection = AsyncMock()
        connection.__aenter__.side_effect = OSError('offline')
        sleep = AsyncMock(side_effect=[None, None, asyncio.CancelledError])
        with patch('fugle_streaming.websockets.connect', return_value=connection), patch('fugle_streaming.asyncio.sleep', sleep), patch('fugle_streaming.random.random', return_value=0):
            try:
                await stream.run()
            except asyncio.CancelledError:
                pass
        assert [call.args[0] for call in sleep.await_args_list] == [2, 4, 8]
    asyncio.run(check())


def test_permanent_auth_error_stops_retrying():
    async def check():
        stream = FugleStreaming('invalid')
        upstream = AsyncMock()
        upstream.recv.return_value = json.dumps({'event': 'error', 'code': 1000, 'data': {'message': 'Invalid authentication credentials'}})
        connection = AsyncMock()
        connection.__aenter__.return_value = upstream
        with patch('fugle_streaming.websockets.connect', return_value=connection) as connect:
            await stream.run()
        assert connect.call_count == 1
        assert stream.error['code'] == 1000
        assert not stream.authenticated
    asyncio.run(check())
