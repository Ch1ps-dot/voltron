import subprocess
from pathlib import Path
import time, select, socket
from typing import Callable

from voltron.utils.logger import logger
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.analyzer.analyzer import Analyzer
import math, statistics, threading

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path, 
            post_script:Path,
            mapper: Mapper,
            analyzer: Analyzer,
            setup_time_s:float = 1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.pre_script: Path = pre_script
        self.post_script: Path = post_script
        self.host = host
        self.port = port
        self.trans_layer = trans_layer

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        self.max_timeout_ms = 5000
        self.probe_times = 5 # for estimating suitable response time
        self.probe_recv_time_s = []
       
        self.mapper = mapper # mapper between symbol and message
        self.analyzer = analyzer # runtime analyzer

        self.last_sent = '-'
        self.last_recv = '-'
        
        self.parser_func: Callable
        self.load_parser(self.mapper.cur_parser)

    def post_exe(
            self
    ) -> subprocess.Popen | None:
        if (self.post_script.is_file()):
            try:
                proc = subprocess.Popen(
                    [self.post_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return proc
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')
                return None

    def pre_exe(
            self,
    ) -> subprocess.Popen | None:
        if (self.pre_script.is_file()):
            try:
                proc = subprocess.Popen(
                    [self.pre_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return proc
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')
                return None

    def communicate(
            self,
            generator_seq: list[Generator]
    ):  
        """
        TODO: Deal with
        """
        # prepare some settings and setup SUT
        proc = self.pre_exe()
        if proc is None:
            return
        if proc.poll() is not None: 
            out, err = proc.communicate()
            logger.debug(f'Executor: SUT Setup Failure:{err}')
            exit(1)

        # wait for server setup
        time.sleep(self.setup_time_s)
        sock = self.setup_socket()
        if sock == None:
            logger.debug('Executor: Socket Setup Failure' )
            if proc.poll() is None:
                proc.terminate()
            exit(1)
            return
        
        resp_code = self.net_recv(sock=sock)
                
        # recv initialize message
        if(resp_code):
            logger.debug(f'Executor: recv {resp_code}')

        # send the message path
        for g in generator_seq:

            # send message and parse response
            if(self.net_send(g, sock)):
                resp_code = self.net_recv(sock=sock)
                
                # handle response. If socket closed, stop sending.
                match resp_code:
                    
                    # remote crash
                    case 'ERR':
                        with self.analyzer.lock:
                            self.analyzer.err_num += 1
                        break
                    
                    # remote hang
                    case 'TIMEOUT':
                        with self.analyzer.lock:
                            self.analyzer.timeout_num += 1
                        break
                    
                    # remote close the socket
                    case 'RCLOSED':
                        with self.analyzer.lock:
                            self.analyzer.rclose_num += 1
                        break
                    case _:
                        self.last_recv = resp_code
                        logger.debug(f'Executor: recv {resp_code}')
            
            # If socket closed, stop sending
            else:
                logger.debug('Executor: socket closed')
                break

        with self.analyzer.lock:
            self.analyzer.path_num = self.analyzer.path_num + 1

        # close socket and SUT
        if sock.fileno() < 0:
            sock.close()
        if proc.poll() is None:
            proc.terminate()

        self.post_exe()
    
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
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((self.host, self.port))
                elif (self.trans_layer == 'udp'):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                else:
                    return None
            except Exception as e:
                logger.debug(f"Setup Socket Failure {e}")
                return None
            sock.setblocking(False)
            return sock

    def net_send(
            self, 
            g : Generator,
            sock: socket.socket
    ):
        """Send message over network

        use poll to monitor the status of socket
        """
        logger.debug("net_send: begin send")
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return False
        
        poller = select.poll()
        poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)
        
        try:
            if (self.trans_layer == 'tcp'):
                # handler poll timeout
                events = poller.poll(self.send_time_ms)
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False

                fd, event = events[0]

                # handler poll error and hup
                if event & (select.POLLERR | select.POLLHUP):
                    logger.debug("net_send: poll error / hup")
                    return False

                # send message
                if event & select.POLLOUT:
                    msg = self.exe_generator(g)
                    sock.sendall(msg)

                    with self.analyzer.lock:
                        self.analyzer.req_num = self.analyzer.req_num + 1
                        self.analyzer.req_types_update(g.msg_type)
                        self.analyzer.last_generator = g
                    return True
            
            # TODO: support udp
            elif (self.trans_layer == 'udp'):
                msg = self.exe_generator(g)
                sock.sendto(msg, (self.host, self.port))
        finally:
            poller.unregister(sock)

        return False
    
    def net_recv(
            self, 
            sock: socket.socket
    ) -> str | None:
        """Recv message over network

        use poll to monitor the status of socket
        """
        logger.debug("Executor: begin recv")
        # check clinet socket before response
        if sock is None or sock.fileno() < 0:
            logger.debug("Executor: socket closed")
            return None
        
        """ 
        Remote Socket Normal Close (FIN): poll in, recv value 0
        Remote Socket Exception Close (RST): poll error, recv value -1
        Remote Program Hang: recv timeout, no poll event
        """
        poller = select.poll()
        poller.register(sock, select.POLLIN | select.POLLERR)

        logger.debug('Executor: begin recv')
        
        try:
            if (self.trans_layer == 'tcp'):
                events = poller.poll(self.max_timeout_ms)

                # # estimate the suitable timeout for recv
                # if (self.probe_times > 0):
                #     s_time = time.time()
                #     events = poller.poll(self.max_timeout_ms)
                #     if not events:
                #         logger.debug('Executor: recv timeout exceed the max limit')
                #         return None
                #     else:
                #         self.probe_times -= 1
                #         if (self.probe_times <= 0):
                #             # timeout = mean_value + 2 * standard_error
                #             mean_time: float = statistics.mean(self.probe_recv_time_s)
                #             if (len(self.probe_recv_time_s) > 2):
                #                 std_dev: float = statistics.stdev(self.probe_recv_time_s)
                #                 self.recv_time_ms = (mean_time + 2 * std_dev) * 1000
                #             else:
                #                 self.recv_time_ms = (mean_time + 0.1) * 1000
                #         else:
                #             self.probe_recv_time_s.append(time.time() - s_time)
                #             logger.debug(f'Executor: probe-remain {self.probe_times} time {self.probe_recv_time_s}')
                # else:
                #     # recv with estimated timeout 
                #     events = poller.poll(self.recv_time_ms)

                # handler recv timeout
                if not events:
                    logger.debug('Executor: recv time out')
                    return 'TIMEOUT'
                
                fd, event = events[0]
                
                if event & (select.POLLERR):
                    logger.debug("Executor: recv poll error")
                    return 'ERR'
                # response can be read

                if event & select.POLLIN:
                    buf = sock.recv(1024)
                    logger.debug(f'recv {buf}')
                    
                    #TODO: handle invalid response
                    
                    # if buf size is 0, socket close
                    if len(buf) == 0:
                        logger.debug('Executor: remote socket closed')
                        return 'RCLOSED'
                    else:
                        # recv response and parse it
                        resp_code: str = self.parser_func(buf)
                        self.last_recv = resp_code
                        
                        # update some analysis data
                        with self.analyzer.lock:
                            self.analyzer.res_num += 1
                            self.analyzer.last_parser = self.mapper.cur_parser
                            if self.analyzer.last_generator != None and self.analyzer.last_generator.cur_res != None:
                                self.analyzer.last_generator.cur_res.append(resp_code)
                                
                        return resp_code
                
            elif (self.trans_layer == 'udp'):
                buf, _ = sock.recvfrom(1024)
                return self.parser_func(buf)
            
        finally:
            poller.unregister(sock)
    
        return None
    
    def exe_generator(
        self,
        g: Generator
    ) -> bytes:
        name_space = {}
        try:
            with open(self.mapper.g_path(g), 'r', encoding='utf-8') as f:
                code = f.read()
                exec(code, name_space)
                obj = name_space[f'generated_{g.msg_type}']
                return obj()
        except Exception as e:
            logger.error(f'Mapper: generated failure {e}')
            exit(0)
    
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
            logger.error(f'Mapper: generated failure {e}')
            exit(0)