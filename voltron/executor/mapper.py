from collections.abc import Callable
from voltron.synthesizer.synthesizer import AsyncProducer
from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.learner.automata import MealyMachine
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
import multiprocessing as mp
import base64
import hashlib
import json
import time
import traceback
from voltron.utils.logger import logger_fuzz as logger
from dataclasses import asdict, dataclass
import threading
from urllib.parse import quote

from pathlib import Path


EXEC_TIMEOUT_S = 3.0
EXEC_RETRY_LIMIT = 3


@dataclass(frozen=True)
class DynamicExecutionResult:
    status: str
    value: object | None = None
    error: str = ''


class RuntimeComponentRepairError(RuntimeError):
    """A required generated component could not be repaired or rolled back."""


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

        if len(item) == 2:
            code, func_name = item
            args = ()
        else:
            code, func_name, args = item
        cache_key = (func_name, code)
        try:
            func = func_cache.get(cache_key)
            if func is None:
                namespace = {}
                exec(code, namespace)
                func = namespace[func_name]
                func_cache[cache_key] = func

            conn.send(('ok', func(*args)))
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
        self.cs_path = producer.checker_path
        self.os_path = producer.observer_path
        self.legacy_os_path = getattr(
            producer,
            'legacy_observer_path',
            producer.observer_path,
        )
        self.ms_path = producer.mutator_path
        
        self.request_types: set[str] = producer.req_types
        self.response_types: set[str] = producer.res_types
        self.req_dep: dict[str, dict[str, dict]] = producer.req_dep
        
        self.generators: dict[str, list[Generator]] = producer.generators
        self.mutators: dict[str, list[Generator]] = producer.mutators
        # self.cur_suite: Suite = Suite(producer.generators)
        self.parsers: list[Parser] = producer.parsers
        self.checkers: dict[str, list[Checker]] = producer.checkers
        self.observers: dict[str, list[ResponseObserver]] = producer.observers

        self.exec_timeout_s = EXEC_TIMEOUT_S
        self.exec_retry_limit = EXEC_RETRY_LIMIT
        self._dynamic_ctx = mp.get_context('spawn')
        self._dynamic_conn = None
        self._dynamic_proc = None
        self._dynamic_lock = threading.Lock()
        self._runtime_repair_lock = threading.RLock()
        self._runtime_manifest_lock = threading.Lock()
        self._runtime_repair_cache: dict[
            tuple[str, str, str], tuple[object, str] | None
        ] = {}
        self._quarantined_components: set[tuple[str, str, str]] = set()
        self._last_known_good: dict[tuple[str, str], object] = {}
        
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

    def c_path(
        self,
        checker: Checker
    ) -> Path:
        typed_path = (
            self.cs_path
            / quote(checker.msg_type, safe='._-')
            / f'{checker.name}.py'
        )
        if typed_path.is_file():
            return typed_path
        if checker.path:
            return Path(checker.path)
        return typed_path

    def o_path(
        self,
        observer: ResponseObserver
    ) -> Path:
        typed_path = (
            self.os_path
            / quote(observer.msg_type, safe='._-')
            / f'{observer.name}.py'
        )
        if typed_path.is_file():
            return typed_path
        legacy_typed_path = (
            self.legacy_os_path
            / quote(observer.msg_type, safe='._-')
            / f'{observer.name}.py'
        )
        if legacy_typed_path.is_file():
            return legacy_typed_path
        if observer.path:
            return Path(observer.path)
        return typed_path

    def h_path(
        self,
        observer: ResponseObserver
    ) -> Path:
        """Compatibility alias for older call sites."""
        return self.o_path(observer)
    
    def m_path(
        self,
        m: Generator
    ) -> Path:
        return self.ms_path / m.msg_type / f'{m.name}.py'
        
    def equip_parser(
        self
    ) -> Parser:
        return self.parsers[-1]

    def equip_checkers(
        self
    ) -> dict[str, Checker]:
        return {
            msg_type: checkers[-1]
            for msg_type, checkers in self.checkers.items()
            if checkers
        }

    def equip_observers(self) -> dict[str, ResponseObserver]:
        if not getattr(configs, 'observer_enabled', True):
            return {}
        return {
            msg_type: observers[-1]
            for msg_type, observers in self.observers.items()
            if observers
        }
    
    def update_parser(
        self,
        message: bytes
    ) -> Parser:
        if not configs.spec_knowledge:
            return self.cur_parser
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
                except Exception:
                    logger.debug(asdict(g))
                    logger.debug(self.message_pool)
                    logger.exception('Mapper: generator selection failed')
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
            selected = False
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
                        selected = True
                    else:
                        logger.debug(f'Mapper: mutator failed {m.msg_type}/{m.name}')
                except Exception:
                    logger.debug(asdict(m))
                    logger.debug(self.message_pool)
                    logger.exception('Mapper: mutator selection failed')
            if not selected:
                fallback = self.select_generators(
                    [req],
                    cache_mode=False,
                    select_mode=select_mode,
                )
                if fallback:
                    logger.debug(
                        f'Mapper: using generator fallback for mutator {req}'
                    )
                    ms.extend(fallback)
                else:
                    logger.debug(f'Mapper: no mutator or generator for {req}')
        return ms
    
    def select_generator(
        self,
        req_type: str,
        mode: str = 'new'
    ) -> Generator:
        versions = self.generators[req_type]
        if mode == 'new':
            for generator in reversed(versions):
                if not self._component_quarantined(
                    'generator', req_type, generator.name
                ):
                    return generator
            return versions[0]
        return versions[0]
        
    def select_mutator(
        self,
        req_type: str,
        mode: str = 'new'
    ) -> Generator:
        versions = self.mutators[req_type]
        if mode == 'new':
            for mutator in reversed(versions):
                if not self._component_quarantined(
                    'mutator', req_type, mutator.name
                ):
                    return mutator
            return versions[0]
        return versions[0]
    
    def exe_generator(
        self,
        g: Generator
    ) -> bytes | None:
        try:
            with open(self.g_path(g), 'r', encoding='utf-8') as f:
                code = f.read()
            msg = self._execute_message_component(
                'generator', g.msg_type, g, code, 'generate'
            )
            if msg is not None:
                g.was_used += 1
            return msg
        except Exception:
            logger.exception('Mapper: generator execution failed')
            return None
        
    def exe_mutator(
        self,
        m: Generator
    ) -> bytes | None:
        try:
            with open(self.m_path(m), 'r', encoding='utf-8') as f:
                code = f.read()
            return self._execute_message_component(
                'mutator', m.msg_type, m, code, 'mutate'
            )
        except Exception:
            logger.exception('Mapper: mutator execution failed')
            return None

    def _runtime_state(self) -> None:
        if not hasattr(self, '_runtime_repair_lock'):
            self._runtime_repair_lock = threading.RLock()
        if not hasattr(self, '_runtime_manifest_lock'):
            self._runtime_manifest_lock = threading.Lock()
        if not hasattr(self, '_runtime_repair_cache'):
            self._runtime_repair_cache = {}
        if not hasattr(self, '_quarantined_components'):
            self._quarantined_components = set()
        if not hasattr(self, '_last_known_good'):
            self._last_known_good = {}

    def _component_quarantined(
        self,
        component: str,
        component_type: str,
        version: str,
    ) -> bool:
        self._runtime_state()
        return (component, component_type, version) in self._quarantined_components

    @staticmethod
    def _valid_generated_message(value: object) -> bool:
        return (
            isinstance(value, bytes)
            and bool(value)
            and len(value) <= getattr(
                configs, 'generated_message_max_bytes', 1024 * 1024
            )
        )

    def _execute_message_component(
        self,
        component: str,
        component_type: str,
        metadata: Generator,
        code: str,
        function_name: str,
    ) -> bytes | None:
        self._runtime_state()
        result = self._run_dynamic_code_result(code, function_name)
        if result.status == 'ok' and self._valid_generated_message(result.value):
            self._last_known_good[(component, component_type)] = metadata
            return result.value

        error = result.error
        if not error:
            error = (
                'invalid_return: expected non-empty bytes no larger than '
                f'{getattr(configs, "generated_message_max_bytes", 1024 * 1024)}; '
                f'got {type(result.value).__name__}'
            )
        repaired = self.repair_runtime_component(
            component=component,
            component_type=component_type,
            version=metadata.name,
            source_code=code,
            error=error,
        )
        if repaired is not None:
            repaired_metadata, repaired_code = repaired
            replay = self._run_dynamic_code_result(
                repaired_code,
                function_name,
            )
            if replay.status == 'ok' and self._valid_generated_message(
                replay.value
            ):
                self._last_known_good[(component, component_type)] = (
                    repaired_metadata
                )
                return replay.value

        fallback = self._last_known_good.get((component, component_type))
        if fallback is None or fallback is metadata:
            return None
        try:
            path = (
                self.g_path(fallback)
                if component == 'generator'
                else self.m_path(fallback)
            )
            fallback_code = path.read_text(encoding='utf-8')
            fallback_result = self._run_dynamic_code_result(
                fallback_code,
                function_name,
            )
            if (
                fallback_result.status == 'ok'
                and self._valid_generated_message(fallback_result.value)
            ):
                return fallback_result.value
        except Exception:
            logger.exception(
                'Mapper: last-known-good %s fallback failed [%s]',
                component,
                component_type,
            )
        return None

    @staticmethod
    def _runtime_input_record(runtime_input: bytes | None) -> dict | None:
        if runtime_input is None:
            return None
        sample = runtime_input[:4096]
        return {
            'length': len(runtime_input),
            'sha256': hashlib.sha256(runtime_input).hexdigest(),
            'truncated': len(sample) < len(runtime_input),
            'base64': base64.b64encode(sample).decode('ascii'),
            'repr': repr(sample),
        }

    def _append_runtime_record(self, filename: str, record: dict) -> None:
        try:
            path = configs.results_path / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._runtime_manifest_lock:
                with path.open('a', encoding='utf-8') as stream:
                    json.dump(record, stream, ensure_ascii=False)
                    stream.write('\n')
        except Exception:
            logger.exception('Mapper: runtime component manifest write failed')

    def repair_runtime_component(
        self,
        component: str,
        component_type: str,
        version: str,
        source_code: str,
        error: str,
        runtime_input: bytes | None = None,
    ) -> tuple[object, str] | None:
        """Deduplicate a runtime repair and record its complete evidence."""
        self._runtime_state()
        source_sha = hashlib.sha256(source_code.encode('utf-8')).hexdigest()
        normalized_error = error.strip().splitlines()[0][:500]
        fingerprint = hashlib.sha256(
            f'{component}\0{source_sha}\0{normalized_error}'.encode('utf-8')
        ).hexdigest()
        key = (component, source_sha, fingerprint)
        failure_record = {
            'timestamp': time.time(),
            'kind': 'runtime_contract_failure',
            'component': component,
            'component_type': component_type,
            'component_version': version,
            'source_sha256': source_sha,
            'phase': getattr(analyzer, 'stage', ''),
            'error': error[:12000],
            'error_fingerprint': fingerprint,
            'input': self._runtime_input_record(runtime_input),
            'contract': {
                'parser': 'bytes -> bytes (non-empty for triggering input)',
                'generator': '() -> non-empty bytes',
                'mutator': '() -> non-empty bytes',
                'checker': 'bytes -> bool',
                'observer': 'bytes -> lowercase sha256',
            }.get(component, ''),
        }
        self._append_runtime_record(
            'component_runtime_failures.jsonl', failure_record
        )
        self._quarantined_components.add(
            (component, component_type, version)
        )

        with self._runtime_repair_lock:
            if key in self._runtime_repair_cache:
                return self._runtime_repair_cache[key]
            repair = getattr(
                self.producer, 'repair_runtime_component', None
            )
            result = None
            repair_error = ''
            started = time.monotonic()
            try:
                if not callable(repair):
                    raise RuntimeError(
                        'producer does not support runtime component repair'
                    )
                error_with_evidence = (
                    f'{error}\nRuntime trigger evidence: '
                    f'{json.dumps(failure_record["input"], ensure_ascii=False)}'
                )
                result = repair(
                    component=component,
                    component_type=component_type,
                    source_code=source_code,
                    error=error_with_evidence,
                    runtime_input=runtime_input,
                )
            except Exception as exception:
                repair_error = f'{type(exception).__name__}: {exception}'
                logger.exception(
                    'Mapper: runtime %s repair failed [%s]',
                    component,
                    component_type,
                )
            self._runtime_repair_cache[key] = result
            repair_record = {
                'timestamp': time.time(),
                'component': component,
                'component_type': component_type,
                'failed_version': version,
                'source_sha256': source_sha,
                'error_fingerprint': fingerprint,
                'status': 'published' if result is not None else 'failed',
                'replacement_version': (
                    getattr(result[0], 'name', '') if result is not None else ''
                ),
                'attempts': getattr(
                    self.producer, '_last_runtime_repair_attempts', 0
                ),
                'duration_s': time.monotonic() - started,
                'error': repair_error,
            }
            self._append_runtime_record(
                'component_repairs.jsonl', repair_record
            )
            return result

    def _run_dynamic_code(
        self,
        code: str,
        func_name: str,
        args: tuple = (),
    ) -> object | None:
        result = self._run_dynamic_code_result(code, func_name, args)
        return result.value if result.status == 'ok' else None

    def _run_dynamic_code_result(
        self,
        code: str,
        func_name: str,
        args: tuple = (),
    ) -> DynamicExecutionResult:
        with self._dynamic_lock:
            if not self._ensure_dynamic_worker():
                logger.debug(f'Executor: {func_name} worker setup failed')
                return DynamicExecutionResult(
                    'worker_error', error='dynamic worker setup failed'
                )

            conn = self._dynamic_conn
            if conn is None:
                logger.debug(f'Executor: {func_name} worker connection missing')
                return DynamicExecutionResult(
                    'worker_error', error='dynamic worker connection missing'
                )

            try:
                conn.send((code, func_name, args))
            except (BrokenPipeError, EOFError, OSError):
                if not self._restart_dynamic_worker():
                    logger.debug(f'Executor: {func_name} worker restart failed')
                    return DynamicExecutionResult(
                        'worker_error', error='dynamic worker restart failed'
                    )

                conn = self._dynamic_conn
                if conn is None:
                    logger.debug(f'Executor: {func_name} worker connection missing after restart')
                    return DynamicExecutionResult(
                        'worker_error',
                        error='dynamic worker connection missing after restart',
                    )
                conn.send((code, func_name, args))

            if not conn.poll(self.exec_timeout_s):
                logger.debug(f'Executor: {func_name} timeout after {self.exec_timeout_s}s')
                self._restart_dynamic_worker()
                return DynamicExecutionResult(
                    'timeout',
                    error=(
                        f'{func_name} execution timed out after '
                        f'{self.exec_timeout_s}s'
                    ),
                )

            try:
                status, payload = conn.recv()
            except (BrokenPipeError, EOFError, OSError):
                logger.debug(f'Executor: {func_name} worker stopped unexpectedly')
                self._restart_dynamic_worker()
                return DynamicExecutionResult(
                    'worker_error',
                    error=f'{func_name} worker stopped unexpectedly',
                )

        if status == 'ok':
            return DynamicExecutionResult('ok', value=payload)

        logger.debug(f'Executor: {func_name} failure {payload}')
        return DynamicExecutionResult('runtime_error', error=str(payload))

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
