import chromadb
import time, pickle
from pprint import pprint
from pathlib import Path
from typing import Self
from .setciontree import SectionTree
from .logger import logger
from ..llm.chat import Chater

class RFCParser:
    """Read protocol specification and parse it to section tree.
    """
    def __init__(
            self, 
            doc_path: Path,
            pro_name: str,
            rfc_id: str
    ) -> None:
        self.doc_path: Path = doc_path
        self.doc_file = doc_path.open('r+', encoding='utf-8')
        self.doc_content: str = self.doc_file.read()
        self.pro_name = pro_name
        self.rfc_id = rfc_id

        # initialize the sectiontree which stands for the section structure of documents
        start = time.perf_counter()    
        self.st = SectionTree(id='', content=self.doc_content)
        end = time.perf_counter()
        logger.debug(f"[ST init]: cost time:{end - start}")

        # initialize the vectordatabase
        # self.chroma_client = chromadb.Client()
        # self.chroma_collection = self.chroma_client.get_or_create_collection(name="RFC_collection")
        # self.db_create()

    def db_create(
            self
    ):
        pass

    






    
