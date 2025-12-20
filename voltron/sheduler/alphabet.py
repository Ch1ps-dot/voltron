"""Symbol stands for unique action in protocol statemachine.
"""
class Symbol:
    def __init__(
            self
    ) -> None:
        pass

"""Alhpabet stands for all actions in protocol statemachine.
"""
class Alphabet:
    def __init__(
            self
    ) -> None:
        self.send_symbols: dict
        self.recv_symbols: dict

    def set_send_symbols(
            self
    ) -> None:
        pass

    def set_recv_symbols(
            self
    ) -> None:
        pass