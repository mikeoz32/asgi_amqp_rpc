from dataclasses import field, dataclass
import json
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Sequence
from starlette import (
    routing,
    applications,
    types,
    responses,
    websockets,
    _utils,
    datastructures,
    middleware,
)
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette.concurrency import run_in_threadpool
from vilha.di import call_with_deps


@dataclass
class RequestBody:
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)


class Request:
    def __init__(
        self, scope: types.Scope, receive: types.Receive, send: types.Send
    ) -> None:
        self.scope = scope
        self.receive = receive
        self.send = send
        self._body = None

    async def body(self):
        if self._body is None:
            event = await self.receive()
            body = event["body"]

            json_body = json.loads(body)

            print(json_body)
            self._body = RequestBody(**json_body)

        return self._body

    async def args(self):
        return (await self.body()).args

    async def kwargs(self):
        return (await self.body()).kwargs


class Response:
    def __init__(self, body: Any) -> None:
        self._body = body

    async def __call__(self, scope: types.Scope, receive: types.Receive, send: types.Send) -> Any:
        result = {'result': self._body, 'error': None}
        result = json.dumps(result)
        print(result)
        await send({"type":"rpc.response", "body":result})


def request_response(
    func: Callable[[Request], Awaitable[Response] | Response],
) -> types.ASGIApp:
    """
    Takes a function or coroutine `func(request) -> response`,
    and returns an ASGI application.
    """

    async def app(scope: types.Scope, receive: types.Receive, send: types.Send) -> None:
        request = Request(scope, receive, send)

        async def app(
            scope: types.Scope, receive: types.Receive, send: types.Send
        ) -> None:
            args = await request.args()
            kwargs = await request.kwargs()
            # if _utils.is_async_callable(func):
            #     response = await func(*args, **kwargs)
            # else:
            #     response = await run_in_threadpool(func, *args, **kwargs)
            response = await call_with_deps(func, ctx=scope)
            await Response(response)(scope, receive, send)

        await wrap_app_handling_exceptions(app, request)(scope, receive, send)

    return app


class BaseRoute(routing.BaseRoute):
    async def __call__(
        self, scope: types.Scope, receive: types.Receive, send: types.Send
    ) -> None:
        """
        A route may be used in isolation as a stand-alone ASGI app.
        This is a somewhat contrived case, as they'll almost always be used
        within a Router, but could be useful for some tooling and minimal apps.
        """
        match, child_scope = self.matches(scope)
        if match == routing.Match.NONE:
            if scope["type"] == "http" or scope["type"] == "rpc":
                response = responses.PlainTextResponse("Not Found", status_code=404)
                await response(scope, receive, send)
            elif scope["type"] == "websocket":
                websocket_close = websockets.WebSocketClose()
                await websocket_close(scope, receive, send)
            return

        scope.update(child_scope)
        await self.handle(scope, receive, send)


class RpcRoute(BaseRoute):
    def __init__(self, name: str, endpoint: Callable[..., Any]) -> None:
        self.name = name
        self.endpoint = endpoint
        self.app = request_response(endpoint)

    def matches(self, scope: types.Scope) -> tuple[routing.Match, types.Scope]:
        if scope["type"] == "rpc":
            if scope["method_name"] == self.name:
                return routing.Match.FULL, {"endpoint": self.endpoint}
        return routing.Match.NONE, {}

    async def handle(
        self, scope: types.Scope, receive: types.Receive, send: types.Send
    ) -> None:
        await self.app(scope, receive, send)


class Router(routing.Router):
    async def app(
        self, scope: types.Scope, receive: types.Receive, send: types.Send
    ) -> None:
        assert scope["type"] in ("http", "websocket", "lifespan", "rpc")

        if "router" not in scope:
            scope["router"] = self

        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        partial = None

        for route in self.routes:
            # Determine if any route matches the incoming scope,
            # and hand over to the matching route if found.
            match, child_scope = route.matches(scope)
            if match == routing.Match.FULL:
                scope.update(child_scope)
                await route.handle(scope, receive, send)
                return
            elif match == routing.Match.PARTIAL and partial is None:
                partial = route
                partial_scope = child_scope

        if partial is not None:
            #  Handle partial matches. These are cases where an endpoint is
            # able to handle the request, but is not a preferred option.
            # We use this in particular to deal with "405 Method Not Allowed".
            scope.update(partial_scope)
            await partial.handle(scope, receive, send)
            return

        if scope["type"] == "http":
            route_path = _utils.get_route_path(scope)
            if self.redirect_slashes and route_path != "/":
                redirect_scope = dict(scope)
                if route_path.endswith("/"):
                    redirect_scope["path"] = redirect_scope["path"].rstrip("/")
                else:
                    redirect_scope["path"] = redirect_scope["path"] + "/"

                for route in self.routes:
                    match, child_scope = route.matches(redirect_scope)
                    if match != routing.Match.NONE:
                        redirect_url = datastructures.URL(scope=redirect_scope)
                        response = responses.RedirectResponse(url=str(redirect_url))
                        await response(scope, receive, send)
                        return

        await self.default(scope, receive, send)


class Starlette(applications.Starlette):
    def __init__(
        self: types.AppType,
        debug: bool = False,
        routes: Sequence[BaseRoute] | None = None,
        middleware: Sequence[middleware.Middleware] | None = None,
        exception_handlers: Mapping[Any, types.ExceptionHandler] | None = None,
        on_startup: Sequence[Callable[[], Any]] | None = None,
        on_shutdown: Sequence[Callable[[], Any]] | None = None,
        lifespan: types.Lifespan[types.AppType] | None = None,
    ) -> None:
        # The lifespan context function is a newer style that replaces
        # on_startup / on_shutdown handlers. Use one or the other, not both.
        assert lifespan is None or (
            on_startup is None and on_shutdown is None
        ), "Use either 'lifespan' or 'on_startup'/'on_shutdown', not both."

        self.debug = debug
        self.state = datastructures.State()
        self.router = Router(
            routes, on_startup=on_startup, on_shutdown=on_shutdown, lifespan=lifespan
        )
        self.exception_handlers = (
            {} if exception_handlers is None else dict(exception_handlers)
        )
        self.user_middleware = [] if middleware is None else list(middleware)
        self.middleware_stack: types.ASGIApp | None = None
