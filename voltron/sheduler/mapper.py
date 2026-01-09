from collections.abc import Callable
from voltron.handler.asyncHandler import asyncHandler
from voltron.utils.logger import logger

from pathlib import Path

class InputSymbol:
    """Symbol stands for unique action in protocol statemachine.

    Attributes
        name: name of symbol
    """
    def __init__(
            self,
            msg_type: str
    ) -> None:
        self.msg_type: str = msg_type
        self.generator_path: Path = 
        self.type = type

class Mapper:
    """Alhpabet stands for all actions in protocol statemachine.
    """
    def __init__(
            self,
            handler: asyncHandler
    ) -> None:
        self.handler = handler

        self.input_symbols: dict[str, Symbol] = self.set_input_symbols()
        self.output_symbols: dict[str, Symbol] = self.set_ouput_symbols()
        logger.debug('[Alphabet: finish init]')

    def set_input_symbols(
            self
    ) -> dict[str, Symbol]:
        ss:dict[str, Symbol] = {}
        for msg_s in self.handler.req_types:
            s = Symbol(
                name=msg_s, 
                func=self.symbol_instance(
                    self.handler.inputs_code[msg_s],
                    f'input_{msg_s}'),
                type='in'
            )
            ss[msg_s] = s
        return ss
    
    def set_ouput_symbols(
            self
    ) -> dict[str, Symbol]:
        ss:dict[str, Symbol] = {}
        for msg_s in self.handler.res_types:
            s = Symbol(
                name=msg_s, 
                func=self.symbol_instance(
                    self.handler.pkt_parser_code,
                    'packet_parser'),
                type='out'
            )
            ss[msg_s] = s
        return ss
    
    def symbol_instance(
            self,
            code: str,
            code_name: str
    ) -> Callable:
        name_space = {}
        exec(code, name_space)
        obj = name_space[code_name]
        return obj

    def show(
            self
    ) -> None:
        print('===input===')
        for s in self.input_symbols.keys():
            print(s)
        print('===output===')
        for s in self.output_symbols.keys():
            print(s)