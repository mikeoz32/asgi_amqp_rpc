import contextlib
from collections.abc import Awaitable
import aiormq
from typing import Annotated, AsyncIterator, Dict, Literal, Optional, Protocol
from typing_extensions import Doc
from urllib import parse

from aiormq.abc import AbstractChannel

class Message(Protocol):
    routing_key: str
    body: str
    channel: "Channel"
    reply_to: Optional[str] = None
    correlation_id: Optional[str] = None

    async def ack(self): ...


class Exchange:
    def __init__(
        self,
        channel: Annotated["Channel", Doc("")],
        exchange_name: Annotated[str, Doc("")],
    ) -> None:
        self.channel = channel
        self.exchange_name = exchange_name


class Consumer(Protocol):
    async def message_handler(self, message: Message): ...


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


ExchangeType = Literal["direct", "topic"]


class Channel(Protocol):
    connection: "Connection"

    async def exchange_declare(
        self,
        exchange_name: Annotated[str, Doc("Exchange name")],
        exchange_type: Annotated[
            ExchangeType, Doc("Exchange type, one for direct or topic")
        ] = "direct",
        durable: Annotated[bool, Doc("Is exchange durable")] = False,
    ): ...

    async def exchange_delete(
        self, exchange_name: Annotated[str, Doc("Exchange name")]
    ): ...

    async def queue_declare(
        self,
        *,
        passive: Annotated[bool, Doc("")],
        durable: Annotated[bool, Doc("")] = False,
        exclusive: Annotated[bool, Doc("")] = False,
        auto_delete: Annotated[bool, Doc("")] = False,
        nowait: Annotated[bool, Doc("")] = False,
    ): ...

    async def queue_bind(
        self,
        queue_name: Annotated[str, Doc("Queue name")],
        exchange_name: Annotated[str, Doc("Exchange name")],
        routing_key: Annotated[str, Doc("Routing key, allows * and .")],
    ): ...

    async def basic_publish(
        self,
        message: Annotated[str, Doc("Message to publish")],
        exchange_name: Annotated[str, Doc("Exchange name")],
        routing_key: Annotated[str, Doc("Routing key")],
    ): ...

    async def basic_consume(
        self, queue_name: str, message_handler: Awaitable[[Message], None]
    ): ...

    async def close(self): ...


class Transport(Protocol):
    connection: "Connection"

    async def connect(self): ...
    async def new_channel(self): ...


class AioRMQMessage(Message):
    def __init__(self, raw: aiormq.abc.DeliveredMessage, channel: Channel) -> None:
        self.raw = raw
        self.routing_key = raw.delivery.routing_key
        self.body = raw.body
        self.channel = channel
        self.reply_to = raw.header.properties.reply_to
        self.correlation_id = raw.header.properties.correlation_id

    async def ack(self):
        await self.raw.channel.basic_ack(self.raw.delivery.delivery_tag)


class AioRMQExchange(Exchange):
    def __init__(self, channel: Annotated["Channel", Doc("")]) -> None:
        self.channel = channel


class AioRMQChannel(Channel):
    def __init__(self, connection: "Connection", rmq_channel: AbstractChannel) -> None:
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
    ):
        await self._rmq.basic_publish(
            message.encode("utf-8"), exchange=exchange_name, routing_key=routing_key
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


class Connection:
    def __init__(self, url="amqp://rabbitmq:rabbitmq@localhost:5672/") -> None:
        self.url = url
        self.connection_params = parse.urlparse(url)

        self._transport: Transport = AioRMQTransport(self)

    async def connect(self):
        await self._transport.connect()

    async def new_channel(self):
        return await self._transport.new_channel()


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
    def __init__(self, server: "Vilha", scope: Dict) -> None:
        self.server = server
        self.scope = scope

    async def __call__(self, event: Dict):
        async with self.server.channel() as channel:
            reply_to = self.scope["reply_to"]
            await channel.basic_publish(event["body"], "test_exchange", reply_to)


RPC_QUEUE_TEMPLATE = "rpc-{}"
RPC_REPLY_QUEUE_TEMPLATE = "rpc.reply-{}-{}"


class Vilha(Consumer):
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


async def app(scope, receive, send):
    print(await receive())
    await send({"type": "rpc.response", "body": "test body"})

