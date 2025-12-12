from llm.chat import Chater
from voltron.utils.rfcparser import RFCParser
from utils.logger import logger
from nio import Nio
from executor import Executor
from pathlib import Path
import os, pickle

class Fuzzer:
    def __init__(self, stype:str, host:str, port:int, sut_path:str,script_path:str = '') -> None:
        self.llm_init(doc_path='../tests/docs/rfc9110.txt')

    def fuzz_one(self):
        pass
    
    def fuzz_loop(self):
        pass

    def llm_init(
            self,
            doc_path:str
    ):
        self.chater = Chater(Path(doc_path).resolve())
        

