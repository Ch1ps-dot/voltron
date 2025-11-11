from .llm import LLM
from .nio import Nio
from .executor import Executor
import subprocess

class Fuzzer:
    def __init__(self, stype:str, host:str, port:int, sut_path:str,script_path:str = '') -> None:
        self.llm = LLM()
        self.executor = Executor(script_path, sut_path)
        self.nio = Nio(stype, host, port)

    def fuzz_one(self):
        pass
    
    def fuzz_loop(self):
        pass
