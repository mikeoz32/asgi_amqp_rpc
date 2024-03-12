from asyncio import Future
import json
from typing import Any, Dict

from vilha.connection import Connection
from vilha.protocol import Consumer, Message
import uuid


RPC_REPLY_QUEUE_TEMPLATE = "rpc.reply-{}-{}"


def parse_response(result: Dict[str, Any]):
    response = json.loads(result)
    if response["error"] is not None:
        raise Exception(response["error"])
    return response["result"]


class Client(Consumer):
    def __init__(self, brocker_url: str) -> None:
        self.connection = None
        self.brocker_url = brocker_url
        self.client_id = str(uuid.uuid4())
        self._intialized = False
        self._futures: Dict[str, Future] = {}
        self.routing_key = str(uuid.uuid4())

    async def call(self, service_name: str, method_name: str) -> Future:
        if self._intialized is False:
            await self.initialize()

        async with self.connection.channel() as channel:
            correlation_id = str(uuid.uuid4())

            routing_key = "{}.{}".format(service_name, method_name)
            future = Future()
            self._futures[correlation_id] = future
            await channel.basic_publish(
                '{"args":[], "kwargs":{}}',
                "test_exchange",
                routing_key,
                reply_to=self.routing_key,
                correlation_id=correlation_id,
            )
        response = await future
        return parse_response(response)

    async def initialize(self):
        queue_name = RPC_REPLY_QUEUE_TEMPLATE.format(self.client_id, self.routing_key)

        self.connection = Connection(self.brocker_url)
        await self.connection.connect()

        channel = await self.connection.new_channel()

        exchange = await channel.exchange_declare(
            "test_exchange", exchange_type="topic"
        )

        queue = await channel.queue_declare(queue_name)
        await queue.bind(exchange, self.routing_key)
        await queue.consume(self)

    async def message_handler(self, message: Message):
        correlation_id = message.correlation_id

        future = self._futures.pop(correlation_id, None)

        if future is None:
            print(f"Future not found for correlation_id {correlation_id}")
            return

        future.set_result(message.body)
