from voltron.executor.executor import Executor, Conversation
from pathlib import Path
import socket, pickle, select, click
from voltron.configs import configs

class Relayer:
    def __init__(
        self,
        path: Path,
        target: str
    ) -> None:
        self.cons: Conversation = self.load_cons(path)
        self.trans_layer = configs[target]['trans_layer']
        self.host = configs[target]['host']
        self.port = configs[target]['port']
        self.max_timeout_ms = 5000
        self.send_time_ms = 1000
        self.sock = self.setup_socket()
    
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
                print(e)
                return None
            sock.setblocking(False)
            return sock
        
    def communicate(
        self
    ):
        if self.sock == None: return
        for msg in self.cons.content:
            if msg[0]:
                self.net_send(msg[0], self.sock)
                self.net_recv(self.sock)
        
    def load_cons(
        self,
        path: Path
    ) -> Conversation:
        with open(path, 'rb') as f:
            cons = pickle.load(f)
            return cons
            
    def net_send(
            self, 
            msg : bytes,
            sock: socket.socket
    ):
        """Send message over network

        use poll to monitor the status of socket
        """
        if sock is None or sock.fileno() < 0:
            return False
        
        poller = select.poll()
        poller.register(sock, select.POLLOUT | select.POLLERR | select.POLLHUP)
        try:
            if (self.trans_layer == 'tcp'):
                # handler poll timeout
                events = poller.poll(self.send_time_ms)
                if not events:
                    return False
                fd, event = events[0]
                # handler poll error and hup
                if event & (select.POLLERR | select.POLLHUP):
                    return False
                # send message
                if event & select.POLLOUT:
                    sock.sendall(msg)
                    return True
        
            # TODO: support udp
            elif (self.trans_layer == 'udp'):
                sock.sendto(msg, (self.host, self.port))
        finally:
            poller.unregister(sock)

        return False
    
    def net_recv(
            self, 
            sock: socket.socket
    ):
        """Recv message over network

        use poll to monitor the status of socket
        """
        # check clinet socket before response
        if sock is None or sock.fileno() < 0:
            return None, None
        poller = select.poll()
        poller.register(sock, select.POLLIN | select.POLLERR)
        
        try:
            if (self.trans_layer == 'tcp'):
                events = poller.poll(self.max_timeout_ms)
                if not events:
                    return None
                fd, event = events[0]
                if event & (select.POLLERR):
                    return None
                # response can be read
                if event & select.POLLIN:
                    buf = sock.recv(1024)     
                    # if buf size is 0, socket close
                    if len(buf) == 0:
                        return None
                    else:
                        # recv response and parse it        
                        return buf
                
            elif (self.trans_layer == 'udp'):
                buf, _ = sock.recvfrom(1024)
                return buf
            
        finally:
            poller.unregister(sock)
    
        return None, None
    

@click.command()
@click.option(
    "--file-path", 
    "-f", 
    required=True, 
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="conversation path"
)
@click.option(
    "--target",  
    "-t",  
    required=True, 
    type=str,
    help="target name"
)
def main(file_path: Path, target: str):
    try:
        # 初始化Relayer实例
        relayer = Relayer(path=file_path, target=target)
        # 执行报文收发逻辑
        relayer.communicate()
        print("communicate success")
    except Exception as e:
        print(f"execution error {e}")
        exit(1)
        
if __name__ == '__main__':
    main()