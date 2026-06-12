import subprocess
from pathlib import Path
import time, select, socket, pickle, json, base64, hashlib
from typing import Callable, Tuple

from voltron.configs import configs
from voltron.utils.logger import logger_fuzz as logger
from voltron.executor.mapper import Mapper
from voltron.synthesizer.synthesizer import Generator, Parser
from voltron.synthesizer.checker import Checker
from voltron.analyzer.analyzer import analyzer
from voltron.executor.conversation import Conversation
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

        self.parser_func: Callable
        self.load_parser(self.mapper.cur_parser)
        self.checker_funcs: dict[str, Callable[[bytes], bool]] = {}
        self.load_checkers(self.mapper.equip_checkers())
        self.checked_request_response_pairs: set[
            tuple[str, str, str]
        ] = set()
        self.reviewed_invalid_responses: set[tuple[str, str, str]] = set()
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
            f'endpoint=localhost:{self.port}',
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

    def interact(
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
        self.kill_listeners(self.port)
        clean = self.setup_exe()
        proc = self.run_exe()
        
        
        # if proc is None:
        #     logger.debug(f'Executor: SUT Setup Failure')
        #     return False, None
        
        # if proc.poll() is not None: 
        #     logger.debug(f'Executor: SUT Setup Failure: {proc.returncode}')
        #     return False, None
        
        # avoid unexceptional crash of target
        for attempt in range(1, 101):
            if proc is not None and proc.poll() is not None:
                self._log_sut_start_failure(
                    proc,
                    stage='process-exited-before-ready-check',
                    attempt=attempt,
                )
                proc = self.run_exe()
                time.sleep(self.setup_time_s)
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
            time.sleep(self.setup_time_s)
            sock = self.setup_socket()
            if sock == None:
                if proc != None and proc.poll() is not None:
                    self._log_sut_start_failure(
                        proc,
                        stage='socket-readiness-check',
                        attempt=attempt,
                        detail='process exited before socket became ready',
                    )
                    proc = self.run_exe()
                    self.kill_listeners(self.port)
                continue
            else:
                break
            
        if proc is None:
            self._log_sut_start_failure(
                proc,
                stage='socket-readiness-check',
                detail='restart returned no process',
            )
            raise Exception('Executor: process close')
        if proc.poll() is not None:
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
                ),
            )
            self.stop_event.set()
            sys.exit(0)
        
        
        logger.debug(">>>Executor: interact start")
        # keep request and response in Conversation
        cons: Conversation = Conversation()
        
        # maybe recv initialize message
        resp_code, resp_data = self.net_recv(sock=sock, poll_timeout_ms=100)
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
        for msg_type, msg in msg_seq:
            last_msg_type = msg_type
            last_msg = msg if msg is not None else bytes()
            
            if self.stop_event.is_set():
                break
            
            if proc.poll() is not None:
                if not self._handle_crash_if_detected(cons, proc, msg_type, last_msg):
                    cons.add_state(msg_type, 'CLOSED')
                    cons.add_data(bytes(), bytes())
                    logger.debug('server close')
                break
            
            # send message and parse response
            if msg == None:
                return False, None
            
            flag, req_data = self.net_send(msg, sock)
            
            # success to send
            if(flag and req_data):
                logger.debug(f'sent -> {req_data}')
                with self.analyzer.lock:
                    self.analyzer.req_num = self.analyzer.req_num + 1
                    self.analyzer.req_types_update(msg_type)
                resp_code, resp_data = self.net_recv(sock=sock, poll_timeout_ms=poll_wait_ms, msg_type=msg_type)

                if resp_code == 'POLLERR':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(cons, proc, msg_type, msg):
                        cons.add_state(msg_type, 'POLLERR')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- POLLERR')
                    break
                
                elif resp_code == 'TIMEOUT':
                    # crash
                    # noraml
                    if not self._handle_crash_if_detected(cons, proc, msg_type, msg):
                        cons.add_state(msg_type, 'TIMEOUT')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.timeout_num += 1
                        logger.debug(f'recv <- TIMEOUT')
                    break
                
                elif resp_code == 'RCLOSED':
                    # crash
                    # normal
                    if not self._handle_crash_if_detected(cons, proc, msg_type, msg):
                        cons.add_state(msg_type, 'CLOSED')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        logger.debug(f'recv <- rclose')
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
                    logger.debug(f'recv <- {resp_data}')
                    
                    # record conversation data
                    if req_data is not None and resp_data is not None:
                        cons.add_data(req_data, resp_data)
                    cons.add_state(msg_type, resp_code)
                    if not is_valid_response:
                        self.handle_nonconforming_response(cons, resp_code)
            
            # If socket closed, stop sending
            else:
                return_code = proc.poll()
                
                # program exited unexpectly
                self._handle_crash_if_detected(cons, proc, msg_type, msg)
                        
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
        
        self._handle_crash_if_detected(cons, proc, last_msg_type, last_msg)
        
        # close process
        close_signal = signal.SIGUSR1 if configs.fuzz_mode == 'replay' else signal.SIGTERM
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
        if clean != None:
            self._terminate_process_group(clean, signal.SIGKILL, timeout=1)
                

        # self.post_exe()
        logger.debug("<<<Executor: interact done")
        return True, cons

    def _terminate_process_group(
        self,
        proc: subprocess.Popen,
        sig: signal.Signals,
        timeout: float
    ) -> None:
        """Terminate a SUT process tree that was started with start_new_session."""
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
                    sock = socket.create_connection(('localhost', self.port))
                elif (self.trans_layer == 'udp'):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
            msg_type = '-'
    ) -> Tuple[str | None, bytes | None]:
        """Recv message over network

        use poll to monitor the status of socket
        """
        # check clinet socket before response
        if sock is None or sock.fileno() < 0:
            logger.debug("Executor: socket closed")
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
                                    new_parser = self.mapper.update_parser(buf)
                                    self.load_parser(new_parser)
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
                                    new_parser = self.mapper.update_parser(buf)
                                    self.load_parser(new_parser)
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
    
    def handle_crash(
        self,
        cons: Conversation,
        proc: subprocess.Popen,
        msg_type: str,
        msg: bytes,
        stdout: str = '',
        stderr: str = ''
    ):
        if msg_type in self.crash_testcases.keys() and msg in self.crash_testcases[msg_type]:
            pass
        else:
            self.crash_testcases.setdefault(msg_type, [])

            self.crash_testcases[msg_type].append(msg)
            cons.add_state('-', 'CRASH')
            logger.debug(f'Program crash exitcode {proc.returncode}')
            with self.analyzer.lock:
                self.analyzer.crash_num += 1

            if configs.fuzz_mode != 'replay':
                if stdout == '' and stderr == '':
                    stdout, stderr = self._read_process_output(proc)
                self.save_cons(cons, stdout, stderr, True)
    
    def _handle_crash_if_detected(
        self,
        cons: Conversation,
        proc: subprocess.Popen,
        msg_type: str,
        msg: bytes
    ) -> bool:
        return_code = proc.poll()
        if return_code is None:
            return False

        stdout = ''
        stderr = ''
        if return_code != 0:
            stdout, stderr = self._read_process_output(proc)

        if self._is_crash(return_code, stdout, stderr):
            self.handle_crash(cons, proc, msg_type, msg, stdout, stderr)
            return True

        return False
    
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

        logger.debug(
            f'Executor: non-conforming response [{response_type}] {response!r}'
        )
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

        dedup_key = (
            request_type,
            response_type,
            hashlib.sha256(response).hexdigest(),
        )
        with self._invalid_response_lock:
            if dedup_key in self.checked_request_response_pairs:
                logger.debug(
                    'Executor: duplicate request-response pair skipped before '
                    f'checker [{request_type}/{response_type}]'
                )
                return True
            self.checked_request_response_pairs.add(dedup_key)

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

        response_digest = hashlib.sha256(response).hexdigest()
        dedup_key = (request_type, response_type, response_digest)
        with self._invalid_response_lock:
            if dedup_key in self.reviewed_invalid_responses:
                logger.debug(
                    'Executor: duplicate non-conforming response skipped '
                    f'[{request_type}/{response_type}] {response_digest}'
                )
                return
            self.reviewed_invalid_responses.add(dedup_key)

        try:
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

        verdict = analysis.get('verdict', 'uncertain')
        if verdict == 'non_compliant':
            self.save_invalid_response(
                cons,
                response_type,
                analysis=analysis,
            )
            return

        if verdict == 'compliant':
            try:
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
    ) -> None:
        """Save a request/response prefix confirmed as non-compliant."""
        target_folder = configs.results_path / 'invalid_responses'
        target_folder.mkdir(parents=True, exist_ok=True)

        file_count = sum(
            1
            for path in target_folder.iterdir()
            if path.is_file() and path.suffix == '.pkl'
        )
        file_id = f'{file_count:06d}'

        with open(target_folder / f'cons_{file_id}.pkl', 'wb') as f:
            pickle.dump(cons, f)

        with open(
            target_folder / f'cons_{file_id}.raw',
            'wb'
        ) as f:
            for request, response in cons.content:
                f.write(b'REQUEST ' + str(len(request)).encode() + b'\n')
                f.write(request + b'\n')
                f.write(b'RESPONSE ' + str(len(response)).encode() + b'\n')
                f.write(response + b'\n')

        with open(
            target_folder / f'cons_{file_id}.info',
            'w',
            encoding='utf-8'
        ) as f:
            f.write(f'response_type: {response_type}\n')
            f.write(f'request_types: {cons.req_seq}\n')
            f.write(f'response_types: {cons.res_seq}\n')

        request, response = cons.content[-1]
        record = {
            'request_type': cons.req_seq[-1],
            'response_type': response_type,
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

        logger.debug(
            f'Executor: saved confirmed non-compliant response cons_{file_id}'
        )
        
    def save_cons(
        self,
        cons: Conversation,
        stdout: str = '',
        stderr: str = '',
        crash: bool = False
    ):
        """Use pickle to store section tree instance
        """
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
