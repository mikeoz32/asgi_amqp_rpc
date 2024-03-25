# Vilha

Rpc server inspired by nameko and aims to `extend` asgi protocol to allow use of asgi middlewares and starlette
with DI inspired by FastAPI

# Example 
```python
import asyncio
from vilha.server import Vilha
from vilha.starlette.applications import RpcRoute, Starlette
from vilha.di import Depends
import random

async def get_rnd():
    return random.randint(0,100)

async def test_method(rnd: Annotated[int, Depends(get_rnd)]):
    print("test_method")
    return rnd


st = Starlette(routes=[RpcRoute("test_method", test_method)])


async def main():
    await Vilha("test_service").run(st)


loop = asyncio.get_event_loop()
loop.create_task(main())

loop.run_forever()
```
