import re
import chromadb
from pprint import pprint
from pathlib import Path

class RAGRfc:
    def __init__(self, doc_path: Path) -> None:
        self.doc_path = doc_path
        self.doc_file = doc_path.open('r+', encoding='utf-8')
        self.doc_content = ''.join([line for line in self.doc_file.readlines() if not line.isspace()])

        self.chroma_client = chromadb.Client()
        self.chroma_collection = self.chroma_client.get_or_create_collection(name="RFC_collection")
        self.pages: list
        self.db_create()

    def pages_split(self, doc_content):
        """Split the documents by page
        Args:
            doc_content: original RFC documents.
        Returns:
            pages: splitted page.
        """

        # match and split documents by string "[Page Number]"
        pattern = re.compile(r'\[Page \d+\]', re.IGNORECASE) 
        pages = pattern.split(doc_content)
        return pages

    def _section_helper():
        pass


    def section_split(self, pages):
        """Split the documents by section
        Args:
            pages: splited pages of documents
        Returns:
            sections: sections of documents
        """
        sections = dict()
        for p in pages:
            pattern = re.compile(r'', )

        return sections

    def db_create(self):
        
    
        self.chroma_collection.upsert(
            ids = [str(i) for i in range(len(self.pages))],
            documents= self.pages
        )

        return self.chroma_collection

    def output_readable(self):
        content = self.doc_file.readlines()
        for i in range(len(content)):
            if (content[i].isspace()): continue
            pprint(content[i])

    def output_raw(self):
        content = self.doc_file.readlines()
        print(content)

    def output_pages(self):
        self.db_create()
        print(len(self.pages))
        for i in range(len(self.pages)):
            print(f'===============NUMBER: {i}================')
            pprint(self.pages[i])

    def db_query(self, txts:str):
        results = self.chroma_collection.query(
            query_texts=txts,
            n_results=5
        )
        return results['documents']