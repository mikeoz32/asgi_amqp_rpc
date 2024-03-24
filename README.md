# Vilha

Rpc server inspired by nameko and aims to `extend` asgi protocol to allow use of asgi middlewares and Starlette

# Example 
```python
import asyncio
from vilha.server import Vilha
from vilha.starlette.applications import RpcRoute, Starlette


async def test_method():
    print("test_method")
    return 10


st = Starlette(routes=[RpcRoute("test_method", test_method)])


async def main():
    await Vilha("test_service").run(st)


loop = asyncio.get_event_loop()
loop.create_task(main())

loop.run_forever()
```
