from .configs import settings
from .utils.logger import logger

from .llm.chat import Chater

from .rfcparser.rfcparser import RFCParser
from .rfcparser.setciontree import SectionTree

from .handler.handler import Handler

from .executor.executor import Executor

from .sheduler.alphabet import Alphabet, Symbol
from .sheduler.rands import Rands

from pathlib import Path
import os, pickle, json

class Fuzzer:
    def __init__(
            self, 
            trans:str, 
            host:str, 
            port:int, 
            pro_name:str,
            rfc_name:str, # TODO: this fields is useless
            sut_path:Path = Path.cwd(),
            pmp_path:Path = Path.cwd() / 'prompts',
            doc_path:Path = Path.cwd() / 'rfcs',
            script_path:Path = Path.cwd()
        ) -> None:

        # key parameter of protocol
        self.host = host
        self.trans = trans # transport layer
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
        self.exe = Executor(
            trans_layer=self.trans,
            host=self.host,
            port=self.port,
            pre_script=Path.cwd(),
            post_scaript=Path.cwd()
        )

        # llm init
        self.chater = Chater(self.pmp_path)

        # rfcparser init
        self.rfcparser = RFCParser(
            doc_path=self.doc_path,
            pro_name=self.pro_name,
            chater=self.chater,
            rfc_name = self.rfc_name
        )

        # handler init
        self.handler = Handler(
            chater=self.chater,
            rfcp=self.rfcparser
        )

        # scheduler init
        self.alphabet = Alphabet(self.handler)

    def fuzz(
            self,
            algo:str
    ):
        """Fuzz the target one
        """
        match algo:
            case 'rand':
                sched = Rands(self.alphabet)
                path = sched.select(10)
                self.exe.run(path=path)
    
    def fuzz_loop(self):
        pass
  


        

