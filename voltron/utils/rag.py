import re
import chromadb
from pprint import pprint
from pathlib import Path
from typing import Self

class SectionNode:
    """Structure of Section Node

    Attributes:
        name: name of section
        subsection: list of name of subsection
        depth: depth of current section
        start: start point of section in documents
        end: end point of section in documents
    """
    def __init__(
            self, 
            name: str, 
            depth: int, 
            start: int,
            end: int
    ) -> None:
        self.name = name
        self.subsection = []
        self.start = start
        self.end = end
        self.depth = depth

    def add_subsection(
            self, 
            node: Self
    ) -> None:
        """Add subsection to current section
        
        Args:
            name: name of subsection
        """
        self.subsection.append(node)

    # TODO
    def is_sub(
            self,
            name: str
    ) -> bool:
        return name in self.subsection
        

class SectionTree:
    """Structure of Section Tree

    Attributes:
        id: identification of documents
        height: the height of tree
        tree: a list of dict which store the Name and SectionNode, the index of dict is also the depth of section.
    """
    def __init__(
            self, 
            id: str = ''
    ) -> None:
        self.tree: list[dict[str, SectionNode]] = [{'root' : SectionNode('root', 0, 0, 0)}]
        self.height = 0
        self.toc = 0
        self.id = id

    def add_section(self, node: SectionNode):
        if(node.depth > self.height): 
            self.height += 1
            self.tree.append({})
        self.tree[node.depth][node.name] = node

    def fetch_node(
            self, 
            level: int, 
            name: str
    ) -> SectionNode:
        return self.tree[level][name]

    def fetch_layer(self, depth):
        return self.tree[depth]
    

    def output_node(
            self,
            node: SectionNode | None
    ) -> None:
        if (node == None): return
        print(node.name)
        if(node.subsection != []):
            for n in node.subsection:
                self.output_node(n)

    def output_tree(self):
        if self.height == 0: return 
        self.output_node(self.tree[0]['root'])

class RFCAgent:
    """reslove document and contruct RAG database
    """
    def __init__(
            self, 
            doc_path: Path
    ) -> None:
        self.doc_path: Path = doc_path
        self.doc_file = doc_path.open('r+', encoding='utf-8')
        self.doc_content: str = ''.join([line for line in self.doc_file.readlines() if not line.isspace()])
        self.doc_pages: list | None = self.pages_split(self.doc_content)

        ans = self.toc_extract(self.doc_content)
        if ans != None:
            self.doc_toc: str = ans['toc']
            self.rest_content = ans['rest']

        # self.chroma_client = chromadb.Client()
        # self.chroma_collection = self.chroma_client.get_or_create_collection(name="RFC_collection")
        # self.db_create()

    def pages_split(
            self, 
            doc_content: str
    ) -> list | None:
        """Split the documents by page
        Args:
            doc_content: original RFC documents.
        Returns:
            pages: splitted page.
        """

        # match and split documents by string "[Page Number]"
        pattern = re.compile(r'\[Page \d+\]', re.IGNORECASE) 
        if pattern.match(doc_content):
            pages = pattern.split(doc_content)
            return pages
        else:
            return None

    def toc_extract(
            self, 
            doc_content: str
    ) -> dict[str, str] | None:
        """extact table of cantent from documents
        Args:
            doc_content: content of documents
        Returns:
            A dict contains table of content and rest part of the document
        """
        pattern_toc = re.compile('Table of Contents', re.IGNORECASE)
        toc = pattern_toc.search(doc_content)
        if toc:
            toc_start = toc.start()

            toc_end = 0
            content_start = 0
            pattern_itr = re.compile('INTRODUCTION', re.IGNORECASE)
            itr = pattern_itr.finditer(doc_content)
            cnt = 0
            for m in itr:
                if cnt == 1: 
                    toc_end = m.start() - 5
                    content_start = m.start() - 5
                    break
                cnt += 1
            doc_toc = doc_content[toc_start:toc_end]
            return {"toc": doc_toc, "rest": doc_content[:toc_start] + doc_content[content_start:]}
        else:
            return None


    def _section_helper(
            self, 
            level: int, 
            start: int,
            end: int,
            content: str,
            sections: SectionTree,
            upper: str = ''
    ):
        """Help function to construct section tree

        use regrex to find the different level of sections.
        """
        reg = r'^(?<!\S)' + r'\d+\.'*level + r'\s+.*'
        pattern = re.compile(reg, re.MULTILINE)
        

        # early return for not matching
        if pattern.findall(content[start:end]) == []: return None

        section_start = 0
        name = ''
        section_end = 0

        for s in pattern.finditer(content[start:end]):
            section_end = s.start()

            # skip first round because we dont know the end of section
            if start == 0:
                name = s.group() 
                continue

            node = SectionNode(name, level, section_start, section_end)

            # add section to SectionTree and upper SectionNode
            sections.add_section(node)
            if upper:
                upper_node = sections.fetch_node(level - 1, upper)
                upper_node.add_subsection(node)
            
            # recursively resolve subsection
            self._section_helper(
                level+1, 
                section_start, 
                section_end,
                content,
                sections,
                name
            )
            # iterate the index and section name
            name = s.group()
            section_start = section_end

        # store the last one node
        node = SectionNode(name, level, section_start, end)
        sections.add_section(node)
        if upper:
            upper_node = sections.fetch_node(level - 1, upper)
            upper_node.add_subsection(node)
        self._section_helper(
                level+1, 
                section_start, 
                section_end,
                content,
                sections,
                name
            )

    def section_split(
            self, 
            doc_content: str
    ) -> SectionTree | None:
        """Split the documents by section
        Args:
            doc_content: content of documents
        Returns:
            sections: SectionTree of documents
        """

        # extract [table of contents] if it exists then resolve remaining txts
        pattern_toc = re.compile('Table of Contents', re.IGNORECASE)
        toc = pattern_toc.search(doc_content)
        section_tree: SectionTree = SectionTree()

        if toc:

            ans = self.toc_extract(doc_content)

            if ans == None: return
            rest = ans['rest']
            self._section_helper(level=1, start=0, end=len(rest)-1, content=rest, sections=section_tree)

        else:
            self._section_helper(1, 0, len(doc_content)-1, doc_content, section_tree)

        return section_tree


    # def db_create(self):
        # self.chroma_collection.upsert(
        #     ids = [str(i) for i in range(len(self.doc_pages))],
        #     documents= self.doc_pages
        # )

        # return self.chroma_collection

    def output_readable(self):
        """helper function: output human readable content
        """
        if self.doc_content is None: return
        pprint(self.doc_content)

    def output_raw(self):
        """helper function: output raw content of file
        """
        pprint(self.doc_file.read())

    def output_pages(self):
        """helper function: output pages of file
        """
        if self.doc_pages is None: return
        print(len(self.doc_pages))
        for i in range(len(self.doc_pages)):
            print(f'===============NUMBER: {i}================')
            pprint(self.doc_pages[i])

    # def db_query(self, txts:str):
    #     results = self.chroma_collection.query(
    #         query_texts=txts,
    #         n_results=5
    #     )
    #     return results['documents']