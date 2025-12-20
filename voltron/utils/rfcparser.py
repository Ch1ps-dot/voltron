import chromadb
import time, pickle
from pprint import pprint
from pathlib import Path
from typing import Self
from .setciontree import SectionTree
from .logger import logger
from ..llm.chat import Chater
from ..sheduler.alphabet import Alphabet, Symbol 
import json

class RFCParser:
    """Read protocol specification and parse it to section tree.
    """
    def __init__(
            self, 
            doc_path: Path,
            pro_name: str,
            rfc_name: str,
            chater: Chater,
            ir_path: Path = Path.cwd()
    ) -> None:
        self.chater =chater

        # doc related value
        self.doc_path: Path = doc_path
        self.doc_file = doc_path.open('r+', encoding='utf-8')
        self.doc_content: str = self.doc_file.read()
        self.pro_name = pro_name
        self.rfc_name = rfc_name

        # initialize the sectiontree which stands for the section structure of documents 
        self.st = SectionTree(id='', content=self.doc_content)

        # ir related value
        self.req: list
        self.res: list
        self.alphabet: Alphabet
        self.req_doc: list = []
        self.res_doc: list = []
        self.ir_path = ir_path

        # sectiontree parse pass
        fn = self.ir_path / "section_tree.pkl"
        if(fn.is_file()):
            self.load_st()
            self._query_prepare()
        else:
            self.spe_parse()
            self._query_prepare()

        # ir generation
        self.ir_generation()
        

    def _query_prepare(
            self
    ):
        """Prepare content for ir generation
        """
        for node in self.st.leafs:
            match node.content_type:
                case "request":
                    self.req_doc.append(self.st.fetch_node_content(node))
                case "response":
                    self.res_doc.append(self.st.fetch_node_content(node))
                case "all":
                    self.req_doc.append(self.st.fetch_node_content(node))
                    self.res_doc.append(self.st.fetch_node_content(node))
                case "none":
                    pass
                case _:
                    logger.debug("[Section type]: unexpected type {_}")

    def spe_parse(
            self
    ):
        """Workflow of specification parse
        """

        # determine the content type of each section
        """Return four different types
        1. request
        2. response
        3. all
        4. none
        """
        for node in self.st.leafs:
            doc = self.st.fetch_node_content(node)
            ans = ''
            if doc != None:
                ans = self.chater.llm_doc_parse(
                    rfc_num = self.rfc_name,
                    pro_name = self.pro_name,
                    rfc_doc = doc
                )
                if ans != None:
                    node.content_type = ans
                    
        self.save_st()           
    
    def ir_generation(
            self
    ):
        """Workflow of IR generation
        """

        """
            key field format
            [
                {
                    "field_name": "",
                    "position": "",
                    "explanation": "",
                    "value": []
                }
                ...
            ]
        """
        
        """Key field parse"""
        req_path = self.ir_path / 'req.json'
        res_path = self.ir_path / 'res.json'

        # request field extraction
        if(req_path.is_file()):
            with open(req_path, 'wb') as f:
                self.req = json.load(f)
        else:
            req_json = self.chater.llm_request_query(
                rfc_num = self.rfc_name,
                pro_name = self.pro_name,
                rfc_doc = ''.join([s for s in self.req_doc])
            )

            if (req_json != None):
                self.req = json.loads(req_json[7:-4])
                logger.debug(self.req)
                with open(req_path, 'wb', encoding='utf-8') as f:
                    json.dump(self.req, f)

        # response field extraction
        if(res_path.is_file()):
            with open(res_path, 'wb') as f:
                self.res = json.load(f)
        else:
            res_json = self.chater.llm_response_query(
                rfc_num = self.rfc_name,
                pro_name = self.pro_name,
                rfc_doc = ''.join([s for s in self.res_doc])
            )

            if (res_json != None):
                self.res = json.loads(res_json[7:-4])
                logger.debug(self.res)
                with open(res_path, 'wb', encoding='utf-8') as f:
                    json.dump(self.res, f)

        # ir generation

        req_ir_path =  self.ir_path / 'xml'

    def load_st(
            self
    ):
        """Load rfc parser 
        """
        with open(self.ir_path / "section_tree.pkl", "rb") as f:
            self.st = pickle.load(f)  
        

    def save_st(
            self
    ):
        """Use pickle to store section tree instance
        """
        with open(self.ir_path / "section_tree.pkl", "wb") as f:
            pickle.dump(self.st, f)  

    def db_create(
            self
    ):
        pass

    






    
