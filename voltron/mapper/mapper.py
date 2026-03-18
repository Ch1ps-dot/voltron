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
import threading

from pathlib import Path

class Mapper:
    """Mapper between actual messages and abstract symbols.
    
    Select generator, mutator and parser for symbols
    
    Attributes:
        producer: AsyncProducer
        analyzer: Analyzer
        gs_path: Path of generator code
        ps_path: Path of parser code
        ms_path: Path of mutator code
        request_types: set of message types for request
        response_types: set of message types for response
        req_dep: dependency between message types
        generators: dict of message type to list of generators
        mutators: dict of message type to list of mutators
        parsers: list of parsers
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
        
        self.request_types: set[str] = producer.req_types
        self.response_types: set[str] = producer.res_types
        self.req_dep: dict[str, dict[str, dict]] = producer.req_dep
        
        self.generators: dict[str, list[Generator]] = producer.generators
        self.mutators: dict[str, list[Generator]] = producer.mutators
        # self.cur_suite: Suite = Suite(producer.generators)
        self.parsers: list[Parser] = producer.parsers
        
        self.suits = Suite(self.generators)
        
        self.cur_parser: Parser  = self.equip_parser()
        
        
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
        self
    ) -> Parser:
        return self.parsers[-1]
    
    def update_parser(
        self,
        message: bytes
    ) -> Parser:
        self.producer.parser_evo(message)
        self.cur_parser = self.equip_parser()
        return self.cur_parser
        
    def select_generators(
        self,
        req_seq: list[str],
        cache_mode: bool = False,
        select_mode: str = 'new'
    ) -> list[tuple[str, bytes]]:
        """Select and execute message generator based on the list of message type
        
        req_seq: message type list
        cache_mode: cache the generated message and get message from cache (for automata learning)
        select_mode: select generator in 'new' or 'old' mode
        
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
                self.message_pool.setdefault(g.msg_type, {})
                    
                try:
                    msg = None
                    if cache_mode and g.was_used != 0:
                        # cache mode to avoid randomness in model learning
                        msg = self.message_pool[g.msg_type][g.name]
                    else:
                        # run generator and cache the generated message in pool
                        # sometimes the generator code may raise exception and return none,
                        # we run generator until the results can be used.
                        msg = self.exe_generator(g)
                        while msg == None:
                            msg = self.exe_generator(g)
                        self.message_pool[g.msg_type][g.name] = msg
                            
                    if msg:
                        msg_type = g.msg_type
                        ms.append((msg_type, msg))
                    else:
                        raise Exception
                except Exception as e:
                    logger.debug(asdict(g))
                    logger.debug(self.message_pool)
                    logger.debug(traceback.format_exc())
            else:
                logger.debug(f'Mapper: unexpected type {req}')
        return ms
    
    def select_mutators(
        self,
        req_seq: list[str],
        select_mode = 'new'
    ) -> list[tuple[str, bytes]]:
        """Select and execute message mutator based on the list of message type
        
        req_seq: message type list
        select_mode: select mutator in 'new' or 'old' mode
        
        return:
            mutated messages
        """
        ms = []
        for req in req_seq:
            if req in self.mutators:
                # get generator of according message type
                m = self.select_mutator(req, select_mode)
                
                self.message_pool.setdefault(m.msg_type, {})
                    
                try:
                    # sometimes the generator code may raise exception and return none,
                    # we run generator until the results can be used.
                    msg = self.exe_mutator(m)
                    msg_type = m.msg_type
                    while msg == None:
                        msg = self.exe_mutator(m)
                        logger.debug(f'mutator error {req} {m.name}')
                    ms.append((msg_type, msg))
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
                g.was_used += 1
                return obj()
                # result = []
                # def thread_task():
                #     res = obj()
                #     result.append(res)
                    
                # t = threading.Thread(target=thread_task)
                # t.start()
                # t.join(timeout=3)
                # return result[0]
        except Exception as e:
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
                mutate = name_space[f'mutate_{m.msg_type}']
                # havoc = name_space[f'havoc_{m.msg_type}']
                return mutate()
        except Exception as e:
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None
                
            
    def register_mapper(
        self,
        h: MealyMachine
    ):
        h.map = self.message_pool
