from collections.abc import Callable
from voltron.producer.AsyncProducer import AsyncProducer, Generator, Parser
from voltron.analyzer.analyzer import Analyzer

from voltron.utils.logger import logger

from pathlib import Path

class Mapper:
    """Mapper between actual messages and abstract symbols.
    
    Select generator and parser
    """
    def __init__(
        self,
        producer: AsyncProducer,
        analyzer: Analyzer
    ) -> None:
        self.producer = producer
        self.analyzer = analyzer
        
        self.req_types: list[str] = producer.req_types
        self.res_types: list[str] = producer.res_types
        
        self.generators: dict[str, list[Generator]] = producer.generators
        self.parsers: list[Parser] = producer.parsers
        
        self.cur_parser: Parser
        self.equip_parser(self.parsers[-1])
        
        logger.debug('Mapper: finish init')
        
    def generate(
        self,
        g: Generator
    ) -> bytes:
        name_space = {}
        try:
            with open(g.path, 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'generated_{g.msg_type}']
                return obj()
        except Exception as e:
            logger.error(f'Mapper: generated failure {e}')
            exit(0)
    
    def equip_parser(
        self,
        p: Parser
    ) -> None:
        self.cur_parser = p
        
    def select_generators(
        self,
        req_seq
    ) -> list[Generator]:
        gs: list[Generator] = []
        for req in req_seq:
            gs.append(self.generators[req][0])
        return gs
    
    def select_generator(
        self,
        req_type
    ) -> Generator:
        return self.generators[req_type][0]
            
    # def parse_msg(
    #     self,
    #     msg: bytes
    # ) -> str:
    #     try:
    #         resp_code = self.parser(msg)
    #         with self.analyzer.lock:
    #             self.analyzer.res_types_update(self.analyzer.last_recv)
    #             self.analyzer.trans_types_update(f'{self.analyzer.last_sent}/{self.analyzer.last_recv}')
    #         return resp_code
    #     except Exception as e:
    #         logger.error(f'Mapper: parse failure {e}')
    #         exit(0)
    #     return str(resp_code)
    
    # def parse_exception(
    #     self,
    #     status: str
    # ) -> str:
    #     with self.analyzer.lock:
    #         self.analyzer.res_types_update(self.analyzer.last_recv)
    #         self.analyzer.trans_types_update(f'{self.analyzer.last_sent}/{self.analyzer.last_recv}')
    #     return status
