from asyncio import get_event_loop
from typing import Annotated, Any
from vilha.client import ClientFactory

from vilha.di import get_typed_signature, call_with_deps
from vilha.di.datastructures import Depends
from vilha.di.utils import get_dependant, solve_dependencies

client = ClientFactory("amqp://rabbitmq:rabbitmq@localhost:5672/")
#

def get_client():
    return ClientFactory("amqp://rabbitmq:rabbitmq@localhost:5672/")
 

def get_something():
    return "something"

async def gel(el: Annotated[Any, Depends(get_client)]):
    return el

async def main(just_param: str, client: Annotated[ClientFactory, Depends(gel)]):
    for i in range(0, 30):
        # try:
            result = await client.test_service.test_method()
            print(result)
        # except Exception as e:
        #     print(e)
#             
#

async def getdeps():
    # print(await solve_dependencies(dependant=get_dependant(call=main, name="main")))
    print(await call_with_deps(main))


loop = get_event_loop()
loop.run_until_complete(getdeps())
