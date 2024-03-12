from collections.abc import Awaitable
from typing import Annotated, AsyncIterator, Optional, Protocol
from typing_extensions import Doc
from urllib.parse import ParseResult

from vilha.types import ExchangeType


class Message(Protocol):
    routing_key: str
    body: str
    channel: "Channel"
    reply_to: Optional[str] = None
    correlation_id: Optional[str] = None

    async def ack(self): ...


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
        reply_to: Annotated[Optional[str], Doc("Reply queue name")] = "",
        correlation_id: Annotated[Optional[str], Doc("Reply queue name")] = "",
    ): ...

    async def basic_consume(
        self, queue_name: str, message_handler: Awaitable[[Message], None]
    ): ...

    async def close(self): ...


class Consumer(Protocol):
    async def message_handler(self, message: Message): ...


class Connection(Protocol):
    url: str
    connection_params: ParseResult

    async def connect(self): ...

    async def new_channel(self): ...


class Transport(Protocol):
    connection: "Connection"

    async def connect(self): ...
    async def new_channel(self): ...


class Server(Protocol):
    async def channel(self) -> AsyncIterator[Channel]: ...
