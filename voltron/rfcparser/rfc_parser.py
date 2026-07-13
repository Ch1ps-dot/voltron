import pickle, json, re, asyncio, sys, subprocess, os
from pathlib import Path
from typing import Tuple
from lxml import etree # type: ignore
from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio
from fastbm25 import fastbm25

from voltron.rfcparser.setciontree import SectionTree, SectionNode
from voltron.utils.logger import logger_fuzz as logger
from voltron.llm.chatter import AsyncChater
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
        self.doc_paths: list[Path] = configs.doc_paths
        self.tree_dict: dict[str, SectionTree] = {}
                
        self.pro_name = configs.pro_name
        self.rfc_name = configs.rfc_name

        # ir related value
        self.req_json: list[dict] # json data of request field
        self.res_json: list[dict] # json data of response field
        self.req_type_rules: dict = {}
        self.res_type_rules: dict = {}
        self.req_types: set[str] = set()
        self.res_types: set[str] = set()
        self.req_fields: list[str] = list()
        self.res_fields: list[str] = list()  
        self.req_doc: set[str] = set()
        self.res_doc: set[str] = set()
        self.all_doc: set[str] = set()
        self.ir_base_path = configs.base_path / 'component' / 'ir'
        self.ir_path = configs.base_path / 'component' / 'ir' / configs.pro_name
        self.ir_base_path.mkdir(parents=True, exist_ok=True)
        self.ir_path.mkdir(parents=True, exist_ok=True)

        self.poss_res: dict[str, list[str]] = {}
        self.req_dep_map: dict[str, dict[str, dict]] = {} # dependency between requests

        self.req_ir = None
        self.res_ir = None

    def run(
        self,
        use_spec_knowledge: bool = True,
    ):
        if not use_spec_knowledge:
            self.load_seed_metadata()
            logger.debug('RFCParser: specification knowledge disabled')
            return

        # Ensure RFC documents are available before parsing.
        dl_script = configs.base_path / 'skills' / 'utils' / 'rfc_download.sh'
        if dl_script.is_file():
            rfc_args: list[str] = []
            rfc_list = self.rfc_name if isinstance(self.rfc_name, list) else [self.rfc_name]
            for rfc in rfc_list:
                raw = str(rfc).strip()
                if not raw:
                    continue
                raw_lower = raw.lower()
                rfc_args.append(raw_lower if raw_lower.startswith('rfc') else f'rfc{raw_lower}')

            if len(rfc_args) > 0:
                try:
                    subprocess.run(
                        ['bash', str(dl_script), *rfc_args],
                        cwd=str(configs.base_path),
                        check=True,
                    )
                    logger.debug(f'RFCParser: downloaded RFC docs via {dl_script.name}: {rfc_args}')
                except subprocess.CalledProcessError as e:
                    logger.warning(f'RFCParser: failed to download RFC docs with {dl_script}: {e}')
        else:
            logger.warning(f'RFCParser: download script not found: {dl_script}')
        
        # sectiontree parse pass
        for i in range(len(self.doc_paths)):
            name=configs.rfc_name[i]
            logger.debug(f'create st: {name}')
            source = self.prepare_section_tree(i, name)
            logger.debug(f'RFCParser: sectiontree {source} [{name}]')
            self._query_prepare(name)
            logger.debug('RFCParser: finish parse')

        self.rag_req_msg: fastbm25 = self.rag_init(list(self.req_doc))
        self.rag_res_msg: fastbm25 = self.rag_init(list(self.res_doc))
        self.rag_all: fastbm25 = self.rag_init(list(self.all_doc))

        # ir generation
        self.ir_generation()

    def load_seed_metadata(
        self
    ) -> None:
        """Load only the symbol metadata needed to replay cached seed equipment."""
        equipment_path = (
            configs.base_path / 'component' / 'equipment' / configs.target_name
        )
        generator_info_path = (
            equipment_path / 'generators' / 'generator_info.json'
        )
        parser_info_path = equipment_path / 'parsers' / 'parser_info.json'

        if not generator_info_path.is_file() or not parser_info_path.is_file():
            raise RuntimeError(
                'Specification knowledge is disabled, but cached seed '
                f'equipment is missing under {equipment_path}'
            )

        with open(generator_info_path, 'r', encoding='utf-8') as f:
            generator_info = json.load(f)
        with open(parser_info_path, 'r', encoding='utf-8') as f:
            parser_info = json.load(f)

        self.req_types = {
            str(msg_type)
            for msg_type, generators in generator_info.items()
            if generators
        }
        if not self.req_types or not parser_info:
            raise RuntimeError(
                'Specification knowledge is disabled, but cached seed '
                f'equipment is empty under {equipment_path}'
            )
        self.req_fields = ['MessageType']
        self.res_json = []
        self.req_type_rules = {}
        self.res_type_rules = {}
        self.res_types = set()
        self.res_fields = []
        self.req_dep_map = {}
        self.poss_res = {}
        
    def spe_parse(
        self,
        idx: int
    ):
        """Parse specification documents and annotate the section tree.

        LLM returns four different types
        1. request
        2. response
        3. all
        4. none
        """
        with open(self.doc_paths[idx], 'r+', encoding='utf-8') as f:
            doc_content: str = f.read()
            st = SectionTree(name=configs.rfc_name[idx], content=doc_content)
            asyncio.run(self._spe_parse_async(st))
            self.tree_dict[configs.rfc_name[idx]] = st
            self.save_st(st)

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
        req_type_rules_path = self.ir_path / 'req_type_rules.json'
        res_type_rules_path = self.ir_path / 'res_type_rules.json'
        
        if not req_path.is_file() or not res_path.is_file():
            res_task = asyncio.create_task(self._res_field(res_path))
            req_task = asyncio.create_task(self._req_field(req_path))
            
            res_json = await res_task
            req_json = await req_task

            self.res_json = res_json
            self.req_json = req_json
            
        else:
            with open(req_path, 'r', encoding='utf-8') as f:
                req_json = json.load(f)
                self.req_json = req_json
                
            with open(res_path, 'r', encoding='utf-8') as f:
                res_json = json.load(f)
                self.res_json = res_json

        self.req_fields = [str(v['field_name']) for v in req_json]
        self.res_fields = [str(v['field_name']) for v in res_json]

        req_type_rules_task = asyncio.create_task(
            self._req_type_rules(req_type_rules_path, req_json)
        )
        res_type_rules_task = asyncio.create_task(
            self._res_type_rules(res_type_rules_path, res_json)
        )
        self.req_type_rules = await req_type_rules_task
        self.res_type_rules = await res_type_rules_task

        self.req_types = self._types_from_rules(self.req_type_rules)
        self.res_types = self._types_from_rules(self.res_type_rules)

        if not self.req_types:
            self.req_types = self._types_from_field_values(req_json)
        if not self.res_types:
            self.res_types = self._types_from_field_values(res_json)

        logger.debug('RFCParser: finish key field extraction')
        
    def combine_field(
        self,
        fields: list[dict]
    ) -> set[str]:
        """Combine fields to generate new request/response type if necessary

        For example, if the combination of two fields can determine the message type, we can combine them together and add the combination into request/response type set.
        """
        from itertools import combinations, product

        ret = set()

        # Normalize input: expect list of dicts with keys 'field_name' and 'value' (list)
        usable = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            name = f.get('field_name') or f.get('name')
            vals = f.get('value')
            if not name or not vals or not isinstance(vals, list):
                continue
            # filter out empty/None values
            clean_vals = [str(v).strip() for v in vals if v is not None and str(v).strip() != '']
            if len(clean_vals) == 0:
                continue
            usable.append((name.strip(), clean_vals))

        # If fewer than 2 usable fields, nothing to combine
        if len(usable) < 2:
            return fields[0]['value'] if len(usable) == 1 else set()

        # For each subset of fields of size >=2, generate Cartesian product of their values
        for r in range(2, len(usable) + 1):
            for combo in combinations(usable, r):
                names = [c[0] for c in combo]
                vals_lists = [c[1] for c in combo]
                for prod in product(*vals_lists):
                    # Format: FieldA=valA|FieldB=valB|...
                    parts = [f"{n}={v}" for n, v in zip(names, prod)]
                    combined = "|".join(parts)
                    ret.add(combined)
        logger.debug(f'Combined fields: {ret}')
        return ret
    
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
        self,
        name: str
    ):
        """Prepare content for ir generation

        concatenate the sections of document with the same type as one augmentation info
        """
        logger.debug(f'query: {self.tree_dict[name]}')
        # self.tree_dict[name].debug_tree()
        for node in self.tree_dict[name].leafs:
            match node.content_type:
                case "request":
                    self.req_doc.add(self.tree_dict[name].fetch_node_content(node))
                    self.all_doc.add(self.tree_dict[name].fetch_node_content(node))
                case "response":
                    self.res_doc.add(self.tree_dict[name].fetch_node_content(node))
                    self.all_doc.add(self.tree_dict[name].fetch_node_content(node))
                case "all":
                    self.all_doc.add(self.tree_dict[name].fetch_node_content(node))
                    self.req_doc.add(self.tree_dict[name].fetch_node_content(node))
                    self.res_doc.add(self.tree_dict[name].fetch_node_content(node))
                case "none":
                    pass
                case _:
                    logger.debug(f"[Section type]: unexpected type")
        if len(self.req_doc) == 0 and len(self.res_doc) == 0:
            logger.debug('RFCParser: bad documents, lack of request and response information')
            sys.exit(1)
            
        logger.debug('[RFCParser]: query prepare')

    async def _spe_parse_async(
        self,
        st: SectionTree
    ):
        logger.debug(f'spe parse: {st}')
        # st.debug_tree()
        sem = asyncio.Semaphore(configs.async_sem_doc)
        tasks = [
            self._spe_parse_one(node, sem, st)
            for node in st.leafs
        ]

        results = await tqdm_asyncio.gather(*tasks, desc=f"Doc Annotation {st.name}")

        # for node, doc_type in results:
        #     node.content_type = doc_type

    async def _spe_parse_one(
        self,
        node: SectionNode,
        sem: asyncio.Semaphore,
        st: SectionTree
    ):
        async with sem:
            error_msg = ""
            while True:
                try:
                    doc = st.fetch_node_content(node)
                    ans = None
                    if doc != None:
                        ans = await self.chater.llm_doc_parse(
                            rfc_num = ' '.join(self.rfc_name),
                            pro_name = self.pro_name,
                            rfc_doc = doc,
                            error_msg = error_msg
                        )
                        if ans is None: raise Exception
                        if ans not in ['request', 'response', 'all', 'none']:
                            continue
                        logger.debug(f'[Tree Annotate]: {node.name}:{ans}')
                        node.content_type = ans
                        break
                except Exception:
                    logger.exception('RFCParser: specification parse error')

    async def _req_field(
            self,
            req_path: Path
    ) -> list[dict]:
        # request field extraction
        if(req_path.is_file()):
            with open(req_path, 'r', encoding='utf-8') as f:
                return json.load(f)
            logger.debug('[IR Generation]: request description load')
        else:
            while(True):
                req_json = None
                try:
                    pmp, req_json = await self.chater.llm_request_query(
                        rfc_num = ' '.join(self.rfc_name),
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.req_doc])
                    )

                    if (req_json != None):
                        req_json = json.loads(req_json)
                        if not self._req_field_check(req_json): 
                            continue
                        with open(req_path, 'w', encoding="utf-8") as f:
                            json.dump(req_json, f)

                        return req_json
                except Exception as e:
                    logger.debug(req_json)
                    logger.debug(f'RFCParser: req field {e}')

    async def _res_field(
            self,
            res_path: Path
    ) -> list[dict]:
        # response field extraction
        if(res_path.is_file()):
            with open(res_path, 'r', encoding='utf-8') as f:
                return json.load(f)
            logger.debug('[IR Generation]: response description load')
        else:
            while(True):
                res_json = None
                try:
                    pmp, res_json = await self.chater.llm_response_query(
                        rfc_num = ' '.join(self.rfc_name),
                        pro_name = self.pro_name,
                        rfc_doc = ''.join([s for s in self.res_doc])
                    )

                    if (res_json != None):
                        res_json = json.loads(res_json)
                        if not self._res_field_check(res_json): 
                            continue
                        with open(res_path, 'w', encoding="utf-8") as f:
                            json.dump(res_json, f)
                        return res_json
                except Exception as e:
                    logger.debug(res_json)
                    logger.debug(f'RFCParser: res field {e}')

    async def _req_type_rules(
            self,
            req_type_rules_path: Path,
            req_json: list[dict]
    ) -> dict:
        if req_type_rules_path.is_file():
            with open(req_type_rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            if self._type_rules_check(rules, 'request'):
                return rules
            logger.debug('RFCParser: invalid cached request type rules')

        while True:
            rules_json = None
            try:
                _, rules_json = await self.chater.llm_request_type_rules(
                    rfc_num=' '.join(self.rfc_name),
                    pro_name=self.pro_name,
                    field_info=json.dumps(req_json),
                    rfc_doc=''.join([s for s in self.req_doc]),
                )
                if rules_json is None:
                    raise ValueError('empty request type rules')
                rules = json.loads(rules_json)
                if not self._type_rules_check(rules, 'request'):
                    continue
                with open(req_type_rules_path, 'w', encoding='utf-8') as f:
                    json.dump(rules, f)
                return rules
            except Exception as e:
                logger.debug(rules_json)
                logger.debug(f'RFCParser: request type rules {e}')

    async def _res_type_rules(
            self,
            res_type_rules_path: Path,
            res_json: list[dict]
    ) -> dict:
        if res_type_rules_path.is_file():
            with open(res_type_rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            if self._type_rules_check(rules, 'response'):
                return rules
            logger.debug('RFCParser: invalid cached response type rules')

        while True:
            rules_json = None
            try:
                _, rules_json = await self.chater.llm_response_type_rules(
                    rfc_num=' '.join(self.rfc_name),
                    pro_name=self.pro_name,
                    field_info=json.dumps(res_json),
                    rfc_doc=''.join([s for s in self.res_doc]),
                )
                if rules_json is None:
                    raise ValueError('empty response type rules')
                rules = json.loads(rules_json)
                if not self._type_rules_check(rules, 'response'):
                    continue
                with open(res_type_rules_path, 'w', encoding='utf-8') as f:
                    json.dump(rules, f)
                return rules
            except Exception as e:
                logger.debug(rules_json)
                logger.debug(f'RFCParser: response type rules {e}')
    
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
                except Exception as e:
                    logger.debug(f'RFCParser: [bad xml format] {msg_type} err: {e}')
                    fix_ir = await self.chater.llm_ir_repair(
                                ir=msg_ir,
                                error=str(e)
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
            sem = asyncio.Semaphore(configs.async_sem_doc)

            m_types  = ''
            if field_type == 'req':
                m_types = self.req_types
                tasks = [
                    self._msg_model_gen_one(msg_type, sem)
                    for msg_type in m_types
                ]
                
            elif field_type == 'res':
                m_types = self.res_types
                tasks = [self._msg_model_gen_one(f'response message of {self.pro_name} protocol', sem)]

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
            sem = asyncio.Semaphore(configs.async_sem_doc)
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
            info = self.rag_res_msg.top_k_sentence([req_type], 8)
            while(True):
                ans_str = None
                try:
                    ans_str = await self.chater.llm_possible_res(
                        pro_name=self.pro_name,
                        current_request=req_type,
                        response_types=json.dumps(list(self.res_types)),
                        info=''.join([' '.join(item[0]) for item in info])
                    )
                    cur_poss_res = json.loads(ans_str)
                    return req_type, cur_poss_res['possible_response']
                except Exception as e:
                    logger.debug(ans_str)
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
            sem = asyncio.Semaphore(configs.async_sem_doc)
            tasks = [
                self._state_dependency_one(last_req, cur_req, sem)
                for last_req in self.req_types
                for cur_req in self.req_types
            ]

            results = await tqdm_asyncio.gather(*tasks, desc='dependency')

            for last_req, cur_req, relation in results:
                if relation['request_dependency'] == 'dependent':
                    cur_dict = self.req_dep_map.setdefault(cur_req, {})
                    cur_dict.setdefault(last_req, relation)

            with open(req_dep_path, 'w') as f:
                json.dump(self.req_dep_map, f)
        

    async def _state_dependency_one(
            self,
            last_req: str,
            cur_req: str,
            sem
    ):
        query = [last_req, cur_req]
        results = self.rag_all.top_k_sentence(query, 8)
        async with sem:
            while(True):
                try:
                    ans_str = await self.chater.llm_infer_dependency(
                        last_request=last_req,
                        pro_name=self.pro_name,
                        current_request=cur_req,
                        response_types=json.dumps(list(self.res_types)),
                        rfc_content=''.join([' '.join(item[0]) for item in results])
                    )
                    relation = json.loads(ans_str)
                    return last_req, cur_req, relation
                except Exception as e:
                    logger.debug(ans_str)
                    logger.debug(f'RFCParser: dependency failure {e}')


    def _req_field_check(
            self,
            data: list[dict]
    ) -> bool:
        """Check the json content of message field information

        Args:
            data: json file of message format

        Return:
            True or False
        """
        for ele in data:
            if len(ele) != 4: 
                return False
            for key in ele.keys():
                if key not in ['field_name', 'position', 'explanation', 'value']:
                    logger.debug('bad json')
                    return False
        return True
    
    def _res_field_check(
            self,
            data: list[dict]
    ) -> bool:
        """Check the json content of message field information

        Args:
            data: json file of message format

        Return:
            True or False
        """
        for ele in data:
            if len(ele) != 4: 
                return False
            for key in ele.keys():
                if key not in ['field_name', 'position', 'explanation', 'value']:
                    logger.debug('bad json')
                    return False
        return True

    def _type_rules_check(
            self,
            data: dict,
            direction: str
    ) -> bool:
        if not isinstance(data, dict):
            return False
        if data.get('message_direction') != direction:
            return False
        if not isinstance(data.get('primary_fields'), list):
            return False
        if not all(isinstance(field, str) for field in data['primary_fields']):
            return False
        if not isinstance(data.get('types'), list):
            return False

        for item in data['types']:
            if not isinstance(item, dict):
                return False
            if not isinstance(item.get('type_name'), str):
                return False
            if not item['type_name'].strip():
                return False
            if not isinstance(item.get('field_values'), dict):
                return False
            if len(item['field_values']) == 0:
                return False
            if not all(
                isinstance(name, str) and str(value).strip() != ''
                for name, value in item['field_values'].items()
            ):
                return False
            if not isinstance(item.get('explanation'), str):
                return False
        return True

    def _types_from_rules(
            self,
            rules: dict
    ) -> set[str]:
        if not isinstance(rules, dict):
            return set()
        return {
            item['type_name'].strip()
            for item in rules.get('types', [])
            if (
                isinstance(item, dict)
                and isinstance(item.get('type_name'), str)
                and item['type_name'].strip()
            )
        }

    def _types_from_field_values(
            self,
            fields: list[dict]
    ) -> set[str]:
        if not fields:
            return set()
        values = fields[0].get('value')
        if not isinstance(values, list):
            return set()
        return {
            str(value)
            for value in values
            if value is not None and str(value).strip() != ''
        }
    
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
        self,
        name: str
    ) -> SectionTree:
        """Load and validate one cached RFC SectionTree."""
        tree_path = self.ir_path / f"{name}.pkl"
        with tree_path.open("rb") as f:
            st = pickle.load(f)
        if not isinstance(st, SectionTree):
            raise TypeError(
                f"expected SectionTree, got {type(st).__name__}"
            )
        if not isinstance(getattr(st, "leafs", None), list):
            raise ValueError("SectionTree leaf list is missing or invalid")
        if not isinstance(getattr(st, "doc_content", None), str):
            raise ValueError("SectionTree document content is missing")
        self.tree_dict[name] = st
        return st

    def prepare_section_tree(
        self,
        idx: int,
        name: str,
    ) -> str:
        """Load a valid cache or regenerate it from the RFC document."""
        tree_path = self.ir_path / f"{name}.pkl"
        if tree_path.is_file():
            try:
                self.load_st(name)
                return "loaded"
            except Exception:
                self.tree_dict.pop(name, None)
                logger.exception(
                    f"RFCParser: damaged SectionTree cache; regenerating "
                    f"[{name}] path={tree_path}"
                )

        self.spe_parse(idx)
        if name not in self.tree_dict:
            raise RuntimeError(
                f"RFCParser: SectionTree regeneration produced no tree "
                f"[{name}]"
            )
        return "regenerated"
        
    def save_st(
        self,
        st: SectionTree
    ):
        """Atomically persist a SectionTree to avoid truncated caches."""
        target_path = self.ir_path / f"{st.name}.pkl"
        temp_path = target_path.with_suffix(
            f"{target_path.suffix}.tmp-{os.getpid()}"
        )
        try:
            with temp_path.open("wb") as f:
                pickle.dump(st, f)
                f.flush()
                os.fsync(f.fileno())
            temp_path.replace(target_path)
            logger.debug("RFCParser: save sectiontree")
        finally:
            temp_path.unlink(missing_ok=True)

    def rag_init(
        self,
        sections: list[str]
    ) -> fastbm25:
        corpus = [s.split() for s in sections]
        bm25 = fastbm25(corpus)
        return bm25
    

    

    






    
