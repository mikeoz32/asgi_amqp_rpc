from collections.abc import Awaitable
from typing import Annotated, Any, Optional
from typing_extensions import Doc
import aiormq
from aiormq.abc import AbstractChannel, DeliveredMessage
from vilha.datastructures import Exchange, Queue
from vilha.protocol import Channel, Connection, Message, Transport
from vilha.types import ExchangeType


class AioRMQMessage(Message):
    def __init__(self, raw: DeliveredMessage, channel: Channel) -> None:
        self.raw = raw
        self.routing_key = raw.delivery.routing_key
        self.body = raw.body
        self.channel = channel
        self.reply_to = raw.header.properties.reply_to
        self.correlation_id = raw.header.properties.correlation_id
        print(self.correlation_id)

    async def ack(self):
        await self.raw.channel.basic_ack(self.raw.delivery.delivery_tag)


class AioRMQExchange(Exchange):
    def __init__(self, channel: Annotated["Channel", Doc("")]) -> None:
        self.channel = channel


class AioRMQChannel(Channel):
    def __init__(self, connection: Connection, rmq_channel: AbstractChannel) -> None:
        self._rmq = rmq_channel
        self.connection = connection

    async def exchange_declare(
        self,
        exchange_name: Annotated[str, Doc("Exchange name")],
        exchange_type: Annotated[
            ExchangeType, Doc("Exchange type, one for direct or topic")
        ] = "direct",
        durable: Annotated[bool, Doc("Is exchange durable")] = False,
    ):
        await self._rmq.exchange_declare(
            exchange_name, exchange_type=exchange_type, durable=durable
        )

        return Exchange(self, exchange_name)

    async def queue_declare(
        self,
        queue_name: Annotated[str, Doc("Queue name")],
        *,
        passive: Annotated[bool, Doc("")] = False,
        durable: Annotated[bool, Doc("")] = False,
        exclusive: Annotated[bool, Doc("")] = False,
        auto_delete: Annotated[bool, Doc("")] = False,
        nowait: Annotated[bool, Doc("")] = False,
    ):
        await self._rmq.queue_declare(
            queue_name,
            passive=passive,
            durable=durable,
            exclusive=exclusive,
            auto_delete=auto_delete,
            nowait=nowait,
        )

        return Queue(self, queue_name)

    async def queue_bind(
        self,
        queue_name: Annotated[str, Doc("Queue name")],
        exchange_name: Annotated[str, Doc("Exchange name")],
        routing_key: Annotated[str, Doc("Routing key, allows * and .")],
    ):
        await self._rmq.queue_bind(queue_name, exchange_name, routing_key)

    async def close(self):
        await self._rmq.close()

    async def basic_consume(
        self, queue_name: str, message_handler: Awaitable[[Message], None]
    ):
        async def handler(message: aiormq.abc.DeliveredMessage):
            await message_handler(AioRMQMessage(message, self))

        await self._rmq.basic_consume(queue_name, handler)

    async def basic_publish(
        self,
        message: Annotated[str, Doc("Message to publish")],
        exchange_name: Annotated[str, Doc("Exchange name")],
        routing_key: Annotated[str, Doc("Routing key")],
        reply_to: Annotated[Optional[str], Doc("Reply queue name")] = "",
        correlation_id: Annotated[Optional[str], Doc("Reply queue name")] = "",
    ):
        await self._rmq.basic_publish(
            message.encode("utf-8"),
            exchange=exchange_name,
            routing_key=routing_key,
            properties=aiormq.spec.Basic.Properties(
                reply_to=reply_to, correlation_id=correlation_id
            ),
        )


class AioRMQTransport(Transport):
    def __init__(
        self, connection: Annotated["Connection", Doc("Owning connection")]
    ) -> None:
        self._rmq = None
        self.connection = connection

    async def connect(self):
        self._rmq = await aiormq.connect(str(self.connection.url))

    async def new_channel(self):
        rmq_channel = await self._rmq.channel()
        return AioRMQChannel(self, rmq_channel)
