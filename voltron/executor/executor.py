import subprocess
from pathlib import Path
import time, select, socket, pickle, json, base64, hashlib, asyncio, ast
from typing import Callable, Tuple

from voltron.configs import configs
from voltron.utils.logger import (
    format_boundary,
    format_event,
    logger_fuzz as logger,
)
from voltron.executor.mapper import Mapper
from voltron.synthesizer.synthesizer import Generator, Parser
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.analyzer.analyzer import analyzer
from voltron.executor.conversation import Conversation
from voltron.executor.pair_recorder import RequestResponsePairRecorder
from voltron.executor.sut_monitor import (
    CRASHED,
    EXITED,
    RUNNING,
    UNREACHABLE,
    RemoteSUTProcess,
    build_sut_monitor,
)
import math, statistics, threading, sys, os, signal, re

CRASH_SIGNALS = {-6, -11, -4, -8}
CRASH_EXIT_CODES = {128 + abs(sig) for sig in CRASH_SIGNALS}
ASAN_CRASH_MARKERS = (
    'ERROR: AddressSanitizer',
    'AddressSanitizer:',
    'SUMMARY: AddressSanitizer',
    'LeakSanitizer',
    'UndefinedBehaviorSanitizer',
    'Sanitizer CHECK failed',
    'DEADLYSIGNAL',
)
RUNTIME_EXCEPTION_PATTERNS = (
    # Python
    re.compile(r'Traceback \(most recent call last\):', re.IGNORECASE),
    re.compile(r'Fatal Python error:', re.IGNORECASE),
    re.compile(r'unhandled exception in (?:asyncio|thread)', re.IGNORECASE),
    # Java and other JVM languages
    re.compile(r'Exception in thread "[^"]+"', re.IGNORECASE),
    re.compile(
        r'A fatal error has been detected by the Java Runtime Environment',
        re.IGNORECASE,
    ),
    re.compile(r'Internal Error \(.*\), pid=\d+, tid=\d+', re.IGNORECASE),
    # .NET and Mono (C#, F#, VB.NET)
    re.compile(r'(?:^|\n)\s*Unhandled exception\.', re.IGNORECASE),
    re.compile(r'(?:^|\n)\s*Unhandled Exception:', re.IGNORECASE),
    re.compile(r'FATAL UNHANDLED EXCEPTION:', re.IGNORECASE),
    # Other managed runtimes with equivalent uncaught-failure behavior
    re.compile(r'(?:^|\n)\s*panic:', re.IGNORECASE),
    re.compile(r"thread '[^']+' panicked at", re.IGNORECASE),
    re.compile(r'(?:uncaught exception|uncaught \w*error)', re.IGNORECASE),
    re.compile(r'PHP Fatal error:', re.IGNORECASE),
)

class Executor:
    """Executor for interacting with the SUT, sending requests and receiving responses, and recording the conversation.
    
    Attributes:
        pre_script: A Path object representing the script to be executed before interacting with the SUT, used for setup.
        post_script: A Path object representing the script to be executed after interacting with the SUT, used for cleanup.
        cmdline: A list of strings representing the command line arguments to execute the SUT.
        host: The hostname or IP address of the SUT to connect to.
        port: The port number on which the SUT is listening for connections.
    """
    def __init__(
            self,
            mapper: Mapper,
            stop_event: threading.Event,
            cmdline: list[str],
            setup_time_s:float = 0.1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.run_script: Path = configs.run_script
        self.setup_script: Path = configs.setup_script
        self.cmdline: list[str] = cmdline
        self.host = configs.host
        self.port = configs.port
        self.trans_layer = configs.trans_layer
        # Kamailio's SIP seeds advertise 127.0.0.1:5061 in Via/Contact.
        # Bind the UDP client socket to that port so replies return to the
        # executor instead of being sent to an unrelated ephemeral port.
        self.local_port = (
            5061
            if self.trans_layer == 'udp'
            and getattr(configs, 'target_name', '') == 'kamailio'
            else None
        )
        self.sut_deployment = getattr(configs, 'sut_deployment', 'local')
        self.sut_monitor = build_sut_monitor(configs)
        self.try_times_parser = 2

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        self.max_timeout_ms = 3000
        self.probe_times = 5 # for estimating suitable response time
        self.probe_recv_time_s = []
       
        self.mapper = mapper # mapper between symbol and message
        self.analyzer = analyzer # runtime analyzer
        self.crash_testcases: dict[str, list[bytes]] = {}
        self.unable_parse_request: set[str] = set()
        self._saved_seed_digests: set[str] = set()
        self._saved_seed_lock = threading.Lock()
        self.pair_recorder = RequestResponsePairRecorder(configs.results_path)

        self.parser_func: Callable
        self.load_parser(self.mapper.cur_parser)
        self.checker_funcs: dict[str, Callable[[bytes], bool]] = {}
        self.observer_funcs: dict[str, Callable[[bytes], str]] = {}
        self.observer_sources: dict[str, tuple[str, str]] = {}
        if configs.fuzz_mode != 'replay':
            self.load_checkers(self.mapper.equip_checkers())
            self.load_observers(self.mapper.equip_observers())
        self.checked_request_response_pairs: set[
            tuple[str, str, str]
        ] = set()
        self.reviewed_invalid_responses: set[tuple[str, str, str]] = set()
        self.checked_response_samples: dict[
            tuple[str, str, str], bytes
        ] = {}
        self.reviewed_response_samples: dict[
            tuple[str, str, str], bytes
        ] = {}
        self.observer_evolution_failures: set[tuple[str, ...]] = set()
        self.observer_semantic_reviews: dict[
            tuple[str, str, str], bool
        ] = {}
        self._invalid_response_lock = threading.Lock()
        self.stop_event = stop_event
            
    def cov_setup(
        self,
        folder: Path,
        cov_file: Path
    ):
        try:
            proc = subprocess.Popen(
                [configs.cov_setup_path, str(folder), str(cov_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate()
            logger.debug(f'cov setup: {proc.returncode} {str(stdout)} {str(stderr)}')
            return proc
        except Exception as e:
            logger.debug(f'[SUT Setup Failure]: {e}')
            return None
    
    def cov_collect(
        self,
        folder: Path,
        cov_file: Path,
        file_path: Path
    ):
        try:
            proc = subprocess.Popen(
                [configs.cov_collect_path, str(folder), str(cov_file), str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()
            logger.debug(f'cov collect: {proc.returncode} {str(stdout)} {str(stderr)}')
            return proc
        except Exception as e:
            logger.debug(f'[SUT Setup Failure]: {e}')
            return None

    def setup_exe(
            self
    ) -> subprocess.Popen | None:
        if (self.setup_script.is_file() and configs.fuzz_mode != 'replay'):
            try:
                proc = subprocess.Popen(
                    [self.setup_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return proc
            except Exception as e:
                logger.debug(f'[SUT clean Failure]: {e}')
                return None
        else:
            return None

    def run_exe(
        self
    ) -> subprocess.Popen | None:
        if not self.run_script.is_file():
            logger.debug(
                'Executor: SUT launch failed before Popen: '
                f'run script does not exist or is not a file; '
                f'script={self.run_script}'
            )
            return None

        fuzz_mode = getattr(configs, 'fuzz_mode', '')
        server_mode = getattr(configs, 'server', None)
        if fuzz_mode != 'replay' and server_mode not in {'parent', 'child'}:
            logger.debug(
                'Executor: SUT launch failed before Popen: '
                f'unsupported server mode={server_mode!r}; '
                f'script={self.run_script}'
            )
            return None

        try:
            proc = subprocess.Popen(
                [self.run_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            analyzer.sut_proc = proc
            logger.debug(
                f'Executor: launched SUT pid={proc.pid} '
                f'script={self.run_script}'
            )
            return proc
        except Exception as e:
            logger.debug(
                'Executor: SUT launch failed during Popen: '
                f'script={self.run_script}; '
                f'executable={os.access(self.run_script, os.X_OK)}; '
                f'exception={type(e).__name__}: {e}'
            )
            return None

    def _log_sut_start_failure(
        self,
        proc: subprocess.Popen | None,
        stage: str,
        attempt: int | None = None,
        detail: str = ''
    ) -> None:
        """Record the available reason for a SUT startup failure."""
        fields = [
            'Executor: SUT startup failure',
            f'stage={stage}',
            f'script={self.run_script}',
            f'transport={self.trans_layer}',
            f'endpoint={getattr(self, "host", "localhost")}:{self.port}',
        ]
        if attempt is not None:
            fields.append(f'attempt={attempt}')
        if detail:
            fields.append(f'detail={detail}')

        if proc is None:
            fields.append('process=not-created')
        else:
            return_code = proc.poll()
            fields.append(f'pid={proc.pid}')
            fields.append(
                'process=running'
                if return_code is None
                else f'returncode={return_code}'
            )
            if return_code is not None:
                stdout, stderr = self._read_process_output(proc)
                if stdout:
                    fields.append(f'stdout={stdout.strip()!r}')
                if stderr:
                    fields.append(f'stderr={stderr.strip()!r}')
                if not stdout and not stderr:
                    fields.append('output=<empty>')

        logger.debug('; '.join(fields))

    def _is_remote_deployment(
        self
    ) -> bool:
        return getattr(self, 'sut_deployment', 'local') == 'remote'

    def _monitor(
        self
    ):
        monitor = getattr(self, 'sut_monitor', None)
        if monitor is None:
            self.sut_monitor = build_sut_monitor(configs)
            monitor = self.sut_monitor
        return monitor

    def _remote_status_summary(
        self
    ) -> str:
        status = self._monitor().status()
        fields = [
            f'remote_state={status.state}',
            f'returncode={status.returncode}',
            f'process_running={status.process_running}',
            f'port_listening={status.port_listening}',
        ]
        if status.detail:
            fields.append(f'detail={status.detail}')
        return '; '.join(fields)

    def interact(
        self,
        msg_seq: list[tuple[str, bytes]],
        poll_wait_ms: int = 5000,
        run_checker: bool = False
    ) -> Tuple[bool, Conversation | None]:
        """Log one complete interaction and execute it against the SUT."""
        interaction_id = f'{time.monotonic_ns():x}'
        request_types = '/'.join(
            msg_type
            for msg_type, _ in msg_seq
        ) or '-'
        started_at = time.perf_counter()
        result: Tuple[bool, Conversation | None] | None = None
        outcome = 'exception'
        error_type = None

        logger.debug(format_boundary(
            'interact.begin',
            interaction_id=interaction_id,
            request_count=len(msg_seq),
            request_types=request_types,
            poll_wait_ms=poll_wait_ms,
            checker_enabled=run_checker,
            mode=getattr(configs, 'fuzz_mode', ''),
            endpoint=(
                f'{getattr(self, "host", "?")}:'
                f'{getattr(self, "port", "?")}'
            ),
        ))
        try:
            result = self._interact_once(
                msg_seq,
                poll_wait_ms=poll_wait_ms,
                run_checker=run_checker,
            )
            flag, conversation = result
            pair_recorder = getattr(self, 'pair_recorder', None)
            if flag and conversation is not None and pair_recorder is not None:
                pair_recorder.observe(
                    conversation,
                    phase=getattr(self.analyzer, 'active_phase', None)
                    or getattr(self.analyzer, 'stage', ''),
                )
            if flag:
                outcome = 'completed'
            elif self.stop_event.is_set():
                outcome = 'stopped'
            else:
                outcome = 'failed'
            return result
        except BaseException as error:
            error_type = type(error).__name__
            outcome = (
                'interrupted'
                if isinstance(error, (KeyboardInterrupt, SystemExit))
                else 'exception'
            )
            raise
        finally:
            conversation = result[1] if result is not None else None
            logger.debug(format_boundary(
                'interact.end',
                interaction_id=interaction_id,
                outcome=outcome,
                duration_ms=round(
                    (time.perf_counter() - started_at) * 1000,
                    3,
                ),
                recorded_exchanges=(
                    len(conversation.content)
                    if conversation is not None
                    else 0
                ),
                response_types=(
                    '/'.join(conversation.res_seq)
                    if conversation is not None
                    else '-'
                ),
                error_type=error_type,
            ))

    def _interact_once(
        self,
        msg_seq: list[tuple[str, bytes]],
        poll_wait_ms: int = 5000,
        run_checker: bool = False
    ) -> Tuple[bool, Conversation | None] :  
        """Interact with the SUT by sending a sequence of messages and receiving the corresponding responses, while recording the conversation.
        
        Args:
            msg_seq: A list of tuples, where each tuple contains a string representing the message type and a bytes object representing the message content to be sent to the SUT.
            poll_wait_ms: An integer representing the maximum time in milliseconds to wait for a response from the SUT after sending each message.
            run_checker: Enable response conformance checking. This is only
                enabled by the fuzzing scheduler, not model learning or replay.
        """
        # logger.debug('exe: begin inter')
        # prepare some settings and setup SUT
        remote_deployment = self._is_remote_deployment()
        if self.stop_event.is_set():
            return False, None
        clean = None
        proc = None
        if remote_deployment:
            self._monitor().start()
        else:
            self.kill_listeners(self.port)
            if self.stop_event.is_set():
                return False, None
            clean = self.setup_exe()
            if self.stop_event.is_set():
                if clean is not None:
                    self._terminate_process_group(
                        clean,
                        signal.SIGKILL,
                        timeout=1,
                    )
                return False, None
            proc = self.run_exe()
        
        
        # if proc is None:
        #     logger.debug(f'Executor: SUT Setup Failure')
        #     return False, None
        
        # if proc.poll() is not None: 
        #     logger.debug(f'Executor: SUT Setup Failure: {proc.returncode}')
        #     return False, None
        
        # avoid unexceptional crash of target
        if not remote_deployment:
            for attempt in range(1, 101):
                if self.stop_event.is_set():
                    self._terminate_process_group(
                        proc,
                        signal.SIGTERM,
                        timeout=1,
                    )
                    return False, None
                if proc is not None and proc.poll() is not None:
                    self._log_sut_start_failure(
                        proc,
                        stage='process-exited-before-ready-check',
                        attempt=attempt,
                    )
                    if self.stop_event.wait(self.setup_time_s):
                        return False, None
                    proc = self.run_exe()
                else:
                    break

            if proc is None:
                self._log_sut_start_failure(
                    proc,
                    stage='process-launch-retries',
                    detail='run_exe returned no process',
                )
                raise Exception('Execute: process close')
            if proc.poll() is not None:
                self._log_sut_start_failure(
                    proc,
                    stage='process-launch-retries',
                    detail='process still exited after launch retries',
                )
                raise Exception('Execute: process close')
        
        # wait for server setup
        sock = None
        for attempt in range(1, 101):
            if self.stop_event.wait(self.setup_time_s):
                if not remote_deployment:
                    self._terminate_process_group(
                        proc,
                        signal.SIGTERM,
                        timeout=1,
                    )
                return False, None
            sock = self.setup_socket()
            if sock == None:
                if remote_deployment:
                    status = self._monitor().status()
                    logger.debug(
                        'Executor: remote SUT not ready; '
                        f'attempt={attempt}; state={status.state}; '
                        f'process_running={status.process_running}; '
                        f'port_listening={status.port_listening}'
                    )
                    if status.state in {EXITED, CRASHED}:
                        self._log_sut_start_failure(
                            proc,
                            stage='remote-readiness-check',
                            attempt=attempt,
                            detail=self._remote_status_summary(),
                        )
                        raise Exception('Execute: remote process close')
                elif proc != None and proc.poll() is not None:
                    self._log_sut_start_failure(
                        proc,
                        stage='socket-readiness-check',
                        attempt=attempt,
                        detail='process exited before socket became ready',
                    )
                    if self.stop_event.is_set():
                        return False, None
                    proc = self.run_exe()
                    if self.stop_event.is_set():
                        self._terminate_process_group(
                            proc,
                            signal.SIGTERM,
                            timeout=1,
                        )
                        return False, None
                    self.kill_listeners(self.port)
                continue
            else:
                break
            
        if not remote_deployment and proc is None:
            self._log_sut_start_failure(
                proc,
                stage='socket-readiness-check',
                detail='restart returned no process',
            )
            raise Exception('Executor: process close')
        if not remote_deployment and proc.poll() is not None:
            self._log_sut_start_failure(
                proc,
                stage='socket-readiness-check',
                detail='process exited after socket readiness attempts',
            )
            raise Exception('Execute: process close')
            
        if sock == None:
            self._log_sut_start_failure(
                proc,
                stage='socket-readiness-timeout',
                attempt=100,
                detail=(
                    f'service did not become reachable within '
                    f'{100 * self.setup_time_s:.2f}s'
                    + (
                        f'; {self._remote_status_summary()}'
                        if remote_deployment
                        else ''
                    )
                ),
            )
            self.stop_event.set()
            sys.exit(0)
        
        
        logger.debug(">>>Executor: interact start")
        # keep request and response in Conversation
        cons: Conversation = Conversation()
        
        # maybe recv initialize message
        resp_code, resp_data = self.net_recv(
            sock=sock,
            poll_timeout_ms=100,
            show_fuzz_ui=run_checker,
        )
        if self.stop_event.is_set():
            sock.close()
            if remote_deployment:
                self._monitor().stop()
            else:
                self._terminate_process_group(
                    proc,
                    signal.SIGTERM,
                    timeout=1,
                )
            return False, None
        last_recv = '-'
        if(resp_code and resp_data):
            is_valid_response = self.check_response_during_fuzzing(
                '-',
                resp_code,
                resp_data,
                run_checker,
            )
            cons.add_state('-', resp_code)
            cons.add_data(bytes(), resp_data)
            if not is_valid_response:
                self.handle_nonconforming_response(cons, resp_code)
            last_recv = resp_code
            with self.analyzer.lock:
                self.analyzer.res_types_update(resp_code)
                self.analyzer.resp_trans_update(f'-/{resp_code}')
        else:
            cons.add_state('-', '-')
            cons.add_data(bytes(), bytes())

        # send the message sequence and parse the response, record the conversation in cons
        last_msg_type = '-'
        last_msg = bytes()
        last_request_recorded = True
        for msg_type, msg in msg_seq:
            if self.stop_event.is_set():
                break
            
            if not remote_deployment and proc.poll() is not None:
                if not self._handle_crash_if_detected(
                    cons,
                    proc,
                    last_msg_type,
                    last_msg,
                    request_recorded=last_request_recorded,
                ):
                    cons.add_state(msg_type, 'CLOSED')
                    cons.add_data(msg or bytes(), bytes())
                    logger.debug('server close')
                break

            last_msg_type = msg_type
            last_msg = msg if msg is not None else bytes()
            
            # send message and parse response
            if msg == None:
                return False, None
            
            flag, req_data = self.net_send(msg, sock)
            
            # success to send
            if(flag and req_data):
                last_request_recorded = False
                logger.debug(format_event(
                    'network.send',
                    request_type=msg_type,
                    length=len(req_data),
                    data=req_data,
                ))
                with self.analyzer.lock:
                    self.analyzer.req_num = self.analyzer.req_num + 1
                    self.analyzer.req_types_update(msg_type)
                resp_code, resp_data = self.net_recv(
                    sock=sock,
                    poll_timeout_ms=poll_wait_ms,
                    msg_type=msg_type,
                    show_fuzz_ui=run_checker,
                )

                if resp_code == 'POLLERR':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'POLLERR')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- POLLERR')
                        last_request_recorded = True
                    break
                
                elif resp_code == 'TIMEOUT':
                    # crash
                    # noraml
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'TIMEOUT')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.timeout_num += 1
                        logger.debug(f'recv <- TIMEOUT')
                        last_request_recorded = True
                    break
                
                elif resp_code == 'RCLOSED':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(
                        cons,
                        proc,
                        msg_type,
                        msg,
                        request_recorded=False,
                    ):
                        cons.add_state(msg_type, 'CLOSED')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- rclose')
                        last_request_recorded = True
                    break
                
                else:
                    if(resp_code == None):
                        logger.debug('Executor: parse error')
                        continue

                    is_valid_response = True
                    if resp_data is not None:
                        is_valid_response = self.check_response_during_fuzzing(
                            msg_type,
                            resp_code,
                            resp_data,
                            run_checker,
                        )
                    
                    with self.analyzer.lock:
                        self.analyzer.res_num += 1
                        self.analyzer.res_types_update(resp_code)
                        self.analyzer.resp_trans_update(f'{last_recv}/{resp_code}')
                    last_recv = resp_code
                    logger.debug(format_event(
                        'network.receive',
                        request_type=msg_type,
                        response_type=resp_code,
                        length=(
                            len(resp_data)
                            if resp_data is not None
                            else 0
                        ),
                        data=resp_data,
                    ))
                    
                    # record conversation data
                    if req_data is not None:
                        cons.add_data(req_data, resp_data or bytes())
                    cons.add_state(msg_type, resp_code)
                    last_request_recorded = True
                    if not is_valid_response:
                        self.handle_nonconforming_response(cons, resp_code)
            
            # If socket closed, stop sending
            else:
                return_code = proc.poll() if proc is not None else None
                
                # program exited unexpectly
                self._handle_crash_if_detected(
                    cons,
                    proc,
                    msg_type,
                    msg,
                    request_recorded=False,
                )
                        
                seq = '/'.join([msg_type for msg_type, data in msg_seq])
                logger.debug(f'Executor: socket closed with {return_code} because of {seq}')
                break

        with self.analyzer.lock:
            self.analyzer.path_num = self.analyzer.path_num + 1

        # close socket
        try:
            sock.close()
        except Exception as e:
            logger.debug(f'socket close error: {e}')
        
        self._handle_crash_if_detected(
            cons,
            proc,
            last_msg_type,
            last_msg,
            request_recorded=last_request_recorded,
        )
        
        # close process
        close_signal = (
            signal.SIGUSR1
            if getattr(configs, 'fuzz_mode', '') == 'replay'
            else signal.SIGTERM
        )
        if remote_deployment:
            self._monitor().stop()
        else:
            self._terminate_process_group(proc, close_signal, timeout=3)
        analyzer.sut_proc = None
        
        # ensure sub-subprocess die
        # if proc.poll is None:
        #     while True:
        #         try:
        #             os.killpg(proc.pid, 0)
        #             # no die, just kill
        #             time.sleep(0.1)
        #             os.killpg(proc.pid, signal.SIGKILL)
        #             logger.debug(f'try to kill: {proc.pid}')
        #         except Exception as e:
        #             # sub-subprocess die out
        #             analyzer.sut_proc = None
        #             logger.debug(f'target process: {e}')
        #             break
        
        # kill clean script
        if clean != None and not remote_deployment:
            self._terminate_process_group(clean, signal.SIGKILL, timeout=1)
                

        # self.post_exe()
        logger.debug("<<<Executor: interact done")
        return True, cons

    def _terminate_process_group(
        self,
        proc: subprocess.Popen | None,
        sig: signal.Signals,
        timeout: float
    ) -> None:
        """Terminate a SUT process tree that was started with start_new_session."""
        if proc is None:
            return
        try:
            if proc.poll() is None:
                os.killpg(proc.pid, sig)
                returncode = proc.wait(timeout=timeout)
                logger.debug(f'close process group [returncode: {returncode} pid: {proc.pid}]')
                return
        except subprocess.TimeoutExpired:
            logger.debug(f'process group did not stop after {sig.name}: {proc.pid}')
        except ProcessLookupError:
            logger.debug(f'process group already closed: {proc.pid}')
            return
        except Exception as err:
            logger.debug(f'process group close err: {err}')

        try:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                returncode = proc.wait(timeout=1)
                logger.debug(f'killed process group [returncode: {returncode} pid: {proc.pid}]')
        except Exception as err:
            logger.debug(f'process group kill err: {err}')
    
    def kill_listeners(
        self,
        port: int
    ) -> None:
        """Kill processes listening on exactly the requested TCP/UDP port."""
        pids, listeners_found = self._find_listener_pids(port)
        if not listeners_found:
            return
        if not pids:
            logger.debug(
                'Executor: listener found but PID is unavailable; '
                f'port={port}; check process visibility and privileges'
            )
            return

        for pid in sorted(pids):
            if pid <= 1 or pid == os.getpid():
                logger.debug(
                    'Executor: refusing to kill unsafe listener PID; '
                    f'port={port}; pid={pid}'
                )
                continue

            try:
                logger.debug(
                    f'Executor: killing listener port={port}; pid={pid}'
                )
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                logger.debug(
                    'Executor: listener exited before kill; '
                    f'port={port}; pid={pid}'
                )
                continue
            except PermissionError as e:
                logger.debug(
                    'Executor: permission denied while killing listener; '
                    f'port={port}; pid={pid}; error={e}'
                )
                continue
            except Exception as e:
                logger.debug(
                    'Executor: failed to kill listener; '
                    f'port={port}; pid={pid}; '
                    f'exception={type(e).__name__}: {e}'
                )
                continue

            if self._wait_for_process_exit(pid, timeout=0.5):
                logger.debug(
                    f'Executor: listener stopped port={port}; pid={pid}'
                )
            else:
                logger.debug(
                    'Executor: listener still exists after SIGKILL; '
                    f'port={port}; pid={pid}; '
                    'possible uninterruptible sleep or PID visibility issue'
                )

        remaining_pids, remaining_found = self._find_listener_pids(port)
        if remaining_found:
            logger.debug(
                'Executor: port remains occupied after listener cleanup; '
                f'port={port}; '
                f'pids={sorted(remaining_pids) if remaining_pids else "hidden"}; '
                'the service may be supervised or automatically restarted'
            )

    def _find_listener_pids(
        self,
        port: int
    ) -> tuple[set[int], bool]:
        """Find listener PIDs with ss, falling back to netstat."""
        commands = (
            ('ss', ['ss', '-H', '-ltnup']),
            ('netstat', ['netstat', '-tulnp']),
        )
        failures = []

        for tool, command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError:
                failures.append(f'{tool}=not-found')
                continue
            except Exception as e:
                failures.append(
                    f'{tool}={type(e).__name__}: {e}'
                )
                continue

            if result.returncode != 0:
                reason = result.stderr.strip() or result.stdout.strip()
                failures.append(
                    f'{tool}=exit-{result.returncode}: '
                    f'{reason or "no diagnostic output"}'
                )
                continue
            if result.stderr.strip() and not result.stdout.strip():
                failures.append(
                    f'{tool}=no-output: {result.stderr.strip()}'
                )
                continue

            pids, listeners_found = self._parse_listener_output(
                result.stdout,
                port,
                tool,
            )
            if listeners_found and not pids:
                diagnostic = result.stderr.strip()
                if diagnostic:
                    logger.debug(
                        'Executor: listener query could not expose PID; '
                        f'tool={tool}; port={port}; '
                        f'diagnostic={diagnostic!r}'
                    )
            return pids, listeners_found

        logger.debug(
            'Executor: unable to inspect port listeners; '
            f'port={port}; reasons={"; ".join(failures)}'
        )
        return set(), False

    def _parse_listener_output(
        self,
        output: str,
        port: int,
        tool: str
    ) -> tuple[set[int], bool]:
        """Parse only lines whose local endpoint exactly matches port."""
        pids: set[int] = set()
        listeners_found = False

        for line in output.splitlines():
            tokens = line.split()
            local_index = 4 if tool == 'ss' else 3
            if len(tokens) <= local_index:
                continue
            local_endpoint = tokens[local_index].rstrip(',')
            port_match = re.search(r':(\d+)$', local_endpoint)
            if port_match is None or int(port_match.group(1)) != port:
                continue

            listeners_found = True
            if tool == 'ss':
                pids.update(
                    int(pid)
                    for pid in re.findall(r'\bpid=(\d+)', line)
                )
            elif tool == 'netstat':
                pids.update(
                    int(pid)
                    for pid in re.findall(r'\b(\d+)/[^\s]+', line)
                )

        return pids, listeners_found

    def _wait_for_process_exit(
        self,
        pid: int,
        timeout: float
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            time.sleep(0.02)

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False
        
    def setup_socket(
        self
    ) -> socket.socket | None:
            """Setup the socket for network communication

            Returns:
                socket for sending and receiving
            """
            sock: socket.socket
            
            try:
                if (self.trans_layer == 'tcp'):
                    sock = socket.create_connection((self.host, self.port))
                elif (self.trans_layer == 'udp'):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    if self.local_port is not None:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind((self.host, self.local_port))
                else:
                    return None
            except ConnectionRefusedError as e:
                logger.debug(f"ConnectionRefusedError {e}. Connect to {self.host}:{self.port}")
                return None
            except PermissionError as e:
                logger.debug(f"PermissionError {e}. Connect to {self.host}:{self.port}")
                return None
            except Exception as e:
                logger.debug(f"Setup Socket Failure {e}. Connect to {self.host}:{self.port}")
                return None
            sock.setblocking(False)
            return sock

    def net_send(
            self, 
            msg : bytes,
            sock: socket.socket
    ) -> Tuple[bool, bytes | None]:
        """Send message over network

        use poll to monitor the status of socket
        """
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return False, None
        if self.stop_event.is_set():
            return False, None
        
        poller = select.poll()
        poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)
        
        try:
            if (self.trans_layer == 'tcp'):
                
                # handler poll timeout
                events = poller.poll(self.send_time_ms)
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False, None

                fd, event = events[0]

                # handler poll error and hup
                if event & (select.POLLERR):
                    logger.debug("net_send: poll err")
                    return False, None
                
                if event & select.POLLHUP:
                    logger.debug("net_send: poll hup")
                    return False, None

                # send message
                if event & select.POLLOUT:
                    
                    try:
                        sock.sendall(msg)
                    
                    except Exception as err:
                        # socket break when sending
                        logger.debug(f'net_send: socket broken {err} {msg}')
                        return False, None
                    return True, msg
            
            # TODO: support udp
            elif (self.trans_layer == 'udp'):
                events = poller.poll(self.send_time_ms)
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False, None

                fd, event = events[0]
                if event & select.POLLOUT:
                    try:
                        sock.sendto(msg, (self.host, self.port))
                    except Exception as err:
                        # socket break when sending
                        logger.debug(f'net_send: socket broken {msg}')
                        return False, None
                    return True, msg
        finally:
            poller.unregister(sock)

        return False, None
    
    def net_recv(
            self, 
            sock: socket.socket,
            poll_timeout_ms = 0,
            msg_type = '-',
            show_fuzz_ui: bool = False
    ) -> Tuple[str | None, bytes | None]:
        """Recv message over network

        use poll to monitor the status of socket
        """
        # check clinet socket before response
        if sock is None or sock.fileno() < 0:
            logger.debug("Executor: socket closed")
            return None, None
        if self.stop_event.is_set():
            return None, None
        
        """ 
        Remote Socket Normal Close (FIN): poll in, recv value 0
        Remote Socket Exception Close (RST): poll error, recv value -1
        Remote Program Hang: recv timeout, no poll event
        """
        poller = select.poll()
        poller.register(sock, select.POLLIN | select.POLLERR)
        
        time_out_ms = 0
        if poll_timeout_ms != 0:
            time_out_ms = poll_timeout_ms
        else:
            time_out_ms = self.max_timeout_ms
        
        try:
            if (self.trans_layer == 'tcp'):
                events = poller.poll(time_out_ms)

                # handler recv timeout
                if not events:
                    logger.debug('recv: poll timeout')
                    return 'TIMEOUT', None
                
                fd, event = events[0]
                
                if event & (select.POLLERR):
                    return 'POLLERR', None
                # response can be read

                if event & select.POLLIN:
                    buf = b''
                    
                    while True:
                        events = poller.poll(10)
                        if not events:
                            break
                        chunk = sock.recv(2048)
                        if not chunk:
                            break
                        buf += chunk

                    # logger.debug(f'net_recv: {buf}')
                    
                    #TODO: handle invalid response
                    
                    # if buf size is 0, socket close
                    if len(buf) == 0:
                        return 'RCLOSED', None
                    else:
                        # recv response and parse it
                        resp_code = 'UNKOWN'
                        resp_byte: bytes = self.parser_func(buf)
                        try_times = 3
                        if resp_byte == b'' and msg_type not in self.unable_parse_request:
                            while try_times > 0:
                                try_times -= 1
                                resp_byte = self.parser_func(buf)
                                if resp_byte == b'':
                                    logger.debug(f'parse error:{buf}')
                                    self._update_parser(
                                        buf,
                                        show_fuzz_ui,
                                    )
                                    logger.debug('Update Parser')
                                else:
                                    break
                            
                        if resp_byte == b'':
                            self.unable_parse_request.add(msg_type)
                            logger.debug('Parse Error')
                        else:
                            resp_code = resp_byte.decode("utf-8", errors="backslashreplace")
                        # update some analysis data
                        
                            # self.analyzer.last_parser = self.mapper.cur_parser
                            # if self.analyzer.last_generator != None and self.analyzer.last_generator.cur_res != None:
                            #     self.analyzer.last_generator.cur_res.append(resp_code)
                        
                        return resp_code, buf
                
            elif (self.trans_layer == 'udp'):
                events = poller.poll(100) # poll timeout will influence the performance, need to adjust
                if not events:
                    logger.debug('recv: poll timeout')
                    return 'TIMEOUT', None
                fd, event = events[0]
                
                if event & select.POLLIN:
                    buf = b''
                    while True:
                        events = poller.poll(100)
                        if not events:
                            break
                        chunk, _ = sock.recvfrom(2048)
                        if not chunk:
                            break
                        buf += chunk

                    if len(buf) == 0:
                        return 'RCLOSED', None
                    else:
                        # recv response and parse it
                        resp_code = None
                        resp_byte: bytes = self.parser_func(buf)

                        try_times = 3
                        if resp_byte == b'':
                            while try_times > 0:
                                try_times -= 1
                                resp_code = self.parser_func(buf)
                                if resp_code == b'':
                                    logger.debug(f'parse error:{buf}')
                                    self._update_parser(
                                        buf,
                                        show_fuzz_ui,
                                    )
                                    logger.debug('Update Parser')
                                else:
                                    break
                            
                        if resp_byte == b'':
                            logger.debug('Parse Error')
                            resp_code = 'UNKOWN'
                        else:
                            resp_code = resp_byte.decode("utf-8", errors="backslashreplace")

                        return resp_code, buf
                else:
                    logger.debug('recv: no data')
        except Exception:
            logger.exception('Executor: receive failed')
        finally:
            poller.unregister(sock)
    
        return None, None

    def _set_ui_operation(
        self,
        operation: str
    ) -> None:
        with self.analyzer.lock:
            self.analyzer.current_operation = operation

    def _update_parser(
        self,
        response: bytes,
        show_fuzz_ui: bool
    ) -> None:
        if show_fuzz_ui:
            self._set_ui_operation('Updating parser with LLM')
        try:
            new_parser = self.mapper.update_parser(response)
            self.load_parser(new_parser)
        finally:
            if show_fuzz_ui:
                self._set_ui_operation('')
    
    def handle_crash(
        self,
        cons: Conversation,
        proc: subprocess.Popen | RemoteSUTProcess | None,
        msg_type: str,
        msg: bytes,
        stdout: str = '',
        stderr: str = '',
        request_recorded: bool = True,
    ):
        if msg_type in self.crash_testcases.keys() and msg in self.crash_testcases[msg_type]:
            pass
        else:
            self.crash_testcases.setdefault(msg_type, [])

            self.crash_testcases[msg_type].append(msg)
            if not request_recorded and msg_type != '-' and msg:
                cons.add_state(msg_type, 'CRASH')
                cons.add_data(msg, bytes())
            else:
                cons.add_state('-', 'CRASH')
                cons.add_data(bytes(), bytes())
            logger.debug(
                f'Program crash exitcode {getattr(proc, "returncode", None)}'
            )
            with self.analyzer.lock:
                self.analyzer.crash_num += 1

            if getattr(configs, 'fuzz_mode', '') != 'replay':
                if (
                    proc is not None
                    and hasattr(proc, 'communicate')
                    and stdout == ''
                    and stderr == ''
                ):
                    stdout, stderr = self._read_process_output(proc)
                self.save_cons(cons, stdout, stderr, True)
                self.generate_crash_report(
                    cons=cons,
                    proc=proc,
                    msg_type=msg_type,
                    msg=msg,
                    stdout=stdout,
                    stderr=stderr,
                )
    
    def _handle_crash_if_detected(
        self,
        cons: Conversation,
        proc: subprocess.Popen | RemoteSUTProcess | None,
        msg_type: str,
        msg: bytes,
        request_recorded: bool = True,
    ) -> bool:
        if self._is_remote_deployment():
            return self._handle_remote_crash_if_detected(
                cons,
                msg_type,
                msg,
                request_recorded=request_recorded,
            )
        if proc is None:
            return False
        return_code = proc.poll()
        if return_code is None:
            return False

        stdout = ''
        stderr = ''
        if return_code != 0:
            stdout, stderr = self._read_process_output(proc)

        if self._is_crash(return_code, stdout, stderr):
            self.handle_crash(
                cons,
                proc,
                msg_type,
                msg,
                stdout,
                stderr,
                request_recorded=request_recorded,
            )
            return True

        return False

    def _handle_remote_crash_if_detected(
        self,
        cons: Conversation,
        msg_type: str,
        msg: bytes,
        request_recorded: bool = True,
    ) -> bool:
        status = self._monitor().collect_failure_evidence()
        if status.state == UNREACHABLE:
            logger.debug(
                'Executor: UNKNOWN_REMOTE_STATUS; '
                f'detail={status.detail or "monitor unreachable"}'
            )
            return False
        stdout = status.stdout
        stderr = '\n'.join(
            part
            for part in (status.stderr, status.logs)
            if part
        )
        crashed = status.state == CRASHED
        if status.state == EXITED:
            return_code = status.returncode
            if return_code is None and (stdout or stderr):
                return_code = 1
            crashed = self._is_crash(return_code, stdout, stderr)
        if not crashed:
            if status.state == RUNNING:
                logger.debug('Executor: remote SUT still running')
            return False

        proc = RemoteSUTProcess(status)
        self.handle_crash(
            cons,
            proc,
            msg_type,
            msg,
            stdout,
            stderr,
            request_recorded=request_recorded,
        )
        return True
    
    def _is_crash(
        self,
        return_code: int | None,
        stdout: str = '',
        stderr: str = ''
    ) -> bool:
        if return_code is None:
            return False

        if return_code in CRASH_SIGNALS or return_code in CRASH_EXIT_CODES:
            return True

        if return_code == 0:
            return False

        output = f'{stdout}\n{stderr}'
        if any(marker in output for marker in ASAN_CRASH_MARKERS):
            return True

        return any(pattern.search(output) for pattern in RUNTIME_EXCEPTION_PATTERNS)
    
    def _read_process_output(
        self,
        proc: subprocess.Popen
    ) -> tuple[str, str]:
        try:
            stdout, stderr = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            return '', ''
        return self._decode_process_output(stdout), self._decode_process_output(stderr)
    
    def _decode_process_output(
        self,
        data
    ) -> str:
        if data is None:
            return ''
        if isinstance(data, bytes):
            return data.decode('utf-8', errors='backslashreplace')
        return str(data)

    def generate_crash_report(
        self,
        cons: Conversation,
        proc,
        msg_type: str,
        msg: bytes,
        stdout: str = '',
        stderr: str = '',
    ) -> None:
        """Ask the fuzz LLM to summarize a crash-inducing exchange."""
        try:
            chater = self._crash_report_chater()
            if chater is None:
                logger.debug('Executor: skip crash report; no LLM client')
                return

            target_folder = configs.results_path / 'crash_reports'
            target_folder.mkdir(parents=True, exist_ok=True)
            report_id = self._next_artifact_id(target_folder, 'report_', '.json')
            record = self._build_crash_record(
                report_id=report_id,
                cons=cons,
                proc=proc,
                msg_type=msg_type,
                msg=msg,
                stdout=stdout,
                stderr=stderr,
            )
            prompt = self._build_crash_report_prompt(record)
            report = asyncio.run(
                chater.chat_llm(
                    prompt=prompt,
                    usage='crash_report',
                )
            )
            record['llm_report'] = report or ''

            json_path = target_folder / f'report_{report_id}.json'
            md_path = target_folder / f'report_{report_id}.md'
            with json_path.open('w', encoding='utf-8') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
                f.write('\n')
            with md_path.open('w', encoding='utf-8') as f:
                f.write(report or 'The model returned no crash report.')
                f.write('\n')
            logger.debug(f'Executor: saved crash report {json_path}')
        except Exception:
            logger.exception('Executor: crash report generation failed')

    def _crash_report_chater(
        self
    ):
        mapper = getattr(self, 'mapper', None)
        producer = getattr(mapper, 'producer', None)
        return getattr(producer, 'chater', None)

    def _build_crash_record(
        self,
        report_id: str,
        cons: Conversation,
        proc,
        msg_type: str,
        msg: bytes,
        stdout: str,
        stderr: str,
    ) -> dict:
        return {
            'report_id': report_id,
            'target': getattr(configs, 'target_name', ''),
            'protocol': getattr(configs, 'pro_name', ''),
            'sut_deployment': getattr(configs, 'sut_deployment', 'local'),
            'crash': {
                'returncode': getattr(proc, 'returncode', None),
                'trigger_request_type': msg_type,
                'trigger_request': self._encode_bytes(msg),
                'stdout': stdout,
                'stderr': stderr,
            },
            'response_feedback': {
                'request_sequence': list(cons.req_seq),
                'response_sequence': list(cons.res_seq),
            },
            'exchanges': [
                {
                    'index': index,
                    'request_type': (
                        cons.req_seq[index]
                        if index < len(cons.req_seq)
                        else ''
                    ),
                    'response_type': (
                        cons.res_seq[index]
                        if index < len(cons.res_seq)
                        else ''
                    ),
                    'request': self._encode_bytes(request),
                    'response': self._encode_bytes(response),
                }
                for index, (request, response) in enumerate(cons.content)
            ],
        }

    def _build_crash_report_prompt(
        self,
        record: dict
    ) -> str:
        compact = json.dumps(record, indent=2, ensure_ascii=False)
        return (
            'You are a security engineer analyzing a protocol fuzzing crash.\n'
            'Use the captured request/response sequence, response feedback, '
            'process exit information, stdout, and stderr to draft a concise '
            'vulnerability report.\n\n'
            'The report should include:\n'
            '1. Summary\n'
            '2. Affected target/protocol\n'
            '3. Crash signal or sanitizer evidence\n'
            '4. Triggering request and preceding protocol context\n'
            '5. Reproduction steps using the captured message sequence\n'
            '6. Security impact hypothesis\n'
            '7. Triage notes and confidence\n\n'
            'If evidence is insufficient, say so explicitly and avoid '
            'inventing root causes.\n\n'
            f'Crash evidence JSON:\n{compact}'
        )

    def _encode_bytes(
        self,
        data: bytes | None
    ) -> dict:
        raw = data or bytes()
        sample = raw[:4096]
        return {
            'encoding': 'base64',
            'length': len(raw),
            'truncated': len(sample) < len(raw),
            'data': base64.b64encode(sample).decode('ascii'),
            'text': sample.decode('utf-8', errors='backslashreplace'),
            'hex': sample.hex(' '),
        }

    def _next_artifact_id(
        self,
        folder: Path,
        prefix: str,
        suffix: str,
    ) -> str:
        max_id = -1
        for item in folder.iterdir():
            if not item.is_file():
                continue
            name = item.name
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            raw_id = name[len(prefix):-len(suffix)]
            if raw_id.isdigit():
                max_id = max(max_id, int(raw_id))
        return f'{max_id + 1:06d}'
        
    
    def load_parser(
        self,
        p: Parser
    ):
        name_space = {}
        try:
            with open(self.mapper.p_path(p), 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'packet_parser']
                self.parser_func = obj
        except Exception as e:
            logger.debug(f'Mapper: generated failure {e}')

    def load_checkers(
        self,
        checkers: dict[str, Checker]
    ) -> None:
        """Load the latest generated checker for each response type."""
        self.checker_funcs = {}
        for msg_type, checker in checkers.items():
            namespace = {}
            try:
                with open(self.mapper.c_path(checker), 'r', encoding='utf-8') as f:
                    exec(f.read(), namespace)
                checker_func: Callable = namespace.get('packet_checker')
                if not callable(checker_func):
                    raise TypeError('packet_checker is missing or not callable')
                self.checker_funcs[msg_type] = checker_func
            except Exception as e:
                logger.debug(
                    f'Executor: checker load failure [{msg_type}] {e}'
                )

    def load_observers(
        self,
        observers: dict[str, ResponseObserver]
    ) -> None:
        """Load the latest generated semantic observer for each response type."""
        self.observer_funcs = {}
        self.observer_sources = {}
        for msg_type, observer in observers.items():
            try:
                with open(self.mapper.o_path(observer), 'r', encoding='utf-8') as f:
                    code = f.read()
                tree = ast.parse(code)
                function_names = {
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                function_name = next(
                    (
                        name for name in ('packet_observer', 'packet_hasher')
                        if name in function_names
                    ),
                    None,
                )
                if function_name is None:
                    raise TypeError('packet_observer is missing or not callable')
                self.observer_sources[msg_type] = (code, function_name)
            except Exception:
                logger.exception(
                    f'Executor: observer load failure [{msg_type}]'
                )

    def observe_response(
        self,
        response_type: str,
        response: bytes
    ) -> str:
        """Return an IR-normalized digest, falling back to raw SHA-256."""
        fallback = hashlib.sha256(response).hexdigest()
        observer_sources = getattr(self, 'observer_sources', {})
        source = observer_sources.get(response_type)
        if source is None:
            source = observer_sources.get('__all__')
        if source is not None:
            code, function_name = source
            digest = self.mapper._run_dynamic_code(
                code,
                function_name,
                args=(response,),
            )
            if self._valid_observer_digest(digest):
                return digest
            logger.warning(
                'Executor: observer failed or returned invalid digest [%s]',
                response_type,
            )
            return fallback

        observer = self.observer_funcs.get(response_type)
        if observer is None:
            observer = self.observer_funcs.get('__all__')
        if observer is None:
            return fallback
        try:
            digest = observer(response)
            if not self._valid_observer_digest(digest):
                raise TypeError(
                    'packet_observer must return lowercase SHA-256'
                )
            return digest
        except Exception:
            logger.exception(
                f'Executor: observer failure [{response_type}]'
            )
            return fallback

    @staticmethod
    def _valid_observer_digest(digest: object) -> bool:
        return (
            isinstance(digest, str)
            and len(digest) == 64
            and digest == digest.lower()
            and all(char in '0123456789abcdef' for char in digest)
        )

    def observe_response_with_evolution(
        self,
        response_type: str,
        response: bytes
    ) -> str:
        """Evolve an observer only for semantically equivalent divergence."""
        if not hasattr(self, 'checked_response_samples'):
            self.checked_response_samples = {}
        if not hasattr(self, 'reviewed_response_samples'):
            self.reviewed_response_samples = {}
        if not hasattr(self, 'observer_evolution_failures'):
            self.observer_evolution_failures = set()
        if not hasattr(self, 'observer_semantic_reviews'):
            self.observer_semantic_reviews = {}
        digest = self.observe_response(response_type, response)
        if (
            response_type not in self.observer_funcs
            and response_type not in getattr(self, 'observer_sources', {})
        ):
            return digest

        previous_samples = self._historical_response_samples(response_type)
        samples_by_digest: dict[str, list[bytes]] = {}
        for sample in previous_samples:
            sample_digest = self.observe_response(response_type, sample)
            samples_by_digest.setdefault(sample_digest, []).append(sample)
        previous_digests = set(samples_by_digest)
        if not previous_samples or digest in previous_digests:
            return digest

        response_raw_hash = hashlib.sha256(response).hexdigest()
        equivalent_samples: list[bytes] = []
        try:
            for old_digest, old_samples in samples_by_digest.items():
                if old_digest == digest:
                    continue
                representative = old_samples[0]
                old_raw_hash = hashlib.sha256(representative).hexdigest()
                review_key = (
                    response_type,
                    old_raw_hash,
                    response_raw_hash,
                )
                reverse_key = (
                    response_type,
                    response_raw_hash,
                    old_raw_hash,
                )
                equivalent = self.observer_semantic_reviews.get(review_key)
                if equivalent is None:
                    equivalent = self.observer_semantic_reviews.get(reverse_key)
                if equivalent is None:
                    self._set_ui_operation(
                        'Comparing response semantics with LLM'
                    )
                    equivalent = (
                        self.mapper.producer
                        .responses_semantically_equivalent(
                            response_type=response_type,
                            old_response=representative,
                            new_response=response,
                        )
                    )
                    self.observer_semantic_reviews[review_key] = equivalent
                if equivalent:
                    equivalent_samples.extend(old_samples)
        except Exception:
            logger.exception(
                f'Executor: response semantic comparison failed '
                f'[{response_type}]'
            )
            return digest
        finally:
            self._set_ui_operation('')

        if not equivalent_samples:
            logger.debug(
                f'Executor: preserve distinct semantic observations '
                f'[{response_type}]'
            )
            return digest

        samples = list(dict.fromkeys([*equivalent_samples, response]))
        failure_key = tuple(sorted(
            hashlib.sha256(sample).hexdigest()
            for sample in samples
        ))
        if failure_key in self.observer_evolution_failures:
            return digest

        try:
            self._set_ui_operation('Updating response observer with LLM')
            evolved = self.mapper.producer.evolve_observer(
                response_type=response_type,
                samples=samples,
            )
            if evolved is None:
                self.observer_evolution_failures.add(failure_key)
                return digest
            self.mapper.observers = self.mapper.producer.observers
            self.load_observers(self.mapper.equip_observers())
            self._rebuild_observation_indexes(response_type)
            self._reobserve_persisted_invalid_responses(response_type)
            return self.observe_response(response_type, response)
        except Exception:
            self.observer_evolution_failures.add(failure_key)
            logger.exception(
                f'Executor: observer evolution failed [{response_type}]'
            )
            return digest
        finally:
            self._set_ui_operation('')

    def check_response(
        self,
        response_type: str,
        response: bytes
    ) -> bool:
        """Validate a response with the checker selected by parser output."""
        checker = self.checker_funcs.get(response_type)
        if checker is None:
            checker = self.checker_funcs.get('__all__')
        if checker is None:
            logger.debug(
                f'Executor: no checker for response type {response_type}'
            )
            return True

        try:
            is_valid = checker(response)
            if not isinstance(is_valid, bool):
                raise TypeError('packet_checker must return bool')
        except Exception as e:
            logger.debug(
                f'Executor: checker failure [{response_type}] {e}'
            )
            is_valid = False

        if is_valid:
            return True

        logger.debug(format_event(
            'checker.reject',
            response_type=response_type,
            length=len(response),
            response=response,
        ))
        return False

    def check_response_during_fuzzing(
        self,
        request_type: str,
        response_type: str,
        response: bytes,
        enabled: bool
    ) -> bool:
        """Deduplicate exchanges before running fuzzing-stage checkers."""
        if not enabled:
            return True

        response_observation = self.observe_response_with_evolution(
            response_type,
            response,
        )
        raw_digest = hashlib.sha256(response).hexdigest()
        dedup_key = (
            request_type,
            response_type,
            response_observation,
        )
        with self._invalid_response_lock:
            if dedup_key in self.checked_request_response_pairs:
                logger.debug(format_event(
                    'checker.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    response_observation=dedup_key[2],
                ))
                return True
            self.checked_request_response_pairs.add(dedup_key)
            self.checked_response_samples[
                (request_type, response_type, raw_digest)
            ] = response

        return self.check_response(response_type, response)

    def handle_nonconforming_response(
        self,
        cons: Conversation,
        response_type: str
    ) -> None:
        """Review one unique checker rejection and act on the LLM verdict."""
        if not cons.content or not cons.req_seq:
            logger.debug(
                'Executor: cannot review response without conversation data'
            )
            return

        request, response = cons.content[-1]
        request_type = cons.req_seq[-1]
        if not response:
            return

        response_observation = self.observe_response(response_type, response)
        dedup_key = (request_type, response_type, response_observation)
        with self._invalid_response_lock:
            if dedup_key in self.reviewed_invalid_responses:
                logger.debug(
                    'Executor: duplicate non-conforming response skipped '
                    f'[{request_type}/{response_type}] {response_observation}'
                )
                return
            self.reviewed_invalid_responses.add(dedup_key)
            self.reviewed_response_samples[
                (
                    request_type,
                    response_type,
                    hashlib.sha256(response).hexdigest(),
                )
            ] = response

        try:
            self._set_ui_operation(
                'Checking possible non-compliance with LLM'
            )
            analysis = self.mapper.producer.review_nonconforming_response(
                request_type=request_type,
                response_type=response_type,
                request=request,
                response=response,
            )
        except Exception:
            logger.exception(
                'Executor: non-conforming response review failed '
                f'[{request_type}/{response_type}]'
            )
            return
        finally:
            self._set_ui_operation('')

        verdict = analysis.get('verdict', 'uncertain')
        if verdict == 'non_compliant':
            saved = self.save_invalid_response(
                cons,
                response_type,
                analysis=analysis,
            )
            if saved:
                with self.analyzer.lock:
                    self.analyzer.non_compliant_num += 1
            return

        if verdict == 'compliant':
            try:
                self._set_ui_operation('Updating checker with LLM')
                checker = self.mapper.producer.evolve_checker(
                    response_type=response_type,
                    response=response,
                    analysis=analysis,
                )
                if checker is not None:
                    self.load_checkers(self.mapper.equip_checkers())
                    logger.debug(
                        'Executor: checker hot-reloaded after false positive '
                        f'[{request_type}/{response_type}]'
                    )
                else:
                    logger.debug(
                        'Executor: checker evolution produced no update '
                        f'[{request_type}/{response_type}]'
                    )
            except Exception:
                logger.exception(
                    'Executor: checker evolution failed '
                    f'[{request_type}/{response_type}]'
                )
            finally:
                self._set_ui_operation('')
            return

        logger.debug(
            'Executor: compliance review uncertain; no response recorded and '
            f'no checker modified [{request_type}/{response_type}]'
        )

    def save_invalid_response(
        self,
        cons: Conversation,
        response_type: str,
        analysis: dict | None = None
    ) -> bool:
        """Persist one unique, confirmed non-compliant response."""
        if not cons.content or not cons.req_seq:
            return False

        target_folder = configs.results_path / 'invalid_responses'
        target_folder.mkdir(parents=True, exist_ok=True)
        request, response = cons.content[-1]
        request_type = cons.req_seq[-1]
        response_digest = hashlib.sha256(response).hexdigest()
        response_observation = self.observe_response(response_type, response)
        dedup_key = (request_type, response_type, response_observation)
        marker_digest = hashlib.sha256(
            json.dumps(dedup_key, separators=(',', ':')).encode('utf-8')
        ).hexdigest()
        marker_path = target_folder / f'.dedup_{marker_digest}'

        with self._invalid_response_lock:
            if self._invalid_response_exists(target_folder, dedup_key):
                logger.debug(format_event(
                    'invalid_response.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    response_observation=response_observation,
                ))
                return False

            try:
                marker_fd = os.open(
                    marker_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.close(marker_fd)
            except FileExistsError:
                logger.debug(format_event(
                    'invalid_response.deduplicated',
                    request_type=request_type,
                    response_type=response_type,
                    response_observation=response_observation,
                ))
                return False

            file_count = sum(
                1
                for path in target_folder.iterdir()
                if path.is_file() and path.suffix == '.pkl'
            )
            file_id = f'{file_count:06d}'

            try:
                with open(
                    target_folder / f'cons_{file_id}.pkl',
                    'wb'
                ) as f:
                    pickle.dump(cons, f)

                with open(
                    target_folder / f'cons_{file_id}.raw',
                    'wb'
                ) as f:
                    for saved_request, saved_response in cons.content:
                        f.write(
                            b'REQUEST '
                            + str(len(saved_request)).encode()
                            + b'\n'
                        )
                        f.write(saved_request + b'\n')
                        f.write(
                            b'RESPONSE '
                            + str(len(saved_response)).encode()
                            + b'\n'
                        )
                        f.write(saved_response + b'\n')

                with open(
                    target_folder / f'cons_{file_id}.info',
                    'w',
                    encoding='utf-8'
                ) as f:
                    f.write(f'response_type: {response_type}\n')
                    f.write(f'request_types: {cons.req_seq}\n')
                    f.write(f'response_types: {cons.res_seq}\n')

                record = {
                    'request_type': request_type,
                    'response_type': response_type,
                    'response_sha256': response_digest,
                    'response_observation': response_observation,
                    'request': {
                        'encoding': 'base64',
                        'data': base64.b64encode(request).decode('ascii'),
                    },
                    'response': {
                        'encoding': 'base64',
                        'data': base64.b64encode(response).decode('ascii'),
                    },
                    'analysis': analysis or {},
                }
                with open(
                    target_folder / f'cons_{file_id}.analysis.json',
                    'w',
                    encoding='utf-8'
                ) as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)
            except Exception:
                marker_path.unlink(missing_ok=True)
                logger.exception(
                    'Executor: failed to save non-compliant response'
                )
                return False

        logger.debug(format_event(
            'invalid_response.saved',
            testcase=f'cons_{file_id}',
            request_type=request_type,
            response_type=response_type,
            response_sha256=response_digest,
            response_observation=response_observation,
        ))
        return True

    def _invalid_response_exists(
        self,
        target_folder: Path,
        dedup_key: tuple[str, str, str]
    ) -> bool:
        """Check persisted analysis files, including files from older runs."""
        request_type, response_type, response_observation = dedup_key
        for path in target_folder.glob('cons_*.analysis.json'):
            try:
                with path.open('r', encoding='utf-8') as f:
                    record = json.load(f)
                saved_hash = (
                    record.get('response_observation')
                    or record.get('response_hash')
                )
                if not saved_hash:
                    encoded = record.get('response', {}).get('data')
                    if not isinstance(encoded, str):
                        continue
                    saved_response = base64.b64decode(
                        encoded,
                        validate=True,
                    )
                    saved_hash = self.observe_response(
                        response_type,
                        saved_response,
                    )
                if (
                    record.get('request_type') == request_type
                    and record.get('response_type') == response_type
                    and saved_hash == response_observation
                ):
                    return True
            except Exception:
                logger.exception(
                    f'Executor: invalid response index read failed {path}'
                )
        return False

    def _historical_response_samples(
        self,
        response_type: str
    ) -> list[bytes]:
        samples = [
            response
            for (_, saved_type, _), response
            in self.checked_response_samples.items()
            if saved_type == response_type
        ]
        target_folder = configs.results_path / 'invalid_responses'
        if target_folder.is_dir():
            for path in target_folder.glob('cons_*.analysis.json'):
                try:
                    with path.open('r', encoding='utf-8') as f:
                        record = json.load(f)
                    if record.get('response_type') != response_type:
                        continue
                    encoded = record.get('response', {}).get('data')
                    if isinstance(encoded, str):
                        samples.append(base64.b64decode(
                            encoded,
                            validate=True,
                        ))
                except Exception:
                    logger.exception(
                        f'Executor: historical response read failed {path}'
                    )
        return list(dict.fromkeys(samples))

    def _rebuild_observation_indexes(
        self,
        response_type: str
    ) -> None:
        self.checked_request_response_pairs = {
            key
            for key in self.checked_request_response_pairs
            if key[1] != response_type
        }
        self.reviewed_invalid_responses = {
            key
            for key in self.reviewed_invalid_responses
            if key[1] != response_type
        }
        for (request_type, saved_type, _), response in (
            self.checked_response_samples.items()
        ):
            if saved_type == response_type:
                self.checked_request_response_pairs.add((
                    request_type,
                    saved_type,
                    self.observe_response(saved_type, response),
                ))
        for (request_type, saved_type, _), response in (
            self.reviewed_response_samples.items()
        ):
            if saved_type == response_type:
                self.reviewed_invalid_responses.add((
                    request_type,
                    saved_type,
                    self.observe_response(saved_type, response),
                ))

    def _reobserve_persisted_invalid_responses(
        self,
        response_type: str
    ) -> None:
        target_folder = configs.results_path / 'invalid_responses'
        if not target_folder.is_dir():
            return

        records = []
        for path in target_folder.glob('cons_*.analysis.json'):
            try:
                with path.open('r', encoding='utf-8') as f:
                    record = json.load(f)
                if record.get('response_type') == response_type:
                    encoded = record.get('response', {}).get('data')
                    if isinstance(encoded, str):
                        response = base64.b64decode(
                            encoded,
                            validate=True,
                        )
                        record['response_observation'] = self.observe_response(
                            response_type,
                            response,
                        )
                        temp_path = path.with_suffix(path.suffix + '.tmp')
                        with temp_path.open('w', encoding='utf-8') as f:
                            json.dump(
                                record,
                                f,
                                indent=2,
                                ensure_ascii=False,
                            )
                        temp_path.replace(path)
                records.append(record)
            except Exception:
                logger.exception(
                    f'Executor: persisted response reobserve failed {path}'
                )

        for marker in target_folder.glob('.dedup_*'):
            marker.unlink(missing_ok=True)
        for record in records:
            request_type = record.get('request_type')
            saved_type = record.get('response_type')
            saved_hash = (
                record.get('response_observation')
                or record.get('response_hash')
            )
            if (
                isinstance(saved_type, str)
                and not isinstance(saved_hash, str)
            ):
                encoded = record.get('response', {}).get('data')
                if isinstance(encoded, str):
                    try:
                        saved_hash = self.observe_response(
                            saved_type,
                            base64.b64decode(encoded, validate=True),
                        )
                    except Exception:
                        logger.exception(
                            'Executor: marker observation reconstruction failed'
                        )
            if not all(isinstance(value, str) for value in (
                request_type,
                saved_type,
                saved_hash,
            )):
                continue
            key = (request_type, saved_type, saved_hash)
            marker_digest = hashlib.sha256(
                json.dumps(key, separators=(',', ':')).encode('utf-8')
            ).hexdigest()
            (target_folder / f'.dedup_{marker_digest}').touch(exist_ok=True)
        
    def save_cons(
        self,
        cons: Conversation,
        stdout: str = '',
        stderr: str = '',
        crash: bool = False
    ) -> bool:
        """Use pickle to store section tree instance
        """
        seed_digest = self._seed_digest(cons, crash)
        seed_lock = getattr(self, '_saved_seed_lock', None)
        if seed_lock is None:
            seed_lock = threading.Lock()
            self._saved_seed_lock = seed_lock
        with seed_lock:
            saved_seed_digests = getattr(self, '_saved_seed_digests', None)
            if saved_seed_digests is None:
                saved_seed_digests = set()
                self._saved_seed_digests = saved_seed_digests
            if seed_digest in saved_seed_digests:
                logger.debug('Executor: skip duplicate replayable seed')
                return False
            saved_seed_digests.add(seed_digest)

        pending = ''
        if crash:
            pending = '_crash'
        target_folder = configs.results_path / 'raw_testcases'
        enrich_folder = configs.results_path / 'enrich_testcases'
        if not target_folder.is_dir():
            target_folder.mkdir()

        if not enrich_folder.is_dir():
            enrich_folder.mkdir()
            
        file_count = 0
        for item in target_folder.iterdir():
            if item.is_file():
                file_count += 1
        
        file_count = str(file_count)
        while len(file_count) < 6:
            file_count = '0' + file_count

        with open(target_folder / f'cons_{file_count}{pending}.raw', 'ab') as f:
            for request, response in cons.content:
                if request:
                    f.write(request + b'\n')
                    f.write(response + b'\n')
        
        with open(enrich_folder / f'request_{file_count}{pending}.raw', 'ab') as f:
            for request, _ in cons.content:
                if request:
                    f.write(request + b'\n')
        
        file_count = 0
        target_folder = configs.results_path / 'replayable_testcases'
        if not target_folder.is_dir():
            target_folder.mkdir()
        for item in target_folder.iterdir():
            if item.is_file():
                file_count += 1
                
        file_count = str(file_count)
        while len(file_count) < 6:
            file_count = '0' + file_count        
        with open(target_folder / f"cons_{file_count}{pending}.pkl", "wb") as f:
            pickle.dump(cons, f)
            
        
        logger.debug(f'run: save cons_{file_count}')    
        info_file = configs.results_path / 'cons_info'
        with open(info_file, 'a', encoding='utf-8') as f:
            f.write(file_count + '\n')
            f.write('-'.join(cons.res_seq) + '\n')
            f.write(f'stdout: {stdout}' + '\n')
            f.write(f'stderr: {stderr}' + '\n')
        return True

    @staticmethod
    def _seed_digest(cons: Conversation, crash: bool) -> str:
        """Return a stable digest for a replayable conversation.

        Retention happens in both model learning and fuzzing.  Include the
        symbolic sequences and raw byte pairs so only an exact replay seed is
        deduplicated; crashes retain a separate corpus from normal traffic.
        """
        digest = hashlib.sha256()
        digest.update(b'crash=' + (b'1' if crash else b'0') + b'\0')
        for sequence in (cons.req_seq, cons.res_seq):
            digest.update(len(sequence).to_bytes(8, 'big'))
            for item in sequence:
                encoded = item.encode('utf-8', errors='surrogatepass')
                digest.update(len(encoded).to_bytes(8, 'big'))
                digest.update(encoded)
        digest.update(len(cons.content).to_bytes(8, 'big'))
        for request, response in cons.content:
            digest.update(len(request).to_bytes(8, 'big'))
            digest.update(request)
            digest.update(len(response).to_bytes(8, 'big'))
            digest.update(response)
        return digest.hexdigest()
