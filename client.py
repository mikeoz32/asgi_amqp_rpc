
from asyncio import get_event_loop
from vilha.client import Client


client = Client("amqp://rabbitmq:rabbitmq@localhost:5672/")

async def main():
    for i in range(0, 30):
        try:
            result = await client.call("test_service","test_method")
            print(result)
        except Exception as e:
            print(e)
            

loop = get_event_loop()
loop.run_until_complete(main())
