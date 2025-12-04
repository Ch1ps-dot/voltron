import socket
from typing import Optional

class Nio:
    """ Network sender and receiver

    Attributte:
        stype: socket type. tcp or udp.
        host: host name 
        port port number
    """
    def __init__(
            self, 
            stype:str, 
            host:str, 
            port:int
    ) -> None:
        self.stype:str = stype
        self.host:str = host
        self.port:int = port
        self.skt:socket.socket = self.setup_socket(stype, host, port)

    def setup_socket(
            self, 
            stype:str, 
            host:str, 
            port:int
    ) -> socket.socket:
            """Setup the socket for network communication

            Args:
                stype: socket type is tcp or udp.
                host: host name.
                port: port number.
            
            Returns:
                socket for sending and receiving
            """
            skt: socket.socket
            try:
                if (stype == 'tcp'):
                    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    skt.connect((host, port))
                elif (stype == 'udp'):
                    skt = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                else:
                    raise ValueError("Unsupport protocol")
            except Exception as e:
                print("Setup Socket Failure")
            
            return skt

    def net_send(
            self, 
            msg
    ):
        try:
            if (self.stype == 'tcp'):
                self.skt.sendall(msg)
            elif (self.stype == 'udp'):
                self.skt.sendto(msg, (self.host, self.port))
            else:
                raise ValueError("Unsupport protocol")
        except Exception as e:
            print('Network Send Failure')
    
    def net_recv(
            self
    ):
        try:
            if (self.stype == 'tcp'):
                response = self.skt.recv(1024)
            elif (self.stype == 'udp'):
                response = self.skt.recvfrom(1024)
            else:
                raise ValueError("Unsupport protocol")
        except Exception as e:
            print('Network Recv Failure')
        
        return response