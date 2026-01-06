import subprocess
from pathlib import Path
import time, select, socket

from voltron.executor.nio import Nio
from voltron.utils.logger import logger
from voltron.sheduler.alphabet import Symbol, Alphabet
from voltron.handler.handler import Handler
from voltron.utils.analyze import Analyzer
import math, statistics, threading

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path, 
            post_script:Path,
            handler: Handler,
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
        self.handler = handler

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        self.max_timeout = 5000
        self.probe_times = 5 # for estimating suitable response time
        self.probe_recv_times = []
       
        self.pkt_parser = self.handler.parser_instance()
        self.analyzer = analyzer

        self.last_sent = ''
        self.last_recv = ''

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

    def run(
            self,
            state_path: list[Symbol],
            stop_event: threading.Event
    ):  
        # prepare some settings and setup SUT
        proc = self.pre_exe()
        if proc is None:
            return
        if proc.poll() is not None: 
            out, err = proc.communicate()
            logger.debug(f'SUT Setup Failure:{err}')
            stop_event.set()

        # wait for server setup
        time.sleep(self.setup_time_s)
        sock = self.setup_socket()
        if sock == None:
            logger.debug('Socket Setup Failure' )
            stop_event.set()
        
        # send the message path
        # TODO: symbolize timeout
        for s in state_path:
            msg = s.mapper()

            # send message and parse response
            if(self.net_send(msg, sock)):
                logger.debug(f'sent {s.name}')
                self.last_sent = s.name
                with self.analyzer.lock:
                    self.analyzer.req_num = self.analyzer.req_num + 1

                res = self.net_recv(sock=sock)
                if(self.pkt_parser == None):
                    logger.debug('packet parser: no packet parser')
                    return
                
                # parse response
                if(res):
                    self.last_recv = self.pkt_parser(res)
                    logger.debug(f'recv {self.last_recv}')
                    with self.analyzer.lock:
                        self.analyzer.res_types_update(self.last_recv)
                        self.analyzer.trans_types_update(f'{self.last_sent}-{self.last_recv}')
            else:
                logger.debug('run: socket closed')
                break

        with self.analyzer.lock:
            self.analyzer.path_num = self.analyzer.path_num + 1

        if sock:
            sock.close()
        if proc.poll() is None:
            proc.terminate()

        self.post_exe()
    
    def setup_socket(
            self
    ) -> socket.socket:
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
                    raise ValueError("Unsupport protocol")
            except Exception as e:
                logger.debug(f"Setup Socket Failure {e}")
            
            return sock

    def net_send(
            self, 
            msg : bytes,
            sock: socket.socket
    ):
        """Send message over network

        use poll to monitor the status of socket
        """
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return False
        
        if (self.trans_layer == 'tcp'):

            # use poll to check the status of socket
            poller = select.poll()
            poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)

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
                sock.sendall(msg)
                return True
        
        # TODO: support udp
        elif (self.trans_layer == 'udp'):
            sock.sendto(msg, (self.host, self.port))

        return False
    
    def net_recv(
            self, 
            sock: socket.socket
    ) -> bytes | None:
        """Recv message over network

        use poll to monitor the status of socket
        """

        # check socket before response
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return None
        
        if (self.trans_layer == 'tcp'):

            # use poll to check socket
            poller = select.poll()
            poller.register(sock, select.POLLIN | select.POLLERR | select.POLLHUP)

            # estimate the suitable timeout for recv
            if (self.probe_times > 0):
                s_time = time.time()
                events = poller.poll(self.max_timeout)
                if not events:
                    logger.debug('net recv: time out is too bad')
                    return None
                else:
                    self.probe_times -= 1
                    if (self.probe_times <= 0):
                        # timeout = mean_value + 2 * standard_error
                        mean_time: float = statistics.mean(self.probe_recv_times)
                        std_dev: float = statistics.stdev(self.probe_recv_times)
                        self.recv_time_ms = (mean_time + 2 * std_dev) * 1000
                    else:
                        self.probe_recv_times.append(time.time() - s_time)
            else:
                # recv with estimated timeout 
                events = poller.poll(self.recv_time_ms)

            # handler recv time out
            if not events:
                logger.debug('net recv: timeout')
                return None
            
            fd, event = events[0]
            
            if event & (select.POLLERR | select.POLLHUP):
                logger.debug("net_recv: poll error / hup")
                return None
            # response can be read

            if event & select.POLLIN:
                response = sock.recv(1024)
                if not response:
                    logger.debug('no reply')
                    return None
                else:
                    return response
            
        elif (self.trans_layer == 'udp'):
            response, _ = sock.recvfrom(1024)
            return response
    
        return None