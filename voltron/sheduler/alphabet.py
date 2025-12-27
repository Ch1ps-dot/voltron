from collections.abc import Callable
from ..handler import handler

class Symbol:
    """Symbol stands for unique action in protocol statemachine.

    Attributes
        name: name of symbol
    """
    def __init__(
            self,
            name: str,
            func: Callable[[], str]
    ) -> None:
        self.name: str = name
        self.func: Callable[[], str] = func

    def instance(
            self
    ):
        return self.func()

class Alphabet:
    """Alhpabet stands for all actions in protocol statemachine.
"""
    def __init__(
            self
    ) -> None:
        self.input_symbols: list[Symbol]
        self.output_symbols: list[Symbol]

    def set_input_symbols(
            self,
            inputs
    ) -> None:
        pass

    def set_ouput_symbols(
            self
    ) -> None:
        pass