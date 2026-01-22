import pickle, json, re, asyncio, sys
from pathlib import Path
from typing import Tuple
from lxml import etree # type: ignore
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio
from fastbm25 import fastbm25

from voltron.rfcparser.setciontree import SectionTree, SectionNode
from voltron.utils.logger import logger
from voltron.llm.AsyncChat import AsyncChater
from voltron.configs import configs


class AsyncRFCParser:
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
            chater: AsyncChater,
    ) -> None:
        self.chater =chater

        # doc related value
        self.doc_path: Path = configs.doc_path
        self.doc_file = configs.doc_path.open('r+', encoding='utf-8')
        self.doc_content: str = self.doc_file.read()
        self.pro_name = configs.pro_name
        self.rfc_name = configs.rfc_name

        # initialize the sectiontree which stands for the section structure of documents 
        self.st = SectionTree(id='', content=self.doc_content)

        # ir related value
        self.req_json: list[dict] # json data of request field
        self.res_json: list[dict] # json data of response field
        self.req_types: list[str]
        self.res_types: list[str]
        self.req_doc: list = []
        self.res_doc: list = []
        self.ir_path = configs.base_path / 'output' / 'ir' / configs.pro_name

        self.poss_res: dict[str, str] = {}
        self.req_dep_map: dict[str, dict] = {} # dependency between requests

        self.req_ir = None
        self.res_ir = None

        if (not self.ir_path.is_dir()):
            self.ir_path.mkdir()

       
    def run(
        self
    ):
        # sectiontree parse pass
        fn = self.ir_path / "section_tree.pkl"
        if(fn.is_file()):
            self.load_st()
            logger.debug('RFCParser: load parser')
            self._query_prepare()
        else:
            self.spe_parse()
            logger.debug('RFCParser: parse document')
            self._query_prepare()
        logger.debug('RFCParser: finish parse')

        self.rag_req_msg: fastbm25 = self.rag_init(self.req_doc)
        self.rag_res_msg: fastbm25 = self.rag_init(self.res_doc)
        self.rag_all: fastbm25 = self.rag_init([self.st.fetch_node_content(node) for node in self.st.leafs])

        # ir generation
        self.ir_generation()
        
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
        asyncio.run(self._spe_parse_aync())
        self.save_st()

    def ir_generation(
            self
    ):
        """Workflow of IR generation

        1. field extraction for request and response message individually.
        2. message ir generation for request and response.
        3. state ir generation for state model
        """
        with tqdm(desc='key field extraction', total=1) as pbar:
            asyncio.run(self.key_field_extract())
            pbar.update(1)
        self.message_model_generation()
        self.state_model_generation()

        logger.debug('RFCParser: finish ir generation')
    
    async def key_field_extract(
            self
    ):
        """Key Field Parse"""
        req_path = self.ir_path / 'req.json'
        res_path = self.ir_path / 'res.json'
        res_task = asyncio.create_task(self._res_field(res_path))
        req_task = asyncio.create_task(self._req_field(req_path))
        
        res_json = await res_task
        req_json = await req_task

        self.req_types = req_json[0]['value']
        self.res_types = res_json[0]['value']

        logger.debug('RFCParser: finish key field extraction')
    
    def message_model_generation(
            self
    ) -> None:
        
        """Message IR Generation"""
        asyncio.run(self._msg_model_gen_async('req'))
        asyncio.run(self._msg_model_gen_async('res'))

        logger.debug('[IR Generation]: finish message model generation')

    def state_model_generation(
            self
    ) -> None:
        """State Model Generation"""
        # infer possible response
        asyncio.run(self._poss_response_async())
        # infer dependency in method
        asyncio.run(self._state_dependency_async())

        logger.debug('RFCParser: finish state model generation')


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
                    logger.debug(f"[Section type]: unexpected type")
        if len(self.req_doc) == 0 or len(self.res_doc) == 0:
            logger.debug('RFCParser: bad documents, lack of request and response information')
            sys.exit(1)
            
        logger.debug('[RFCParser]: query prepare')

    async def _spe_parse_aync(
            self
    ):
        sem = asyncio.Semaphore(configs.async_sem)
        tasks = [
            self._spe_parse_one(node, sem)
            for node in self.st.leafs
        ]

        results = await tqdm_asyncio.gather(*tasks, desc="Doc Annotation")

        for node, doc_type in results:
            node.content_type = doc_type

    async def _spe_parse_one(
            self,
            node: SectionNode,
            sem: asyncio.Semaphore
    ):
        async with sem:
            while True:
                try:
                    doc = self.st.fetch_node_content(node)
                    ans = ''
                    if doc != None:
                        ans = await self.chater.llm_doc_parse(
                            rfc_num = self.rfc_name,
                            pro_name = self.pro_name,
                            rfc_doc = doc
                        )
                        if ans is None: raise Exception
                        logger.debug(f'[Tree Annotate]: {node.name}-{ans}')
                        return node, ans
                except Exception as e:
                    logger.error(f'RFCParser: specification parse error {e}')

    async def _req_field(
            self,
            req_path: Path
    ) -> list:
        # request field extraction
        if(req_path.is_file()):
            with open(req_path, 'r', encoding='utf-8') as f:
                return json.load(f)
            logger.debug('[IR Generation]: request description load')
        else:
            while(True):
                try:
                    pmp, req_json = await self.chater.llm_request_query(
                        rfc_num = self.rfc_name,
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.req_doc])
                    )
                    
                    req_json = await self.chater.llm_try_again(
                        last_question=pmp,
                        last_answer=req_json,
                        current_question=pmp
                    )
                    
                    if req_json == None:
                        logger.debug('empty json')
                        continue
                    
                    req_json = await self.chater.llm_try_again(
                        last_question=pmp,
                        last_answer=req_json,
                        current_question=pmp
                    )

                    if (req_json != None):
                        req_json = json.loads(req_json)
                        if self._field_check(req_json): 
                            continue
                        with open(req_path, 'w', encoding="utf-8") as f:
                            json.dump(req_json, f)
                        return req_json
                except Exception as e:
                    logger.debug(f'RFCParser: req field {e}')

    async def _res_field(
            self,
            res_path: Path
    ) -> list:
        # response field extraction
        if(res_path.is_file()):
            with open(res_path, 'r', encoding='utf-8') as f:
                return json.load(f)
            logger.debug('[IR Generation]: response description load')
        else:
            while(True):
                try:
                    pmp, res_json = await self.chater.llm_response_query(
                        rfc_num = self.rfc_name,
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.res_doc])
                    )
                    
                    res_json = await self.chater.llm_try_again(
                        last_question=pmp,
                        last_answer=res_json,
                        current_question=pmp
                    )
                    
                    if res_json == None:
                        logger.debug('empty json')
                        continue
                    
                    res_json = await self.chater.llm_try_again(
                        last_question=pmp,
                        last_answer=res_json,
                        current_question=pmp
                    )

                    if (res_json != None):
                        res_json = json.loads(res_json)
                        if self._field_check(res_json): 
                            continue
                        with open(res_path, 'w', encoding="utf-8") as f:
                            json.dump(res_json, f)
                        return res_json
                except Exception as e:
                    logger.debug(f'RFCParser: res field {e}')
    
    async def _msg_model_gen_one(
            self,
            msg_type: str,
            sem: asyncio.Semaphore
    ):
        query = [msg_type]
        topk = self.rag_all.top_k_sentence(query, 5)
        async with sem:    
            msg_ir = await self.chater.llm_ir_generation(
                            pro_name=self.pro_name,
                            message_name=msg_type,
                            rfc_doc=''.join([' '.join(item[0]) for item in topk])
                        )
            while(True):
                if msg_ir == None:
                    logger.debug('RFCParser: empty IR')
                    raise Exception
                try:
                    ir_xml = etree.fromstring(msg_ir)
                    return ir_xml
                except etree.XMLSyntaxError as e:
                    logger.debug(f'RFCParser: [bad xml format] {msg_type} err: {e}')
                    fix_ir = await self.chater.llm_ir_repair(
                                ir=msg_ir,
                                error=e.msg
                            )
                    if (fix_ir != None):
                        msg_ir = fix_ir
    
    async def _msg_model_gen_async(
            self,
            field_type
    ):
        # message IR generation
        if (field_type == 'req'):
            ir_path =  self.ir_path / 'req_ir.xml'
        elif (field_type == 'res'):
            ir_path =  self.ir_path / 'res_ir.xml'
        if (ir_path.is_file()):
            if (field_type == 'req'):
                self.req_ir = etree.parse(ir_path)
            elif (field_type == 'res'):
                self.res_ir = etree.parse(ir_path)
            logger.debug(f'RFCParser: {field_type} ir load')
        else:
            root = etree.Element('ir')
            sem = asyncio.Semaphore(configs.async_sem)

            tasks = [
                self._msg_model_gen_one(msg_type, sem)
                for msg_type in self.req_types
            ]

            results = await tqdm_asyncio.gather(*tasks, desc=f"{field_type} msg ir")
            for ir_xml in results:
                root.append(ir_xml)

            tree = etree.ElementTree(root)
            tree.write( 
                ir_path,
                encoding="UTF-8",
                xml_declaration=True,
                pretty_print=True,
                standalone="yes"
            )
            if (field_type == 'req'):
                self.req_ir = etree.parse(ir_path)
            elif (field_type == 'res'):
                self.res_ir = etree.parse(ir_path)
    
    async def _poss_response_async(
            self
    ):
        poss_res_path = self.ir_path / "poss_res.json"
        if (poss_res_path.is_file()):
            with open(poss_res_path, 'r', encoding='utf-8') as f:
                self.poss_res = json.load(f)
            logger.debug('RFCParser: poss response load')
        else:
            sem = asyncio.Semaphore(configs.async_sem)
            tasks = [
                self._poss_response_one(req_type, sem)
                for req_type in self.req_types
            ]
            results = await tqdm_asyncio.gather(*tasks, desc='poss res')
            for req_type, poss_res in results:
                self.poss_res[req_type] = poss_res
        with open(poss_res_path, 'w') as f:
                json.dump(self.poss_res, f)
        logger.debug('RFCParser: finish poss response')

    async def _poss_response_one(
            self,
            req_type,
            sem
    ):
        async with sem:
            while(True):
                try:
                    ans_str = await self.chater.llm_possible_res(
                        pro_name=self.pro_name,
                        current_request=req_type,
                        response_types=json.dumps(self.res_types)
                    )
                    cur_poss_res = json.loads(ans_str)
                    return req_type, cur_poss_res
                except Exception as e:
                    logger.debug(f'RFCParser: poss response {e}')

    async def _state_dependency_async(
            self
    ):
        req_dep_path = self.ir_path / "state_dependency.json"
        if (req_dep_path.is_file()):
            with open(req_dep_path, 'r', encoding='utf-8') as f:
                self.req_dep_map = json.load(f)
            logger.debug('RFCParser: request description load')
        else:
            sem = asyncio.Semaphore(configs.async_sem)
            tasks = [
                self._state_dependency_one(last_req, cur_req, sem)
                for last_req in self.req_types
                for cur_req in self.req_types
            ]

            results = await tqdm_asyncio.gather(*tasks, desc='dependency')

            for pair, relation in results:
                self.req_dep_map[pair] = relation

            with open(req_dep_path, 'w') as f:
                    json.dump(self.req_dep_map, f)
        

    async def _state_dependency_one(
            self,
            last_req: str,
            cur_req: str,
            sem
    ):
        query = [last_req, cur_req]
        results = self.rag_all.top_k_sentence(query, 5)
        async with sem:
            while(True):
                try:
                    ans_str = await self.chater.llm_infer_dependency(
                        last_request=last_req,
                        pro_name=self.pro_name,
                        current_request=cur_req,
                        response_types=json.dumps(self.res_types),
                        rfc_content=''.join([' '.join(item[0]) for item in results])
                    )
                    relation = json.loads(ans_str)
                    return f'{last_req}/{cur_req}', relation
                except Exception as e:
                    logger.debug(f'RFCParser: dependency failure {e}')


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
                logger.debug('bad json')
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
            logger.debug("RFCParser: save sectiontree")   

    def rag_init(
        self,
        sections: list[str]
    ) -> fastbm25:
        corpus = [s.split() for s in sections]
        bm25 = fastbm25(corpus)
        return bm25
    

    

    






    
