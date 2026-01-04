import subprocess
from pathlib import Path
import time, select, socket

from .nio import Nio
from ..utils.logger import logger
from ..sheduler.alphabet import Symbol, Alphabet
from ..handler.handler import Handler
from ..utils.analyze import Analyzer

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path, 
            post_scaript:Path,
            handler:Handler,
            setup_time_s:float = 0.1,
            recv_time_ms:int = 1000 
        ) -> None:

        self.pre_script = pre_script
        self.post_script = post_scaript
        self.host = host
        self.port = port

        self.trans_layer = trans_layer
        self.handler = handler

        self.setup_time_s = setup_time_s
        self.recv_time_ms = recv_time_ms
       
        self.pkt_parser = self.handler.parser_instance()
        self.analyzer = Analyzer()

    def reset_sut(self):
        try:
            subprocess.run(
                [self.post_script.resolve()],
                check = True,
                shell = False
            )
        except Exception as e:
            print(f'Reset Failure: {e}')

    def setup_sut(
            self,
    ) -> subprocess.Popen | None:
        try:
            process = subprocess.Popen(
                [self.pre_script.resolve()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return process
        except Exception as e:
            logger.debug(f'[SUT Execution Failure]: {e}')

    def run(
            self,
            path: list[Symbol]
    ):
        sut = self.setup_sut()
        sock = self.setup_socket()
        poller = select.poll()
        poller.register(sock, select.POLLIN)
        events = poller.poll(self.recv_time_ms)
        
        # wait for server setup
        time.sleep(self.setup_time_s)

        if sut != None:
            for s in path:
                msg = s.inst()
                self.net_send(msg, sock)
                res = self.net_recv(timeout_ms=self.recv_time_ms, sock=sock)
                if(self.pkt_parser != None):
                    logger.debug(self.pkt_parser(res))
            sock.close()
            sut.terminate()
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
                print("Setup Socket Failure")
            
            return sock

    def net_send(
            self, 
            msg : bytes,
            sock: socket.socket
    ):
        try:
            if (self.trans_layer == 'tcp'):
                sock.sendall(msg)
            elif (self.trans_layer == 'udp'):
                sock.sendto(msg, (self.host, self.port))
            else:
                raise ValueError("Unsupport protocol")
        except Exception as e:
            print(f'Network Send Failure: {e}')
    
    def net_recv(
            self, 
            timeout_ms: int,
            sock: socket.socket
    ):
        try:
            if (self.trans_layer == 'tcp'):
                response = sock.recv(1024)
            elif (self.trans_layer == 'udp'):
                response = sock.recvfrom(1024)
            else:
                raise ValueError("Unsupport protocol")
        except Exception as e:
            print(f'Network Recv Failure: {e}')
        
        return response