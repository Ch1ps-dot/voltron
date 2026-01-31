import re
from typing import Self
from voltron.utils.logger import logger

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
            level: int, 
            start: int,
            end: int,
            name: str,
    ) -> None:
        self.name: str = name
        self.subsection: list[SectionNode] = []
        self.start: int = start
        self.end: int = end
        self.level: int = level
        self.isLeaf: bool = False
        self.upper: SectionNode | None
        self.content_type: str = 'none'

        # debug
        # print(f'{name}: [{start}-{end}]')

    def add_subsection(
            self, 
            node: Self
    ) -> None:
        """Add subsection to current section
        
        Args:
            name: name of subsection
        """

        # add the content between first subsection and start point of upper section.
        if self.subsection == [] and node.start - self.start > len(self.name) + 5:
            ov_node = SectionNode(
                level = node.level,
                start = self.start,
                end = node.start,
                name = f'\t{self.name}[PADDING]'
            )
            ov_node.upper = self
            self.subsection.append(ov_node)
        self.subsection.append(node)

    def is_sub(
            self,
            name: str
    ) -> bool:
        """TODO
        """
        return name in self.subsection
        

class SectionTree:
    """Structure of Section Tree

    Attributes:
        id: identification of documents
        height: the height of tree
        toc: table of content of the document
        tree: a double list of SectionNode. The index of second level list stands for the level of belonging SectionNode.
        content: content of the original txt
    """
    def __init__(
            self, 
            name: str = '',
            content: str = ''
    ) -> None:
        self.tree: list[list[SectionNode]] = [[SectionNode(0, 0, len(content) - 1, '0.')]]
        self.leafs: list[SectionNode] = []
        self.height: int = 0
        self.doc_toc: str = ''
        self.doc_apx: str = ''
        self.name: str = name

        ans = self._toc_extract(content)
        if ans != None:
            self.doc_content = ans['rest']
        else:
            self.doc_content = content

        ans = self._apx_extract(self.doc_content)
        if ans != None:
            self.doc_apx = ans['apx']
            self.doc_content = ans['rest']

        self.construct_tree()
        self.identify_leaf(self.tree[0][0])

    def construct_toc(
            self,
            node: SectionNode | None
    ) -> None:
        if (node == None): return
        self.doc_toc = self.doc_toc + '\n' + node.name
        if(node.subsection != []):
            for n in node.subsection:
                self.construct_toc(n)

    
    def construct_pages(
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
        
    def _toc_extract(
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
        
    def _apx_extract(
            self, 
            doc_content: str
    ) -> dict[str, str] | None:
        """extact table of cantent from documents
        Args:
            doc_content: content of documents
        Returns:
            A dict contains table of content and rest part of the document
        """
        reg = r'$(?=\r?\n^\s*$)' + r'^\s*' + \
                r'appendix' + \
                r'[^,\n]*' + \
                r'$(?=\r?\n^\s*$)'
        pattern_apx = re.compile(reg, re.MULTILINE | re.IGNORECASE)
        apx = pattern_apx.search(doc_content)
        
        if apx:
            apx_start = apx.start()
            doc_apx = doc_content[apx_start:]
            return {"apx": doc_apx, "rest": doc_content[:apx_start]}
        else:
            return None

    def _check_section(
            self,
            pre: str,
            cur: str
    ) -> bool:
        """Check the string whether it is section name by indent space

        Args:
            pre: previous section name
            cur: current string

        Return:
            true or false
        """

        # pre_seg = pre.strip().split('.')
        # cur_seg = cur.strip().split('.')

        # if(len(pre_seg) == len(cur_seg)): 
        #     reg = r'^\s*'
        #     pattern = re.compile(reg)
        #     pos_pre = -1
        #     pos_cur = -1
        #     m_pre: re.Match | None = pattern.match(pre)
        #     m_cur: re.Match | None = pattern.match(cur)

        #     if m_pre and m_cur:
        #         pos_pre = m_pre.end()
        #         pos_cur = m_cur.end()
            
        #     if pos_cur == pos_pre:
        #         return True
        #     else:
        #         return False
            
        # return True

        cnt = 0
        for c in cur.strip():
            if c == '.': cnt = cnt + 1
            if cnt != 0: return True
    
        reg = r'^\s*'
        pattern = re.compile(reg)
        pos_pre = -1
        pos_cur = -1
        m_pre: re.Match | None = pattern.match(pre)
        m_cur: re.Match | None = pattern.match(cur)

        if m_pre and m_cur:
            pos_pre = m_pre.end()
            pos_cur = m_cur.end()
        
        if pos_cur <= pos_pre:
            return False
        else:
            return True
        
    def _section_helper(
            self, 
            level: int, 
            start: int,
            end: int,
            upper: str = '0.'
    ):
        """Help function to construct section tree

        use regrex to find the different level of sections.
        Recursively construct section tree from upper to lower section.

        Args:
            level: level of current section
            start: start point of current section
            end: end point of current section
            upper: name of upper level section

        """
        reg = r'(?<=^\s*$)\r?\n' + \
                r'^[ ]*' + \
                r'\d+\.' * level + \
                r'[ ]*' + \
                r'[^,.\n]*' + \
                r'$(?=\r?\n^\s*$)'
        pattern = re.compile(reg, re.MULTILINE)

        # early return if not match
        if pattern.findall(self.doc_content[start:end]) == []: return None

        # initialize the index by scope of current section
        pre_section_start = start
        cur_section_start = start
        pre_name = ''
        cur_name = ''
        skip_first = True
    
        for s in pattern.finditer(self.doc_content[start:end]):

            # skip first round because we dont know the end of section
            # we must change relative index which find by regrex to real index
            if skip_first:
                pre_section_start = s.start() + start
                pre_name =  re.sub(r'\n', '', s.group()) 
                skip_first = False
                continue

            # validate the section name
            cur_name = re.sub(r'\n', '', s.group())
            
            if self._check_section(pre_name, cur_name) == False:
                logger.debug(f'{pre_name} {cur_name}') 
                continue

            cur_section_start = s.start() + start

            # add previous section to SectionTree and upper SectionNode
            node = SectionNode(level, pre_section_start, cur_section_start, pre_name)          
            self.add_section(node)
            if upper:
                upper_node = self.fetch_node(level - 1, upper)
                if upper_node != None:
                    upper_node.add_subsection(node)
                    node.upper = upper_node
            
            # recursively resolve subsection
            self._section_helper(
                level+1, 
                pre_section_start, 
                cur_section_start,
                pre_name
            )

            # iterate the index and name of current section
            pre_name = cur_name
            pre_section_start = cur_section_start
            
        # store the last one node
        # if (self._check_section(pre_name, cur_name)): 
        node = SectionNode(level, pre_section_start, end, pre_name)
        self.add_section(node)

        if upper:
            upper_node = self.fetch_node(level - 1, upper)
            if upper_node != None:
                upper_node.add_subsection(node)
                node.upper = upper_node
        self._section_helper(
                level+1, 
                pre_section_start, 
                end,
                pre_name
            )
        
    def construct_tree(
            self
    ) -> None:
        """Construct the section tree
        """
        self._section_helper(1, 0, len(self.doc_content) - 1, '0.') 

    def add_section(
            self, 
            node: SectionNode
    ):
        """Add section node to section tree
        """
        if(node.level > self.height): 
            self.height += 1
            self.tree.append([])
        self.tree[node.level].append(node)

    def identify_leaf(
            self,
            node: SectionNode
    ):
        """Scan the section tree and identify leaf nodes, then set the isLeaf flag
        """
        if node.subsection == []:
            node.isLeaf = True 
            self.leafs.append(node)
        else:
            for n in node.subsection:
                self.identify_leaf(n)

    def fetch_node(
            self, 
            level: int = -1,
            id: str = '', 
            mode: bool = False
    ) -> SectionNode | None:
        """fetch the node with section name or section id, you must apply the arguments clearly.
        This function have two different application method. When mode is set to true, search the node by section number.
        Otehrwise, search the node by section name. If level hasn't been set, iterate through the entire tree to search the node.

        Args:
            level: level of the node in tree
            id: section number or section name of the section node

        Returns:
            Specified SectionNode
        """
        if level != -1:
            if mode:
                comma = 0
                for c in id:
                    if c == '.':
                        comma += 1

                reg =  r'\d+\.' * comma
                pattern = re.compile(reg)
                
                for n in self.tree[level]:
                    if pattern.match(n.name):
                        return n
                    
            else:
                for n in self.tree[level]:
                    if n.name == id:
                        return n
        else:
            for l in range(len(self.tree)):
                if id != '':
                    comma = 0
                    for c in id:
                        if c == '.':
                            comma += 1

                    reg =  r'\d+\.' * comma
                    pattern = re.compile(reg)
                
                    for n in self.tree[l]:
                        if pattern.match(n.name):
                            return n
                    
                else:
                    for n in self.tree[l]:
                        if n.name == id:
                            return n
                
        return None

    def fetch_layer(self, level):
        return self.tree[level]
    
    def fetch_node_content(
            self,
            node: SectionNode
    ) -> str:
        return self.doc_content[node.start:node.end]
    
    def fetch_id_content(
            self,
            id: str = '', 
            name: str = ''
    ) -> str | None:
        """TODO: fetch the content of section by section id
        
        Args:
            id: section id

        Returns:
            content of section
        """
        if id != '':
            level = 0
            for c in id:
                if c == '.':
                    level += 1

            reg =  r'\d+\.' * level
            pattern = re.compile(reg)
            
            for n in self.tree[level]:
                if pattern.match(n.name):
                    return self.doc_content[n.start:n.end]
                
        if name != '':
            for n in self.tree[level]:
                if n.name == name:
                    return self.doc_content[n.start:n.end]

        return None
    
    def fetch_toc(
            self
    ) -> str | None:
        """Return the table of content if it exists, otherwise constructing it.

        Returns:
            strings of toc
        """
        if (self.doc_toc != ''): return self.doc_toc

        self.construct_toc(self.tree[0][0])
        return self.doc_toc
    
    def debug_tree(
            self
    ):
        for node in self.leafs:
            logger.debug(f'{node.name}-{node.content_type}')
    
