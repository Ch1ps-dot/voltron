from collections.abc import Callable
from voltron.producer.AsyncProducer import AsyncProducer
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
    """Mapper between actual messages and abstract symbols.
    
    Recv a request symbol, return an actual message
    Recv a response message, return an request symbol
    """
    def __init__(
            self,
            producer: AsyncProducer
    ) -> None:
        self.producer = producer
        
        self.ins_set: list[str] = producer.req_types
        self.ous_set: list[str] = producer.res_types

        self.input_InputSymbols: dict[str, InputSymbol] = self.set_input_InputSymbols()
        self.output_InputSymbols: dict[str, InputSymbol] = self.set_ouput_InputSymbols()
        logger.debug('[Alphabet: finish init]')

    def set_input_InputSymbols(
            self
    ) -> dict[str, InputSymbol]:
        ss:dict[str, InputSymbol] = {}
        for msg_s in self.handler.req_types:
            s = InputSymbol(
                name=msg_s, 
                func=self.InputSymbol_instance(
                    self.handler.inputs_code[msg_s],
                    f'input_{msg_s}'),
                type='in'
            )
            ss[msg_s] = s
        return ss
    
    def set_ouput_InputSymbols(
            self
    ) -> dict[str, InputSymbol]:
        ss:dict[str, InputSymbol] = {}
        for msg_s in self.handler.res_types:
            s = InputSymbol(
                name=msg_s, 
                func=self.InputSymbol_instance(
                    self.handler.pkt_parser_code,
                    'packet_parser'),
                type='out'
            )
            ss[msg_s] = s
        return ss
    
    def InputSymbol_instance(
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
        for s in self.input_InputSymbols.keys():
            print(s)
        print('===output===')
        for s in self.output_InputSymbols.keys():
            print(s)