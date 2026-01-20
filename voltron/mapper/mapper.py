from collections.abc import Callable
from voltron.producer.AsyncProducer import AsyncProducer
from voltron.producer.generator import Generator
from voltron.producer.parser import Parser
from voltron.mapper.suite import Suite
from voltron.analyzer.analyzer import analyzer
import traceback, sys
from voltron.utils.logger import logger
from dataclasses import asdict

from pathlib import Path

class Mapper:
    """Mapper between actual messages and abstract symbols.
    
    Select generator and parser
    """
    def __init__(
        self,
        producer: AsyncProducer
    ) -> None:
        self.producer = producer
        self.analyzer = analyzer
        self.gs_path = producer.generator_path
        self.ps_path = producer.parser_path
        
        self.request_types: list[str] = producer.req_types
        self.response_types: list[str] = producer.res_types
        
        self.generators: dict[str, list[Generator]] = producer.generators
        # self.cur_suite: Suite = Suite(producer.generators)
        self.parsers: list[Parser] = producer.parsers
        
        self.suits = Suite(self.generators)
        
        self.cur_parser: Parser
        self.equip_parser(self.parsers[-1])
        
        self.message_pool: dict[str, dict[str, bytes]] = {} # store actual message
        
        logger.debug('Mapper: finish init')
    
    def g_path(
        self,
        g: Generator
    ) -> Path:
        return self.gs_path / g.msg_type / f'{g.name}.py'
    
    def p_path(
        self,
        p: Parser
    ) -> Path:
        return self.ps_path / f'{p.name}.py'
        
    def equip_parser(
        self,
        p: Parser
    ) -> None:
        self.cur_parser = p
        
    def select_generators(
        self,
        req_seq: list[str],
        cache_mode: bool = False,
        mode: str = 'default'
    ) -> list[tuple[str, bytes]]:
        """Select and execute message generator based on the list of message type
        
        req_seq: message type list
        cache_mode: cache the generated message and get message from cache (for automata learning)
        
        Return:
            generated message
        """
        ms = []
        for req in req_seq:
            if req == '-':
                continue
            elif req in self.generators.keys():
                g = self.select_generator(req, mode)
                if g.msg_type not in self.message_pool.keys():
                    self.message_pool[g.msg_type] = {}
                try:
                    if cache_mode and g.was_used != 0:
                        msg = self.message_pool[g.msg_type][g.name]
                    else:
                        msg = self.exe_generator(g)
                        if msg:
                            self.message_pool[g.msg_type][g.name] = msg
                            g.was_used += 1
                        else:
                            g.broken = False
                    msg_type = g.msg_type
                    ms.append((msg_type, msg))
                except Exception as e:
                    logger.debug(asdict(g))
                    logger.debug(self.message_pool)
                    logger.debug(traceback.format_exc())
            else:
                logger.debug(f'Mapper: unexpected type {req}')
        return ms
    
    def select_generator(
        self,
        req_type: str,
        mode: str
    ) -> Generator:
        if mode == 'new':
            return self.generators[req_type][-1]
        else:
            return self.generators[req_type][0]
    
    def exe_generator(
        self,
        g: Generator
    ) -> bytes | None:
        name_space = {}
        try:
            with open(self.g_path(g), 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'generate_{g.msg_type}']
                return obj()
        except Exception as e:
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None
            
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
