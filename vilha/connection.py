from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from typing import Dict
from urllib import parse
from vilha.protocol import Channel, Server, Transport

from vilha.transport.aiormq import AioRMQTransport


class Connection:
    def __init__(self, url="amqp://rabbitmq:rabbitmq@localhost:5672/") -> None:
        self.url = url
        self.connection_params = parse.urlparse(url)

        self._transport: Transport = AioRMQTransport(self)

    async def connect(self):
        await self._transport.connect()

    async def new_channel(self) -> Channel:
        return await self._transport.new_channel()

    @asynccontextmanager
    async def channel(self) -> AsyncIterable[Channel]:
        channel = await self.new_channel()
        yield channel
        await channel.close()


class Receive:
    """
    type = rpc.request - when request is single message request
    type = rpc.event - when request is event that does not accepts responses
    type = rpc.stream.start - when request is stream and will end on rpc.stream.end type
    type = rpc.stream.end - when stream is completed
    """

    def __init__(self, event_name, body) -> None:
        self.event_name = event_name
        self.body = body

    async def __call__(self) -> Dict:
        return dict(type=self.event_name, body=self.body, more_body=None)


class Send:
    def __init__(self, server: Server, scope: Dict) -> None:
        self.server = server
        self.scope = scope
        print(scope)

    async def __call__(self, event: Dict):
        async with self.server.channel() as channel:
            reply_to = self.scope["reply_to"]
            correlation_id = self.scope["correlation_id"]
            await channel.basic_publish(
                event["body"], "test_exchange", reply_to, correlation_id=correlation_id
            )
