from llm.chat import Chater
from utils.rag import RFCAgent
from utils.logger import logger
from nio import Nio
from executor import Executor
from pathlib import Path
import subprocess

class Fuzzer:
    def __init__(self, stype:str, host:str, port:int, sut_path:str,script_path:str = '') -> None:
        self.chater = Chater(Path('../tests/docs/rfc9110.txt').resolve())
        self.executor = Executor(script_path, sut_path)
        self.nio = Nio(stype, host, port)

    def fuzz_one(self):
        pass
    
    def fuzz_loop(self):
        pass
