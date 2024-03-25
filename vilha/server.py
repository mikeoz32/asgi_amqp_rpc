import contextlib
from typing import AsyncIterator
from vilha.connection import Connection, Receive, Send
from vilha.protocol import Channel, Consumer, Message, Server


RPC_QUEUE_TEMPLATE = "rpc-{}"


class Vilha(Consumer, Server):
    def __init__(self, service_name: str) -> None:
        self.app = None
        self.connection = Connection()
        self.service_name = service_name
        self.rpc_queue_name = RPC_QUEUE_TEMPLATE.format(service_name)
        self.rpc_routing_key = "{}.*".format(service_name)

    async def run(self, app):
        self.app = app
        await self.initialize()

    async def initialize(self):
        await self.connection.connect()

        channel = await self.connection.new_channel()
        exchange = await channel.exchange_declare(
            "test_exchange", exchange_type="topic"
        )
        queue = await channel.queue_declare(self.rpc_queue_name)
        await queue.bind(exchange, self.rpc_routing_key)
        await queue.consume(self)

    @contextlib.asynccontextmanager
    async def channel(self) -> AsyncIterator[Channel]:
        channel = await self.connection.new_channel()
        yield channel
        await channel.close()

    async def message_handler(self, message: Message):
        method_name = message.routing_key.replace(f"{self.service_name}.", "")
        scope = dict(
            type="rpc",
            correlation_id=message.correlation_id,
            reply_to=message.reply_to,
            method_name=method_name,
        )
        await message.ack()

        await self.app(
            scope,
            Receive(event_name="rpc.request", body=message.body),
            Send(self, scope),
        )
