from typing import Any, Callable, List, Optional


class Dependant:
    def __init__(
        self,
        *,
        dependencies: Optional[List["Dependant"]] = None,
        call: Optional[Callable[..., Any]] = None,
        name: Optional[str] = None
    ) -> None:
        self.dependencies = dependencies or []
        self.call = call
        self.name = name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name}{self.call},{self.dependencies})"

class Depends:
    def __init__(
        self, dependency: Optional[Callable[..., Any]] = None, *, use_cache: bool = True
    ):
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", type(self.dependency).__name__)
        cache = "" if self.use_cache else ", use_cache=False"
        return f"{self.__class__.__name__}({attr}{cache})"
