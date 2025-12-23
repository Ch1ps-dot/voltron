from .llm.chat import Chater
from .rfcparser.rfcparser import RFCParser
from .rfcparser.setciontree import SectionTree
from .utils.logger import logger
from .nio.nio import Nio
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
            rfc_name:str,
            sut_path:Path = Path(''),
            pmp_dir:Path = Path('./prompts').resolve(),
            doc_path:Path = Path('./tests/docs').resolve(),
            script_path:Path = Path('')
        ) -> None:

        # key parameter of fuzzer
        self.host = host
        self.stype = stype
        self.port = port
        self.pro_name = pro_name
        self.rfc_name = rfc_name

        self.sut_path = sut_path
        self.script_path = script_path
        self.doc_path = doc_path
        self.ir_path = Path.cwd() / 'ir'

        # key parameter of ir generation
        self.st: SectionTree
        self.rfcparser: RFCParser
        self.req: list
        self.res: list
        self.alphabet: Alphabet
        self.req_doc: list
        self.res_doc: list


        # network I/O init
        self.nio = Nio(
            stype = stype,
            host=host,
            port=port
        )

        # llm init
        self.chater = Chater(Path(pmp_dir).resolve())

        # ir generation
        self.rfcparser = RFCParser(
            Path(self.doc_path).resolve(),
            pro_name=self.pro_name,
            chater=self.chater,
            rfc_name = self.rfc_name
        )
        self.st = self.rfcparser.st

        self.res_ir = self.rfcparser.res_ir
        self.req_ir = self.rfcparser.req_ir

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
  


        

