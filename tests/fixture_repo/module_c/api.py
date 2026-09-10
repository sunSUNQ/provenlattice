from typing import Protocol


class Runner(Protocol):
    def run(self, value: int) -> int: ...
