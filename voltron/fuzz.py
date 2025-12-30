from .configs import ftp
import yaml
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
            pro_name:str
        ) -> None:

        with open('configs.yaml', 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # key parameter of protocol
        self.pro_name = pro_name
        self.host = self.config[pro_name]['host']
        self.trans = self.config[pro_name]['trans'] # transport layer
        self.port = self.config[pro_name]['port']
        self.rfc_name = self.config[pro_name]['rfc_name']

        # some file path 
        self.pre_script = Path.cwd() / 'scripts' / self.rfc_name / 'pre.sh'
        self.post_script = Path.cwd() / 'scripts' / self.rfc_name / 'post.sh'
        self.doc_path = Path.cwd() / 'rfcs' / f'{self.rfc_name}.txt'
        self.pmp_path = Path.cwd() / 'prompts'

        self.module_init()

    def module_init(
            self
    ) -> None:

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

        # setup executor
        self.exe = Executor(
            trans_layer=self.trans,
            host=self.host,
            port=self.port,
            pre_script=self.pre_script,
            post_scaript=self.post_script,
            handler=self.handler
        )

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
  


        

