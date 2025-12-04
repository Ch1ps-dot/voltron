import chromadb
import time
from pprint import pprint
from pathlib import Path
from typing import Self
from .setciontree import SectionTree
from .logger import logger

class RFCRag:
    """Reslove document and contruct RAG database
    """
    def __init__(
            self, 
            doc_path: Path
    ) -> None:
        self.doc_path: Path = doc_path
        self.doc_file = doc_path.open('r+', encoding='utf-8')
        self.doc_content: str = self.doc_file.read()

        # initialize the sectiontree which stands for the section structure of documents
        start = time.perf_counter()    
        self.st = SectionTree(id='', content=self.doc_content)
        end = time.perf_counter()
        logger.debug(f"\n[ST init]: \n cost time:{end - start}")

        # initialize the vectordatabase
        # self.chroma_client = chromadb.Client()
        # self.chroma_collection = self.chroma_client.get_or_create_collection(name="RFC_collection")
        # self.db_create()

    def db_create(
            self
    ):
        pass



    
