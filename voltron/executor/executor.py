import subprocess
from pathlib import Path
import time, select, socket, pickle
from typing import Callable, Tuple

from voltron.configs import configs
from voltron.utils.logger import logger
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.analyzer.analyzer import analyzer
from voltron.executor.conversation import Conversation
import math, statistics, threading, traceback, sys, os, signal

class Executor:
    def __init__(
            self,
            mapper: Mapper,
            stop_event:threading.Event,
            setup_time_s:float = 0.1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.pre_script: Path = configs.pre_script
        self.post_script: Path = configs.post_script
        self.host = configs.host
        self.port = configs.port
        self.trans_layer = configs.trans_layer

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        self.max_timeout_ms = 3000
        self.probe_times = 5 # for estimating suitable response time
        self.probe_recv_time_s = []
       
        self.mapper = mapper # mapper between symbol and message
        self.analyzer = analyzer # runtime analyzer

        self.parser_func: Callable
        self.load_parser(self.mapper.cur_parser)
        self.stop_event = stop_event
        
        self.cons_path = configs.results_path / 'testcases'
        if (not self.cons_path.is_dir()):
            self.cons_path.mkdir()

    def post_exe(
            self
    ) -> subprocess.Popen | None:
        if (self.post_script.is_file()):
            try:
                proc = subprocess.Popen(
                    [self.post_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setpgrp
                )
                return proc
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')
                return None

    def pre_exe(
        self
    ) -> subprocess.Popen | None:
        if (self.pre_script.is_file()):
            try:
                proc = subprocess.Popen(
                    [self.pre_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setpgrp
                )
                analyzer.sut_proc = proc
                return proc
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')
                return None

    def interact(
        self,
        msg_seq: list[tuple[str, bytes]],
        poll_wait_ms: int = 5000
    ) -> Tuple[bool, Conversation | None]:  
        """
        TODO: Deal with interaction
        """
        # logger.debug('exe: begin inter')
        # prepare some settings and setup SUT
        self.kill_listeners(self.port)
        clean = self.post_exe()
        proc = self.pre_exe()
        
        # logger.debug('exe: after setup')
        
        if proc is None or clean is None:
            logger.debug(f'Executor: SUT Setup Failure')
            return False, None
        if proc.poll() is not None: 
            # out, err = proc.communicate()
            # logger.debug(f'Executor: SUT Setup Failure: {err} {out}')
            return False, None
        
        # avoid unexceptional crash of target
        for _ in range(100):
            if proc is not None and proc.poll() is not None:
                logger.debug(f'Executor:  SUT Setup Failure {proc.returncode}')
                proc = self.pre_exe()
                time.sleep(self.setup_time_s)
            else:
                break

        if proc is None:
            raise Exception('Execute: process bad')
        if proc.poll() is not None:
            raise Exception('Execute: process bad')
        
        # wait for server setup
        for _ in range(100):
            time.sleep(self.setup_time_s)
            sock = self.setup_socket()
            if sock == None:
                if proc.poll() is not None:
                    stderr_data = proc.communicate()
                    logger.debug(f'Executor:  SUT Setup Failure {proc.returncode} {stderr_data}')
                logger.debug('Executor: Socket Setup Failure' )
                continue
            else:
                break
            
        if sock == None:
            logger.debug('socket: setup failure')
            self.stop_event.set()
            sys.exit(0)
            
        # keep request and response in Conversation
        cons: Conversation = Conversation()
        
        # maybe recv initialize message
        resp_code, resp_data = self.net_recv(sock=sock, poll_timeout_ms=100)
        last_recv = '-'
        if(resp_code and resp_data):
            cons.add_state('-', resp_code)
            cons.add_data(bytes(), resp_data)
            last_recv = resp_code
            with self.analyzer.lock:
                self.analyzer.res_types_update(resp_code)
                self.analyzer.resp_trans_update(f'-/{resp_code}')
        else:
            cons.add_state('-', '-')
            cons.add_data(bytes(), bytes())

        # send the message path
        for msg_type, msg in msg_seq:
            
            if self.stop_event.is_set():
                sock.close()
                break
            
            # the target is running
            if proc.poll() is not None:
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
                resp_code, resp_data = self.net_recv(sock=sock, poll_timeout_ms=poll_wait_ms)

                if resp_code == 'POLLERR':
                    return_code = proc.poll()
                    if return_code:
                        cons.add_state(msg_type, 'CRASH')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.crash_num += 1
                    else:
                        cons.add_state(msg_type, 'CLOSED')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                    break
                
                elif resp_code == 'TIMEOUT':
                    return_code = proc.poll()
                    if return_code:
                        cons.add_state(msg_type, 'CRASH')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.crash_num += 1
                    else:
                        cons.add_state(msg_type, 'TIMEOUT')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.timeout_num += 1
                    break
                
                elif resp_code == 'RCLOSED':
                    return_code = proc.poll()
                    if return_code:
                        cons.add_state(msg_type, 'CRASH')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.crash_num += 1
                    else:
                        cons.add_state(msg_type, 'CLOSED')
                        cons.add_data(req_data, bytes())
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                    break
                
                else:
                    if(resp_code == None):
                        logger.debug('Executor: parse error')
                        continue
                    with self.analyzer.lock:
                        self.analyzer.res_num += 1
                        self.analyzer.res_types_update(resp_code)
                        self.analyzer.resp_trans_update(f'{last_recv}/{resp_code}')
                    last_recv = resp_code
                    logger.debug(f'recv <- {resp_data}')
                    
                    # record conversation data
                    if(req_data and resp_data):
                        cons.add_data(req_data, resp_data)
                    cons.add_state(msg_type, resp_code)
            
            # If socket closed, stop sending
            else:
                return_code = proc.poll()
                
                # program exited unexpectly
                if return_code and return_code != 0:
                    cons.add_state('-', 'CRASH')
                    with self.analyzer.lock:
                        self.analyzer.crash_num += 1
                    cons.save_cons()
                seq = '/'.join([msg_type for msg_type, data in msg_seq])
                logger.debug(f'Executor: socket closed with {return_code} because of {seq}')
                break

        with self.analyzer.lock:
            self.analyzer.path_num = self.analyzer.path_num + 1

        # close socket
        sock.close()
        
        # close process
        try:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                returncode = proc.wait(timeout=0.5)
                logger.debug(f'sut returncode: {returncode}')
        except Exception as err:
            logger.debug(f'proc close err: {err}')
            
        if clean.poll() is None:
            os.killpg(clean.pid, signal.SIGTERM)
            clean.wait()
        
        # ensure sub-subprocess die
        while True:
            try:
                os.killpg(proc.pid, 0)
                # no die, just kill
                time.sleep(0.1)
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception as e:
                # sub-subprocess die out
                analyzer.sut_proc = None
                # logger.debug(f'target process: {e}')
                break
        
        # kill clean script
        try:
            os.killpg(clean.pid, 0)
            
            # no die, just kill
            os.killpg(clean.pid, signal.SIGKILL)
            logger.debug(f"clean process: clean process alive")
        except Exception as e:
            # sub-subprocess die out
            # logger.debug(f'clean process: {e}')
            pass
                

        # self.post_exe()
        logger.debug("Executor: query done")
        return True, cons
    
    def kill_listeners(
        self,
        port: int
    ):
        pids = []
        try:
            result = subprocess.check_output(
                ["netstat", "-tulnp", "2>/dev/null"],  
                text=True,
                stderr=subprocess.DEVNULL
            )
            lines = result.strip().split("\n")[1:]
            for line in lines:
                if f":{port}" in line:
                    pid_str = line.split("/")[0].split(" ")[-1]
                    if pid_str.isdigit():
                        pids.append(int(pid_str))
            pids = list(set(pids))
        except subprocess.CalledProcessError as e:
            logger.debug(f'kill execution failure {e}')
        
        try:
            for pid in pids:
                logger.debug(f'kill {pid}')
                os.kill(pid, signal.SIGTERM)
        except Exception as e:
            logger.debug(f'kill execution failure {e}')
        
        
        
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
            poll_timeout_ms = 0
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
                        resp_code = ''
                        for i in range(5):
                            resp_code: str = self.parser_func(buf)
                            if resp_code == '':
                                new_parser = self.mapper.update_parser(buf)
                                self.load_parser(new_parser)
                                logger.debug('Update Parser')
                        if resp_code == '':
                            logger.debug('Parse Error')
                            resp_code = 'UNKOWN'
                        
                        # update some analysis data
                        
                            # self.analyzer.last_parser = self.mapper.cur_parser
                            # if self.analyzer.last_generator != None and self.analyzer.last_generator.cur_res != None:
                            #     self.analyzer.last_generator.cur_res.append(resp_code)
                                
                        return resp_code, buf
                
            elif (self.trans_layer == 'udp'):
                events = poller.poll(time_out_ms)
                if not events:
                    logger.debug('recv: poll timeout')
                    return 'TIMEOUT', None
                fd, event = events[0]
                
                if event & select.POLLIN:
                    buf = b''
                    while True:
                        events = poller.poll(time_out_ms)
                        if not events:
                            break
                        chunk, _ = sock.recvfrom(2048)
                        if not chunk:
                            break
                        buf += chunk
                    if len(buf) == 0:
                        return 'RCLOSED', None
                    resp_code = self.parser_func(buf)
                    return resp_code, buf
                else:
                    logger.debug('recv: no data')
            
        finally:
            poller.unregister(sock)
    
        return None, None
    
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
    
    def load_cons(
            self,
            cons: Conversation
    ):
        """Load rfc parser 
        """
        with open(self.cons_path / "section_tree.pkl", "rb") as f:
            pickle.load(f)
        
    def save_cons(
            self,
            cons: Conversation
    ):
        """Use pickle to store section tree instance
        """
        with open(self.cons_path / "section_tree.pkl", "wb") as f:
            pickle.dump(cons, f)
            logger.debug("Executor: save cons")  