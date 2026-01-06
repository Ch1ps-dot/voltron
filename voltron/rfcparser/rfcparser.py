import time, pickle, json, re
from pprint import pprint
from pathlib import Path
from typing import Self
from lxml import etree # type: ignore
from tqdm import tqdm
from fastbm25 import fastbm25

from voltron.rfcparser.setciontree import SectionTree
from voltron.utils.logger import logger
from voltron.llm.chat import Chater

class RFCParser:
    """Read protocol specification and parse it to section tree, then use these information to generate IR.

    Attributes:
        pro_name: name of protocol
        req: discription of request status field
        res: discription of response status field
        req_ir: message format information for request message
        res_ir: message format information for response message 
        st: tree-like data structure of specification document
    """
    def __init__(
            self, 
            doc_path: Path,
            pro_name: str,
            rfc_name: str,
            chater: Chater,
            base_path: Path
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
        self.req_json: list[dict] # json data of request field
        self.res_json: list[dict] # json data of response field
        self.req_types: list[str]
        self.res_types: list[str]
        self.req_doc: list = []
        self.res_doc: list = []
        self.ir_path = base_path / 'ir' / pro_name

        self.poss_res: dict[str, str] = {}
        self.req_res_map: dict[str, str] = {}

        self.req_ir = None
        self.res_ir = None

        if (not self.ir_path.is_dir()):
            self.ir_path.mkdir()

        # sectiontree parse pass
        fn = self.ir_path / "section_tree.pkl"
        if(fn.is_file()):
            self.load_st()
            logger.debug('[RFC Parse]: load parser')
            self._query_prepare()
        else:
            self.spe_parse()
            logger.debug('[RFC Parse]: parse document')
            self._query_prepare()
        logger.debug('[RFC Parse]: finish parse')

        self.rag_req: fastbm25 = self.rag_init(self.req_doc)
        self.rag_res: fastbm25 = self.rag_init(self.res_doc)
        self.rag_all: fastbm25 = self.rag_init(list(dict.fromkeys(self.req_doc + self.res_doc)))

        # ir generation
        self.ir_generation()

    def _query_prepare(
            self
    ):
        """Prepare content for ir generation

        concatenate the sections of document with the same type as one augmentation info
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
        logger.debug('[RFCParser]: query prepare')

    def spe_parse(
            self
    ):
        """Parse specification documents and annotate the section tree.

        LLM returns four different types
        1. request
        2. response
        3. all
        4. none
        """
        with tqdm(total=len(self.st.leafs), desc='[Spec Parse]', unit='section') as pbar:
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
                        logger.debug(f'[Tree Annotate]: {node.name}-{ans}')
                pbar.update(1)
                    
        self.save_st()           
    
    def ir_generation(
            self
    ):
        """Workflow of IR generation

        1. field extraction for request and response message individually.
        2. message ir generation for request and response.
        3. state ir generation for state model

        """
        """
            format of key field description
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
        
        """===Key Field Parse==="""
        req_path = self.ir_path / 'req.json'
        res_path = self.ir_path / 'res.json'

        # request field extraction
        if(req_path.is_file()):
            with open(req_path, 'r', encoding='utf-8') as f:
                self.req_json = json.load(f)
            logger.debug('[IR Generation]: request description load')
        else:
            while(True):
                try:
                    req_json = self.chater.llm_request_query(
                        rfc_num = self.rfc_name,
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.req_doc])
                    )

                    if (req_json != None):
                        self.req_json = json.loads(req_json[7:-4])
                        with open(req_path, 'w', encoding="utf-8") as f:
                            json.dump(self.req_json, f)
                        break
                except Exception as e:
                    logger.debug('[IR Generation]: {e}')
            logger.debug('[IR Generation]: request description generation')

        # response field extraction
        if(res_path.is_file()):
            with open(res_path, 'r', encoding='utf-8') as f:
                self.res_json = json.load(f)
            logger.debug('[IR Generation]: response description load')
        else:
            while(True):
                try:
                    res_json = self.chater.llm_response_query(
                        rfc_num = self.rfc_name,
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.res_doc])
                    )

                    if (res_json != None):
                        self.res_json = json.loads(res_json[7:-4])
                        with open(res_path, 'w', encoding="utf-8") as f:
                            json.dump(self.res_json, f)
                        break
                except Exception as e:
                    logger.debug('[IR Generation]: {e}')
                logger.debug('[IR Generation]: response description generation')

        if(self._field_check(self.req_json[0]) and self._field_check(self.res_json[0])):
            logger.debug('[bad field format]')

        self.req_types = self.req_json[0]['value']
        self.res_types = self.res_json[0]['value']

        # model generation
        self.message_model_generation()
        self.state_model_generation()

    def message_model_generation(
            self
    ) -> None:
        """===Message IR Generation==="""
        # request message IR generation
        req_ir_path =  self.ir_path / 'req_ir.xml'
        if (req_ir_path.is_file()):
            self.req_ir = etree.parse(req_ir_path)
            logger.debug('[IR Generation]: req ir load')
        else:
            root = etree.Element('ir')
            # generate ir for every message type
            with tqdm(total=len(self.req_types), desc='[REQ MSG IR]', unit='type') as pbar:
                for msg_type in self.req_types:
                    msg_ir = self.chater.llm_ir_generation(
                        pro_name=self.pro_name,
                        message_name=msg_type,
                        rfc_doc=''.join([s for s in self.req_doc])
                    )
                    if msg_ir == None:
                        raise Exception
                    try_times = 0
                    while(True):
                        fix_ir = self.chater.llm_ir_repair(
                            pro_name=self.pro_name,
                            message_name=msg_type,
                            ir=msg_ir
                        )
                        try:
                            if fix_ir != None:
                                ir = re.sub(r'"([^"]*)"', self._fix_attr, fix_ir[6:-4]) # fix xml
                                ir_xml = etree.fromstring(ir)
                                root.append(ir_xml)
                                break
                        except Exception as e:
                            try_times += 1
                            logger.debug(fix_ir)
                            logger.debug(f'[bad xml format] {msg_type}: {try_times} err: {e}')
                            if (fix_ir != None):
                                msg_ir = fix_ir
                    pbar.update(1)
            tree = etree.ElementTree(root)
            tree.write( 
                req_ir_path,
                encoding="UTF-8",
                xml_declaration=True,
                pretty_print=True,
                standalone="yes"
            )
            self.req_ir = etree.parse(req_ir_path)

        # response message IR generation, just like above.
        res_ir_path = self.ir_path / 'res_ir.xml'
        if (res_ir_path.is_file()):
            self.res_ir = etree.parse(res_ir_path)
            logger.debug('[IR Generation]: res ir load')
        else:
            root = etree.Element('ir')

            # generation for every response type
            with tqdm(total=len(self.res_types), desc='[RES MSG IR]', unit='type') as pbar:
                for msg_type in self.res_types:

                    msg_ir = self.chater.llm_ir_generation(
                        pro_name=self.pro_name,
                        message_name=msg_type,
                        rfc_doc=''.join([s for s in self.res_doc])
                    )

                    if msg_ir == None:
                        raise Exception
                    
                    while(True):
                        fix_ir = self.chater.llm_ir_repair(
                            pro_name=self.pro_name,
                            message_name=msg_type,
                            ir=msg_ir
                        )
                        try:
                            if fix_ir != None:
                                ir = re.sub(r'"([^"]*)"', self._fix_attr, fix_ir[6:-4]) # fix xml
                                logger.debug(ir)
                                ir_xml = etree.fromstring(ir)
                                root.append(ir_xml)
                                break
                        except Exception as e:
                            try_times += 1
                            logger.debug(fix_ir)
                            logger.debug(f'{msg_type}: {try_times} err: {e}')
                            if (fix_ir != None):
                                msg_ir = fix_ir
                    pbar.update(1)

            tree = etree.ElementTree(root)
            tree.write( 
                res_ir_path,
                encoding="UTF-8",
                xml_declaration=True,
                pretty_print=True,
                standalone="yes"
            )
            self.res_ir = etree.parse(res_ir_path)

        logger.debug('[IR Generation]: finish message model generation')


    def state_model_generation(
            self
    ) -> None:
        """===State Model Generation==="""

        # generate or load possible response of each request
        poss_res_path = self.ir_path / "poss_res.json"
        if (poss_res_path.is_file()):
            with open(poss_res_path, 'r', encoding='utf-8') as f:
                self.poss_res = json.load(f)
            logger.debug('[IR Generation]: request description load')
        else:
            with tqdm(total=len(self.req_types), desc='[Possible Response]', unit='type') as pbar:
                for req_type in self.req_types:
                    while(True):
                        try:
                            ans_str = self.chater.llm_possible_res(
                                pro_name=self.pro_name,
                                current_request=req_type,
                                response_types=json.dumps(self.res_types)
                            )
                            cur_poss_res = json.loads(ans_str[7:-4])
                            self.poss_res[req_type] = cur_poss_res['possible_response']
                            break
                        except Exception as e:
                            logger.debug(e)
                    pbar.update(1)
            with open(poss_res_path, 'w') as f:
                json.dump(self.poss_res, f)
               
        # infer dependency in method
        req_res_map_path = self.ir_path / "state_dependency.json"
        if (req_res_map_path.is_file()):
            with open(req_res_map_path, 'r', encoding='utf-8') as f:
                self.req_res_map = json.load(f)
            logger.debug('[IR Generation]: request description load')
        else:
            with tqdm(total=len(self.req_types), desc=f'[Infer Dependency]', unit='type') as pbar1:
                for req_type in self.req_types:
                    with tqdm(total=len(self.poss_res[req_type]), desc=f'[Infer req-res pair]', unit='type') as pbar2:
                        for res_type in self.poss_res[req_type]:
                            while(True):
                                try:
                                    query = [req_type, res_type]
                                    results = self.rag_all.top_k_sentence(query, 5)
                                    logger.debug(f'[Rag]: topk {' '.join(results[0][0])}')
                                    ans_str = self.chater.llm_infer_dependency(
                                        pro_name=self.pro_name,
                                        current_request=req_type,
                                        request_types=json.dumps(self.req_types),
                                        response_type=res_type,
                                        rfc_content=''.join([' '.join(item[0]) for item in results])
                                    )
                                    next_request = json.loads(ans_str[7:-4])
                                    self.req_res_map[f'{req_type}-{res_type}'] = next_request['next_request']
                                    break
                                except Exception as e:
                                    logger.debug(e)
                            pbar2.update(1)
                    pbar1.update(1)
                with open(req_res_map_path, 'w') as f:
                    json.dump(self.req_res_map, f)

        logger.debug('[IR Generation]: finish state model generation')


    def _field_check(
            self,
            data: dict
    ) -> bool:
        """Check the json content of message field information

        Args:
            data: json file of message format

        Return:
            True or False
        """
        for key in data:
            if key not in ['field', 'position', 'explanation', 'value']:
                return False
        return True
    
    def _escape_xml_attr(
            self,
            s: str
    ) -> str:
        """Fix xml file, transfer some special character to avoid xml parsing failure

        Args:
            s: xml file as string

        Return:
            fixed xml file
        """
        s = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;', s)
        s = s.replace('<', '&lt;')
        s = s.replace('>', '&gt;')
        return s
    
    def _fix_attr(
            self,
            match
    ) -> str:
        """Callback function for xml fixing
        """
        return '"' + self._escape_xml_attr(match.group(1)) + '"'


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
            logger.debug("[Save Sectiontree]")   

    def rag_init(
        self,
        sections: list[str]
    ) -> fastbm25:
        corpus = [s.split() for s in sections]
        bm25 = fastbm25(corpus)
        return bm25
    

    

    






    
