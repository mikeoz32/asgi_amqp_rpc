

from typing import Annotated
from typing_extensions import Doc

from vilha.protocol import Channel


class Exchange:
    def __init__(
        self,
        channel: Annotated[Channel, Doc("")],
        exchange_name: Annotated[str, Doc("")],
    ) -> None:
        self.channel = channel
        self.exchange_name = exchange_name


class Queue:
    def __init__(
        self,
        channel: Annotated["Channel", Doc("")],
        queue_name: Annotated[str, Doc("")],
    ) -> None:
        self.channel = channel
        self.queue_name = queue_name

    async def bind(self, exchange: Exchange, routing_key: str):
        await self.channel.queue_bind(
            self.queue_name, exchange.exchange_name, routing_key
        )

    async def consume(self, consumer):
        await self.channel.basic_consume(self.queue_name, consumer.message_handler)
