
from vilha.di.datastructures import Dependant


class Container:
    def __init__(self) -> None:
        pass

    def solve_dependencies(self, *, dependant: Dependant):
        ...
