from collections.abc import Callable
from voltron.producer.AsyncProducer import AsyncProducer
from voltron.producer.generator import Generator
from voltron.producer.parser import Parser
from voltron.mapper.suite import Suite
from voltron.scheduler.automata import MealyMachine
from voltron.analyzer.analyzer import analyzer
import traceback, sys
from voltron.utils.logger import logger
from dataclasses import asdict

from pathlib import Path

class Mapper:
    """Mapper between actual messages and abstract symbols.
    
    Select generator, mutator and parser for symbols
    """
    def __init__(
        self,
        producer: AsyncProducer
    ) -> None:
        self.producer = producer
        self.analyzer = analyzer
        self.gs_path = producer.generator_path
        self.ps_path = producer.parser_path
        self.ms_path = producer.mutator_path
        
        self.request_types: list[str] = producer.req_types
        self.response_types: list[str] = producer.res_types
        
        self.generators: dict[str, list[Generator]] = producer.generators
        self.mutators: dict[str, list[Generator]] = producer.mutators
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
    
    def m_path(
        self,
        m: Generator
    ) -> Path:
        return self.ms_path / m.msg_type / f'{m.name}.py'
        
    def equip_parser(
        self,
        p: Parser
    ) -> None:
        self.cur_parser = p
        
    def select_generators(
        self,
        req_seq: list[str],
        cache_mode: bool = False,
        select_mode: str = 'new'
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
                # ignore empty symbol
                continue
            
            # select normal generator
            elif req in self.generators.keys(): 
                # get generator of according message type
                g = self.select_generator(req, select_mode)
                
                if g.msg_type not in self.message_pool.keys():
                    self.message_pool[g.msg_type] = {}
                    
                try:
                    msg = None
                    if cache_mode and g.was_used != 0:
                        # cache mode to avoid randomness in model learning
                        msg = self.message_pool[g.msg_type][g.name]
                    else:
                        # run generator at first time
                        msg = self.exe_generator(g)
                        if msg:
                            self.message_pool[g.msg_type][g.name] = msg
                            g.was_used += 1
                        else:
                            g.broken = False
                            
                    if msg:
                        msg_type = g.msg_type
                        ms.append((msg_type, msg))
                    else:
                        raise Exception
                except Exception as e:
                    logger.debug(asdict(g))
                    logger.debug(self.message_pool)
                    logger.debug(traceback.format_exc())
                    
            # select mutators
            elif req in self.mutators:
                # get generator of according message type
                m = self.select_mutator(req, select_mode)
                
                if m.msg_type not in self.message_pool.keys():
                    self.message_pool[m.msg_type] = {}
                    
                try:
                    msg = None
                    if cache_mode and m.was_used != 0:
                        # cache mode to avoid randomness in model learning
                        msg = self.message_pool[m.msg_type][m.name]
                    else:
                        # run generator at first time
                        msg = self.exe_mutator(m)
                        if msg:
                            self.message_pool[m.msg_type][m.name] = msg
                            m.was_used += 1
                        else:
                            m.broken = False
                            
                    if msg:
                        msg_type = m.msg_type
                        ms.append((f'{msg_type}[m]', msg))
                    else:
                        raise Exception
                except Exception as e:
                    logger.debug(asdict(m))
                    logger.debug(self.message_pool)
                    logger.debug(traceback.format_exc())
            else:
                logger.debug(f'Mapper: unexpected type {req}')
        return ms
    
    def select_generator(
        self,
        req_type: str,
        mode: str = 'new'
    ) -> Generator:
        if mode == 'new':
            return self.generators[req_type][-1]
        else:
            return self.generators[req_type][0]
        
    def select_mutator(
        self,
        req_type: str,
        mode: str = 'new'
    ) -> Generator:
        if mode == 'new':
            return self.mutators[req_type][-1]
        else:
            return self.mutators[req_type][0]
    
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
            analyzer.stop_event.set()
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None
        
    def exe_mutator(
        self,
        m: Generator
    ) -> bytes | None:
        name_space = {}
        try:
            with open(self.m_path(m), 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'generate_{m.msg_type}']
                return obj()
        except Exception as e:
            analyzer.stop_event.set()
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None
            
    def register_mapper(
        self,
        h: MealyMachine
    ):
        h.map = self.message_pool
