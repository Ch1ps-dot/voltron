from .llm.chat import Chater
from .rfcparser.rfcparser import RFCParser
from .rfcparser.setciontree import SectionTree
from .utils.logger import logger
from .executor.nio import Nio
from .executor.executor import Executor
from .sheduler.alphabet import Alphabet, Symbol
from .handler.handler import Handler

from pathlib import Path
import os, pickle, json

class Fuzzer:
    def __init__(
            self, 
            stype:str, 
            host:str, 
            port:int, 
            pro_name:str,
            rfc_name:str, # TODO: this fields is useless
            sut_path:Path = Path.cwd(),
            pmp_path:Path = Path.cwd() / 'prompts',
            doc_path:Path = Path.cwd() / 'tests' / 'docs',
            script_path:Path = Path.cwd()
        ) -> None:

        # key parameter of protocol
        self.host = host
        self.stype = stype
        self.port = port
        self.pro_name = pro_name
        self.rfc_name = rfc_name

        # some file path 
        self.sut_path = sut_path
        self.script_path = script_path
        self.doc_path = doc_path
        self.pmp_path = pmp_path

        self.module_init()

    def module_init(
            self
    ) -> None:
        
        # network I/O init
        self.nio = Nio(
            stype = self.stype,
            host=self.host,
            port=self.port
        )

        # llm init
        self.chater = Chater(self.pmp_path)

        # ir generation
        self.rfcparser = RFCParser(
            doc_path=self.doc_path,
            pro_name=self.pro_name,
            chater=self.chater,
            rfc_name = self.rfc_name
        )

        # handler generation
        self.handler = Handler(
            chater=self.chater,
            rfcp=self.rfcparser
        )
        

    def fuzz_one(
            self
    ):
        """Fuzz the target one
        """
        pass
    
    def fuzz_loop(self):
        pass
  


        

