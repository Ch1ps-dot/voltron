import subprocess
from pathlib import Path

from .nio import Nio
from ..utils.logger import logger
from ..sheduler.alphabet import Symbol, Alphabet
from ..handler.handler import Handler

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path, 
            post_scaript:Path,
            handler:Handler
        ) -> None:

        self.pre_script = pre_script
        self.post_script = post_scaript
        self.host = host
        self.port = port

        self.trans_layer = trans_layer
        self.handler = handler

        self.nio = Nio(
            trans=trans_layer,
            host=host,
            port=port
        )
       
        self.pkt_parser = self.handler.parser_instance()

    def reset_sut(self):
        try:
            subprocess.run(
                [self.post_script],
                check = True,
                shell = False
            )
        except Exception as e:
            print(f'Reset Failure: {e}')

    def setup_sut(
            self,
    ):
        process = None
        try:
            process = subprocess.Popen(
                [self.pre_script.resolve()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f'[SUT Execution Failure]: {e}')
        return process

    def run(
            self,
            path: list[Symbol]
    ):
        process = self.setup_sut()
        if process != None:
            for s in path:
                try:
                    msg = s.inst()
                    if msg != None:
                        self.nio.net_send(msg)
                        res = self.nio.net_recv()
                        if(self.pkt_parser != None):
                            logger.debug(self.pkt_parser(res))
                except Exception as e:
                    logger.debug(f'[Executor]: {e}')
                    self.reset_sut()
            process.terminate()
        self.reset_sut()