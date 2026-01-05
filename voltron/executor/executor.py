import subprocess
from pathlib import Path
import time, select, socket

from .nio import Nio
from ..utils.logger import logger
from ..sheduler.alphabet import Symbol, Alphabet
from ..handler.handler import Handler
from ..utils.analyze import Analyzer
import math, statistics

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path | None, 
            post_script:Path | None,
            handler: Handler,
            analyzer: Analyzer,
            setup_time_s:float = 0.1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.pre_script = pre_script
        self.post_script = post_script
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

    def post_exe(self):
        if (self.post_script != None):
            try:
                subprocess.run(
                    [self.post_script],
                    check = True,
                    shell = False
                )
            except Exception as e:
                logger.debug(f'Reset Failure: {e}')

    def pre_exe(
            self,
    ) -> subprocess.Popen | None:
        if (self.pre_script != None):
            try:
                process = subprocess.Popen(
                    [self.pre_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return process
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')

    def run(
            self,
            path: list[Symbol]
    ):  
        # prepare some settings and setup SUT
        self.pre_exe()
        sock = self.setup_socket()
        
        # wait for server setup
        time.sleep(self.setup_time_s)

        # send the message path
        # TODO: symbolize timeout
        for s in path:
            msg = s.inst

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
        if sock is None:
            sock.close()
        self.post_exe()
    
    def setup_socket(
            self
    ) -> socket.socket:
            """Setup the socket for network communication

            Args:
                trans: socket type is tcp or udp.
                host: host name.
                port: port number.
            
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
            
        elif (self.trans_layer == 'udp'):
            response, _ = sock.recvfrom(1024)
            return response
    
        return None