from asyncio import Future
import json
from typing import Any, Dict

from vilha.connection import Connection
from vilha.protocol import Consumer, Message
import uuid


RPC_REPLY_QUEUE_TEMPLATE = "rpc.reply-{}-{}"


def parse_response(result: Dict[str, Any]):
    response = json.loads(result)
    if response.get("error") is not None:
        raise Exception(response["error"])
    return response["result"]

class Client(Consumer):
    def __init__(self, brocker_url: str, service_name: str, method_name: str) -> None:
        self.connection = None
        self._service_name = service_name
        self._method_name = method_name
        self.brocker_url = brocker_url
        self.client_id = str(uuid.uuid4())
        self._intialized = False
        self._futures: Dict[str, Future] = {}
        self.reply_to= str(uuid.uuid4())

    @property
    def routing_key(self) -> str:
        return "{}.{}".format(self._service_name, self._method_name)

    async def __call__(self, *args: Any, **kwds: Any) -> Any:
        return await self.call(*args, **kwds)


    async def call(self, *args, **kwargs) -> Future:
        if self._intialized is False:
            await self.initialize()

        async with self.connection.channel() as channel:
            correlation_id = str(uuid.uuid4())

            future = Future()
            self._futures[correlation_id] = future
            await channel.basic_publish(
                '{"args":[], "kwargs":{}}',
                "test_exchange",
                self.routing_key,
                reply_to=self.reply_to,
                correlation_id=correlation_id,
            )
        response = await future
        return parse_response(response)

    async def initialize(self):
        queue_name = RPC_REPLY_QUEUE_TEMPLATE.format(self.client_id, self.reply_to)

        print(self.brocker_url)
        self.connection = Connection(self.brocker_url)
        await self.connection.connect()

        channel = await self.connection.new_channel()

        exchange = await channel.exchange_declare(
            "test_exchange", exchange_type="topic"
        )

        queue = await channel.queue_declare(queue_name)
        await queue.bind(exchange, self.reply_to)
        await queue.consume(self)

    async def message_handler(self, message: Message):
        correlation_id = message.correlation_id

        future = self._futures.pop(correlation_id, None)

        if future is None:
            print(f"Future not found for correlation_id {correlation_id}")
            return

        future.set_result(message.body)


class ClientFactory():
    def __init__(self, brocker_url: str) -> None:
        self._brocker_url = brocker_url

    def __getattribute__(self, __name: str) -> Any:
        try:
            return super().__getattribute__(__name)
        except:
            ...
        return ServiceFactory(self._brocker_url, __name)


class ServiceFactory():
    def __init__(self, brocker_url: str, service_name: str) -> None:
        self._brocker_url = brocker_url 
        self._service_name = service_name

    def __getattribute__(self, __name: str) -> Any:
        try:
            return super().__getattribute__(__name)
        except:
            ...
        return Client(self._brocker_url, self._service_name, __name)
