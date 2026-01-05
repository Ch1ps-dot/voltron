import subprocess
from pathlib import Path
import time, select, socket

from .nio import Nio
from ..utils.logger import logger
from ..sheduler.alphabet import Symbol, Alphabet
from ..handler.handler import Handler
from ..utils.analyze import Analyzer
import math

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path | None, 
            post_scaript:Path | None,
            handler: Handler,
            analyzer: Analyzer,
            setup_time_s:float = 0.1,
            send_time_ms:int = 1000,
            recv_time_ms:int = 1000
        ) -> None:

        # some attributes for sut
        self.pre_script = pre_script
        self.post_script = post_scaript
        self.host = host
        self.port = port

        self.trans_layer = trans_layer
        self.handler = handler

        # time related values
        self.setup_time_s = setup_time_s
        self.recv_time_ms = -1
        self.send_time_ms = send_time_ms
        
        self.max_timeout = 5000
        self.time_probe = 3 # for estimating suitable response time
       
        self.pkt_parser = self.handler.parser_instance()
        self.analyzer = analyzer

        self.last_sent = ''
        self.last_recv = ''

    def reset_sut(self):
        if (self.post_script != None):
            try:
                subprocess.run(
                    [self.post_script.resolve()],
                    check = True,
                    shell = False
                )
            except Exception as e:
                logger.debug(f'Reset Failure: {e}')
            logger.debug('SUT Reset Execution Success')

    def setup_sut(
            self,
    ) -> subprocess.Popen | None:
        if (self.pre_script != None):
            try:
                process = subprocess.Popen(
                    [self.pre_script.resolve()],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return process
            except Exception as e:
                logger.debug(f'[SUT Setup Failure]: {e}')
            logger.debug('SUT Setup Success')

    def run(
            self,
            path: list[Symbol]
    ):
        self.setup_sut()
        sock = self.setup_socket()
        
        # wait for server setup
        time.sleep(self.setup_time_s)

        for s in path:
            msg = s.inst
            if(self.net_send(msg, sock)):
                logger.debug(f'sent {s.name}')
                self.last_sent = s.name
                with self.analyzer.lock:
                    self.analyzer.req_num = self.analyzer.req_num + 1

                res = self.net_recv(sock=sock)
                if(self.pkt_parser == None): raise Exception
                if(res != False):
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
        self.reset_sut()
    
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
        
        try:
            if (self.trans_layer == 'tcp'):
                poller = select.poll()
                poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)

                events = poller.poll(self.send_time_ms)
                if not events:
                    logger.debug("net_send: poll timeout")
                    return False

                fd, event = events[0]

                if event & (select.POLLERR | select.POLLHUP):
                    logger.debug("net_send: poll error / hup")
                    return False

                if event & select.POLLOUT:
                    sock.sendall(msg)
                    return True
                
            elif (self.trans_layer == 'udp'):
                sock.sendto(msg, (self.host, self.port))
            else:
                raise ValueError("Unsupport protocol")
        except Exception as e:
            logger.debug(f'Network Send Failure: {e}')
        logger.debug(f'send {msg}')
        return False
    
    def net_recv(
            self, 
            sock: socket.socket
    ):
        """Recv message over network

        use poll to monitor the status of socket
        """
        response = ''
        if sock is None or sock.fileno() < 0:
            logger.debug("net_send: invalid socket")
            return False
        
        try:
            if (self.trans_layer == 'tcp'):
                poller = select.poll()
                poller.register(sock, select.POLLIN)
                if (self.time_probe > 0):
                    s_time = time.time()
                    events = poller.poll(self.max_timeout)
                    if not events:
                        logger.debug('net recv: time out is too bad')
                        return False
                    else:
                        self.time_probe -= 1
                        if (self.recv_time_ms < 0):
                            self.recv_time_ms = int(1000*(time.time()-s_time))
                        else:
                            self.recv_time_ms = math.floor((self.recv_time_ms + int(1000*(time.time()-s_time))) / 2)
                else:
                    events = poller.poll(self.recv_time_ms)

                if not events:
                    logger.debug('net recv: time out')
                    return False

                fd, event = events[0]
                if event & select.POLLIN:
                    response = sock.recv(1024)
                    if not response:
                        logger.debug('no reply')
                        return False
                
            elif (self.trans_layer == 'udp'):
                response = sock.recvfrom(1024)
                return response
        except Exception as e:
            logger.debug(f'Network Recv Failure: {e}')
        
        return False