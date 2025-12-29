import subprocess
from pathlib import Path

from .nio import Nio
from ..utils.logger import logger
from ..sheduler.alphabet import Symbol, Alphabet

class Executor:
    def __init__(
            self,
            trans_layer:str, 
            host:str, 
            port:int,
            pre_script:Path, 
            post_scaript:Path
        ) -> None:

        self.pre_script = pre_script
        self.post_script = post_scaript
        self.host = host
        self.port = port

        self.trans_layer = trans_layer

        self.nio = Nio(
            trans=trans_layer,
            host=host,
            port=port
        )

    def reset_sut(self):
        try:
            subprocess.run(
                [self.post_script],
                check = True,
                shell = False
            )
        except Exception as e:
            print('Reset Failure')

    def setup_sut(self, args:list = []):
        try:
            subprocess.Popen(
                args = args,
                shell=False
            )
        except Exception as e:
            print('SUT Execution Failure')

    def run(
            self,
            path: list[Symbol]
    ):
        for s in path:
            logger.debug(s.inst())