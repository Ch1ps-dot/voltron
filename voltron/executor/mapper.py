from collections.abc import Callable
from voltron.synthesizer.synthesizer import AsyncProducer
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.learner.automata import MealyMachine
from voltron.analyzer.analyzer import analyzer
import multiprocessing as mp
import traceback
from voltron.utils.logger import logger
from dataclasses import asdict
import threading

from pathlib import Path


EXEC_TIMEOUT_S = 3.0
EXEC_RETRY_LIMIT = 3


def _dynamic_code_worker(
    conn
) -> None:
    func_cache = {}

    while True:
        try:
            item = conn.recv()
        except EOFError:
            break

        if item is None:
            break

        code, func_name = item
        cache_key = (func_name, code)
        try:
            func = func_cache.get(cache_key)
            if func is None:
                namespace = {}
                exec(code, namespace)
                func = namespace[func_name]
                func_cache[cache_key] = func

            conn.send(('ok', func()))
        except Exception:
            conn.send(('error', traceback.format_exc()))

    conn.close()

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

        self.exec_timeout_s = EXEC_TIMEOUT_S
        self.exec_retry_limit = EXEC_RETRY_LIMIT
        self._dynamic_ctx = mp.get_context('spawn')
        self._dynamic_conn = None
        self._dynamic_proc = None
        self._dynamic_lock = threading.Lock()
        
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
                    if cache_mode:
                        # cache mode to avoid randomness in model learning
                        msg = self.message_pool[g.msg_type].get(g.name)

                    if msg is None:
                        # run generator with bounded retries so one bad template
                        # cannot stall the entire execution loop.
                        for _ in range(self.exec_retry_limit):
                            msg = self.exe_generator(g)
                            if msg is not None:
                                self.message_pool[g.msg_type][g.name] = msg
                                break

                    if msg is not None:
                        msg_type = g.msg_type
                        ms.append((msg_type, msg))
                    else:
                        logger.debug(f'Mapper: generator failed {g.msg_type}/{g.name}')
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
                    # Bound retries for the same reason as generators.
                    msg = None
                    for _ in range(self.exec_retry_limit):
                        msg = self.exe_mutator(m)
                        if msg is not None:
                            break
                        logger.debug(f'mutator error {req} {m.name}')

                    if msg is not None:
                        msg_type = m.msg_type
                        ms.append((msg_type, msg))
                    else:
                        logger.debug(f'Mapper: mutator failed {m.msg_type}/{m.name}')
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
        try:
            with open(self.g_path(g), 'r', encoding='utf-8') as f:
                code = f.read()
                msg = self._run_dynamic_code(code, 'generate')
                if msg is not None:
                    g.was_used += 1
                return msg
        except Exception as e:
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None
        
    def exe_mutator(
        self,
        m: Generator
    ) -> bytes | None:
        try:
            with open(self.m_path(m), 'r', encoding='utf-8') as f:
                code = f.read()
                return self._run_dynamic_code(code, 'mutate')
        except Exception as e:
            logger.debug(f'Executor: generated failure {e}')
            logger.debug(traceback.format_exc())
            return None

    def _run_dynamic_code(
        self,
        code: str,
        func_name: str
    ) -> bytes | None:
        with self._dynamic_lock:
            if not self._ensure_dynamic_worker():
                logger.debug(f'Executor: {func_name} worker setup failed')
                return None

            conn = self._dynamic_conn
            if conn is None:
                logger.debug(f'Executor: {func_name} worker connection missing')
                return None

            try:
                conn.send((code, func_name))
            except (BrokenPipeError, EOFError, OSError):
                if not self._restart_dynamic_worker():
                    logger.debug(f'Executor: {func_name} worker restart failed')
                    return None

                conn = self._dynamic_conn
                if conn is None:
                    logger.debug(f'Executor: {func_name} worker connection missing after restart')
                    return None
                conn.send((code, func_name))

            if not conn.poll(self.exec_timeout_s):
                logger.debug(f'Executor: {func_name} timeout after {self.exec_timeout_s}s')
                self._restart_dynamic_worker()
                return None

            try:
                status, payload = conn.recv()
            except (BrokenPipeError, EOFError, OSError):
                logger.debug(f'Executor: {func_name} worker stopped unexpectedly')
                self._restart_dynamic_worker()
                return None

        if status == 'ok':
            return payload

        logger.debug(f'Executor: {func_name} failure {payload}')
        return None

    def _ensure_dynamic_worker(
        self
    ) -> bool:
        if self._dynamic_proc is not None and self._dynamic_proc.is_alive():
            return self._dynamic_conn is not None

        return self._start_dynamic_worker()

    def _start_dynamic_worker(
        self
    ) -> bool:
        parent_conn = None
        child_conn = None
        try:
            parent_conn, child_conn = self._dynamic_ctx.Pipe()
            proc = self._dynamic_ctx.Process(
                target=_dynamic_code_worker,
                args=(child_conn,),
                daemon=True,
            )
            proc.start()
            child_conn.close()
            self._dynamic_conn = parent_conn
            self._dynamic_proc = proc
            return True
        except Exception as err:
            logger.debug(f'Executor: dynamic worker start failure {err}')
            for conn in (parent_conn, child_conn):
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self._dynamic_conn = None
            self._dynamic_proc = None
            return False

    def _restart_dynamic_worker(
        self
    ) -> bool:
        self._stop_dynamic_worker()
        return self._start_dynamic_worker()

    def _stop_dynamic_worker(
        self
    ) -> None:
        conn = getattr(self, '_dynamic_conn', None)
        proc = getattr(self, '_dynamic_proc', None)
        self._dynamic_conn = None
        self._dynamic_proc = None

        if conn is not None:
            try:
                conn.send(None)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        if proc is not None:
            proc.join(timeout=0.2)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)

    def close(
        self
    ) -> None:
        with self._dynamic_lock:
            self._stop_dynamic_worker()

    def __del__(
        self
    ) -> None:
        self._stop_dynamic_worker()
                
            
    def register_mapper(
        self,
        h: MealyMachine
    ):
        h.map = self.message_pool
