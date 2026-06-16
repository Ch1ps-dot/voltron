import re
from typing import Self
from voltron.utils.logger import logger_fuzz as logger

FIXED_SECTION_TITLES = {
    'abstract',
    'status of this memo',
    'security considerations',
    'iana considerations',
    'references',
    'acknowledgements',
    'acknowledgments',
}

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

        self.tree = [[SectionNode(0, 0, len(self.doc_content), '0.')]]
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
        reg =  r'^\s*$' + \
                r'\r?\n' + \
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
        if not self._construct_tree_from_headings():
            self._section_helper(1, 0, len(self.doc_content), '0.')

    def _construct_tree_from_headings(
            self
    ) -> bool:
        """Construct the tree from scored line-based heading candidates."""
        candidates = self._scan_heading_candidates()
        headings = self._filter_heading_candidates(candidates)
        if len(headings) < 2:
            return False

        self.tree = [[SectionNode(0, 0, len(self.doc_content), '0.')]]
        self.height = 0
        root = self.tree[0][0]
        stack = [root]
        nodes: list[SectionNode] = []

        for heading in headings:
            node = SectionNode(
                heading['level'],
                heading['offset'],
                len(self.doc_content),
                heading['raw'],
            )
            self.add_section(node)
            while stack and stack[-1].level >= node.level:
                stack.pop()
            parent = stack[-1] if stack else root
            parent.add_subsection(node)
            node.upper = parent
            stack.append(node)
            nodes.append(node)

        for index, node in enumerate(nodes):
            node.end = (
                nodes[index + 1].start
                if index + 1 < len(nodes)
                else len(self.doc_content)
            )
        root.end = len(self.doc_content)
        return True

    def _scan_heading_candidates(
            self
    ) -> list[dict]:
        candidates = []
        offset = 0
        lines = self.doc_content.splitlines(keepends=True)
        for line_no, line in enumerate(lines):
            raw_line = line.rstrip('\r\n')
            stripped = raw_line.strip()
            if not stripped:
                offset += len(line)
                continue

            candidate = self._parse_heading_line(stripped, raw_line, offset, line_no)
            if candidate is None:
                offset += len(line)
                continue

            prev_blank = self._is_blank_line(lines, line_no - 1)
            next_blank = self._is_blank_line(lines, line_no + 1)
            score, reasons = self._score_heading_candidate(
                candidate,
                raw_line,
                prev_blank,
                next_blank,
            )
            candidate['score'] = score
            candidate['reasons'] = reasons
            if score >= 0.65:
                candidates.append(candidate)
            offset += len(line)
        return candidates

    def _parse_heading_line(
            self,
            stripped: str,
            raw_line: str,
            offset: int,
            line_no: int,
    ) -> dict | None:
        numeric = re.match(
            r'^(?P<number>\d+(?:\.\d+)*\.?)\s+(?P<title>\S.*)$',
            stripped,
        )
        if numeric:
            number = numeric.group('number')
            title = numeric.group('title').strip()
            clean_number = number.rstrip('.')
            level = len(clean_number.split('.'))
            return {
                'raw': stripped,
                'number': clean_number,
                'title': title,
                'level': level,
                'offset': offset + raw_line.index(stripped[0]),
                'line_no': line_no,
                'source': 'numeric',
            }

        fixed_title = stripped.lower()
        if fixed_title in FIXED_SECTION_TITLES:
            return {
                'raw': stripped,
                'number': None,
                'title': stripped,
                'level': 1,
                'offset': offset + raw_line.index(stripped[0]),
                'line_no': line_no,
                'source': 'fixed',
            }

        appendix = re.match(
            r'^(Appendix\s+(?P<number>[A-Z])(?:\.\d+)*\.?)'
            r'(?:\s+(?P<title>\S.*))?$',
            stripped,
            re.IGNORECASE,
        )
        if appendix:
            number = appendix.group('number').upper()
            suffix = stripped.split(None, 2)
            title = appendix.group('title') or ''
            return {
                'raw': stripped,
                'number': f'Appendix {number}',
                'title': title or suffix[-1],
                'level': 1,
                'offset': offset + raw_line.index(stripped[0]),
                'line_no': line_no,
                'source': 'appendix',
            }
        return None

    def _score_heading_candidate(
            self,
            candidate: dict,
            raw_line: str,
            prev_blank: bool,
            next_blank: bool,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons = []
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(' '))

        if candidate['source'] in {'numeric', 'appendix'}:
            score += 0.55
            reasons.append('structured-prefix')
        if candidate['source'] == 'fixed':
            score += 0.75
            reasons.append('fixed-title')
        if prev_blank:
            score += 0.2
            reasons.append('previous-blank')
        if next_blank:
            score += 0.2
            reasons.append('next-blank')
        if len(stripped) <= 90:
            score += 0.1
            reasons.append('short-line')
        if indent >= 8:
            score -= 0.4
            reasons.append('deep-indent')
        if stripped.endswith(('.', ';', ',')) and candidate['source'] == 'numeric':
            score -= 0.25
            reasons.append('sentence-like-ending')
        if len(re.findall(r'[,;:]', stripped)) >= 2:
            score -= 0.2
            reasons.append('punctuation-heavy')
        if candidate['source'] == 'numeric' and not prev_blank:
            score -= 0.35
            reasons.append('inline-numbered-text')
        return score, reasons

    def _filter_heading_candidates(
            self,
            candidates: list[dict],
    ) -> list[dict]:
        filtered = []
        seen_numbers = set()
        for candidate in candidates:
            number = candidate.get('number')
            if number and number in seen_numbers:
                continue
            if candidate['source'] == 'numeric':
                parent_number = self._parent_section_number(number)
                if (
                    parent_number is not None
                    and parent_number not in seen_numbers
                ):
                    candidate['score'] -= 0.2
                    if candidate['score'] < 0.65:
                        continue
            filtered.append(candidate)
            if number:
                seen_numbers.add(number)
        return filtered

    def _parent_section_number(
            self,
            number: str | None
    ) -> str | None:
        if number is None or '.' not in number:
            return None
        return number.rsplit('.', 1)[0]

    def _is_blank_line(
            self,
            lines: list[str],
            index: int,
    ) -> bool:
        if index < 0 or index >= len(lines):
            return True
        return lines[index].strip() == ''

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
            logger.debug(f'{node.name}:{node.content_type}')
    
