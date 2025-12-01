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
            level: int, 
            start: int,
            end: int
    ) -> None:
        self.name = name
        self.subsection = []
        self.start = start
        self.end = end
        self.level = level

        print(f'{name}: {start}-{end}')

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
        tree: a double list of SectionNode. The index of second level list stands for the level of belonging SectionNode.
    """
    def __init__(
            self, 
            id: str = ''
    ) -> None:
        self.tree: list[list[SectionNode]] = [[SectionNode('root', 0, 0, 0)]]
        self.height = 0
        self.toc = 0
        self.id = id

    def add_section(self, node: SectionNode):
        if(node.level > self.height): 
            self.height += 1
            self.tree.append([])
        self.tree[node.level].append(node)

    def fetch_node(
            self, 
            level: int, 
            name: str
    ) -> SectionNode | None:
        """fetch the node with section name
        """
        for s in self.tree[level]:
            if s.name == name:
                return s
        return None

    def fetch_layer(self, level):
        return self.tree[level]
    

    def output_node(
            self,
            node: SectionNode | None
    ) -> None:
        if (node == None): return
        print('-'*node.level + node.name)
        if(node.subsection != []):
            for n in node.subsection:
                self.output_node(n)

    def output_tree(self):
        if self.height == 0: return 
        self.output_node(self.tree[0][0])

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
            upper: str = 'root'
    ):
        """Help function to construct section tree

        use regrex to find the different level of sections.
        Recursively construct section tree from upper to lower section.

        Args:
            level: level of current section
            start: start point of current section
            end: end point of current section
            content: the original txt
            sections: section tree
            upper: name of upper level section

        """
        reg = r'^(?<!\S)' + r'\d+\.' * level + r'\s+.*'
        pattern = re.compile(reg, re.MULTILINE)

        # early return if not match
        if pattern.findall(content[start:end]) == []: return None

        # initialize the index by scope of current section
        pre_section_start = start
        cur_section_start = start
        pre_name = ''
        skip_first = True
    
        for s in pattern.finditer(content[start:end]):
            
            # skip first round because we dont know the end of section
            # we must change relative index which find by regrex to real index
            if skip_first:
                pre_section_start = s.start() + start
                pre_name = s.group() 
                skip_first = False
                continue

            cur_section_start = s.start() + start

            # add previous section to SectionTree and upper SectionNode
            node = SectionNode(pre_name, level, pre_section_start, cur_section_start)          
            sections.add_section(node)
            if upper:
                upper_node = sections.fetch_node(level - 1, upper)
                if upper_node != None:
                    upper_node.add_subsection(node)
            
            # recursively resolve subsection
            self._section_helper(
                level+1, 
                pre_section_start, 
                cur_section_start,
                content,
                sections,
                pre_name
            )

            # iterate the index and name of current section
            pre_name = s.group()
            pre_section_start = cur_section_start
            

        # store the last one node
        node = SectionNode(pre_name, level, pre_section_start, end)
        sections.add_section(node)
        if upper:
            upper_node = sections.fetch_node(level - 1, upper)
            if upper_node != None:
                upper_node.add_subsection(node)
        self._section_helper(
                level+1, 
                pre_section_start, 
                end,
                content,
                sections,
                pre_name
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