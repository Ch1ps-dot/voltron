from .llm.chat import Chater
from .utils.rfcparser import RFCParser
from .utils.setciontree import SectionTree
from .utils.logger import logger
from .nio.nio import Nio
from .executor.executor import Executor

from pathlib import Path
import os, pickle

class Fuzzer:
    def __init__(
            self, 
            stype:str, 
            host:str, 
            port:int, 
            pro_name:str,
            sut_path:Path = Path(''),
            pmp_dir:Path = Path('./prompts').resolve(),
            doc_path:Path = Path('./tests/docs').resolve(),
            script_path:Path = Path('')
        ) -> None:

        # init some key parameter
        self.host = host
        self.stype = stype
        self.port = port
        self.pro_name = pro_name

        self.sut_path = sut_path
        self.script_path = script_path
        self.doc_path = doc_path

        self.st: SectionTree
        self.rfcparser: RFCParser


        # network I/O init
        self.nio = Nio(
            stype = stype,
            host=host,
            port=port
        )

        # llm init
        self.chater = Chater(Path(pmp_dir).resolve())

        # specification parse
        self.spe_parse()

        # ir generation
        self.ir_generation()

    def fuzz_one(
            self
    ):
        """Fuzz the target one time
        """
        pass
    
    def fuzz_loop(self):
        pass

    def spe_parse(
            self
    ):
        """Workflow of specification parse
        """
        # section tree construct
        self.rfcparser = RFCParser(
            Path(self.doc_path).resolve(),
            pro_name=self.pro_name,
            rfc_id=''
        )
        self.st = self.rfcparser.st

        # section tree parse
        for node in self.st.leafs:
            
            doc = self.st.fetch_node_content(node)
            ans = ''
            if doc != None:
                ans = self.chater.llm_doc_parse(
                    rfc_num = self.rfcparser.rfc_id,
                    pro_name = self.rfcparser.pro_name,
                    rfc_doc = doc
                )
                if ans != None:
                    node.content_type = ans
                    logger.debug(f'[SPE_PARSE]:{ans} {node.name}')           
    
    def ir_generation(
            self
    ):
        """Workflow of IR generation
        """
        
        # key field query

        # type query

        # section tree decoration

        # ir generation

    def save_parser(
            self,
            save_path: Path = Path.cwd()
    ):
        """Use pickle to store section tree instance
        """
        with open("section_tree.pkl", "wb") as f:
            pickle.dump(self.st, f)  


        

