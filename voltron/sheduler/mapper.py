from collections.abc import Callable
from voltron.producer.AsyncProducer import AsyncProducer, Generator, Parser

from voltron.utils.logger import logger

from pathlib import Path

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
        
        self.generator_info = producer.generator_info
        self.parser_info = producer.parser_info
        
        logger.debug('Mapper: finish init')

    def setup_generators(
            self
    ) -> dict[str, Generator]:
        
    
    def setup_parsers(
            self
    ) -> dict[str, Parser]:
        
    
    def generate(
            self,
            code: str,
            code_name: str
    ) -> Callable:
        name_space = {}
        exec(code, name_space)
        obj = name_space[code_name]
        return obj
    
    def parse(
            self,
            msg: bytes
    ) -> str:
        pass

    def show(
            self
    ) -> None:
        print('===input===')
        for s in self.input_InputSymbols.keys():
            print(s)
        print('===output===')
        for s in self.output_InputSymbols.keys():
            print(s)