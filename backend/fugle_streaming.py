"""Process-local Fugle connection, independent of market hours and browser lifetime."""
import asyncio
import json
import logging
import random
import time

import websockets

logger = logging.getLogger(__name__)
URL = 'wss://api.fugle.tw/marketdata/v1.0/stock/streaming'
PERMANENT_ERRORS = {
    'Invalid authentication credentials',
    'Cannot switch user on an authenticated connection',
    'Your plan does not support this product type',
}


def retry_delay(attempt):
    return min(60, 2 ** min(attempt + 1, 6)) + random.random()


class FugleStreaming:
    def __init__(self, api_key, symbols=()):
        self.api_key = api_key
        self.symbols = set(symbols)
        self.clients = {}
        self.candles = {}
        self.upstream = None
        self.authenticated = False
        self.task = None
        self.error = None

    async def start(self):
        if self.api_key:
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def publish(self, message, symbol=None):
        for queue, selected in list(self.clients.items()):
            if symbol is None or selected == symbol:
                if queue.full():
                    # Disconnect slow consumers rather than block the upstream heartbeat.
                    self.clients.pop(queue, None)
                    while not queue.empty():
                        queue.get_nowait()
                    queue.put_nowait(None)
                else:
                    queue.put_nowait(message)

    async def subscribe(self, queue, symbol):
        self.clients[queue] = symbol
        if self.error:
            queue.put_nowait(self.error)
            return
        new = symbol not in self.symbols
        self.symbols.add(symbol)
        if new and self.authenticated:
            await self.upstream.send(json.dumps({
                'event': 'subscribe', 'data': {'channel': 'candles', 'symbol': symbol},
            }))
        elif symbol in self.candles:
            queue.put_nowait({'event': 'snapshot', 'channel': 'candles', 'data': {
                'symbol': symbol, 'data': list(self.candles[symbol].values()),
            }})

    async def run(self):
        attempt = 0
        while True:
            connected_at = time.monotonic()
            try:
                async with websockets.connect(URL, open_timeout=30, ping_interval=20, ping_timeout=30) as upstream:
                    self.upstream = upstream
                    await upstream.send(json.dumps({'event': 'auth', 'data': {'apikey': self.api_key}}))
                    while True:
                        # Heartbeats arrive even outside trading hours; lack of trades is normal.
                        message = json.loads(await asyncio.wait_for(upstream.recv(), timeout=75))
                        event = message.get('event')
                        if event == 'authenticated':
                            self.authenticated = True
                            self.candles.clear()
                            if self.symbols:
                                await upstream.send(json.dumps({'event': 'subscribe', 'data': {
                                    'channel': 'candles', 'symbols': sorted(self.symbols),
                                }}))
                            self.publish(message)
                        elif event == 'error':
                            self.publish(message)
                            if message.get('data', {}).get('message') in PERMANENT_ERRORS:
                                self.error = message
                                return
                        elif event in ('snapshot', 'data') and message.get('channel') == 'candles':
                            data = message.get('data', {})
                            symbol = data.get('symbol')
                            rows = data.get('data', []) if event == 'snapshot' else [data]
                            cache = self.candles.setdefault(symbol, {})
                            if event == 'snapshot':
                                cache.clear()
                            for row in rows:
                                date = row.get('date', '')
                                if cache and date[:10] != next(iter(cache))[:10]:
                                    cache.clear()
                                cache[date] = row
                            self.publish(message, symbol)
                        elif event in ('heartbeat', 'pong'):
                            self.publish(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning('Fugle streaming disconnected (%s)', type(exc).__name__)
            finally:
                self.authenticated = False
                self.upstream = None
            self.publish({'event': 'reconnecting'})
            # A brief successful handshake must not reset repeated failures' backoff.
            if time.monotonic() - connected_at >= 120:
                attempt = 0
            await asyncio.sleep(retry_delay(attempt))
            attempt += 1
