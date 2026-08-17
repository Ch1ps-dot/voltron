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
    ANNOTATION_MAX_ATTEMPTS = 3
    ANNOTATION_TIMEOUT_S = 30.0
    IR_REPAIR_MAX_ATTEMPTS = 3
    # SMTP reply types are a closed, standards-defined catalog.  Keeping this
    # list deterministic prevents a cached LLM extraction from silently
    # shrinking the runtime response alphabet to a handful of examples.
    SMTP_REPLY_CODE_CATALOG: tuple[tuple[str, str], ...] = (
        ('211', 'System status or system help reply (RFC 5321).'),
        ('214', 'Help message reply (RFC 5321).'),
        ('220', 'Service ready (RFC 5321).'),
        ('221', 'Service closing transmission channel (RFC 5321).'),
        ('235', 'Authentication successful (RFC 4954).'),
        ('250', 'Requested mail action completed (RFC 5321).'),
        ('251', 'User not local; will forward (RFC 5321).'),
        ('252', 'Cannot verify user, but will accept message (RFC 5321).'),
        ('334', 'Authentication challenge (RFC 4954).'),
        ('354', 'Start mail input (RFC 5321).'),
        ('421', 'Service not available (RFC 5321).'),
        ('432', 'Temporary authentication failure (RFC 4954).'),
        ('450', 'Mailbox unavailable (RFC 5321).'),
        ('451', 'Requested action aborted (RFC 5321).'),
        ('452', 'Insufficient system storage (RFC 5321).'),
        ('454', 'Temporary authentication or TLS failure (RFC 4954/RFC 3207).'),
        ('455', 'Server unable to accommodate parameters (RFC 5321).'),
        ('458', 'Unable to process ETRN command (RFC 1985).'),
        ('459', 'ETRN parameter not recognized (RFC 1985).'),
        ('500', 'Syntax error, command unrecognized (RFC 5321).'),
        ('501', 'Syntax error in parameters (RFC 5321).'),
        ('502', 'Command not implemented (RFC 5321).'),
        ('503', 'Bad sequence of commands (RFC 5321).'),
        ('504', 'Command parameter not implemented (RFC 5321).'),
        ('530', 'Must issue STARTTLS command first (RFC 3207).'),
        ('534', 'Authentication mechanism too weak (RFC 4954).'),
        ('535', 'Authentication credentials invalid (RFC 4954).'),
        ('538', 'Encryption required for authentication (RFC 4954; deprecated).'),
        ('550', 'Mailbox unavailable (RFC 5321).'),
        ('551', 'User not local (RFC 5321).'),
        ('552', 'Exceeded storage allocation (RFC 5321).'),
        ('553', 'Mailbox name not allowed (RFC 5321).'),
        ('554', 'Transaction failed (RFC 5321).'),
        ('555', 'MAIL FROM or RCPT TO parameters not recognized (RFC 5321).'),
    )

    def _apply_smtp_response_catalog(
            self,
            fields: list[dict],
            rules: dict,
    ) -> tuple[list[dict], dict]:
        """Normalize SMTP reply types without altering extended-status fields."""
        if str(getattr(self, 'pro_name', '')).lower() != 'smtp':
            return fields, rules

        reply_field = next(
            (
                field for field in fields
                if str(field.get('field_name', '')).casefold() == 'smtp reply code'
            ),
            None,
        )
        if reply_field is None:
            return fields, rules

        field_name = str(reply_field['field_name'])
        codes = [code for code, _ in self.SMTP_REPLY_CODE_CATALOG]
        normalized_fields = [
            {**field, 'value': codes}
            if field is reply_field else field
            for field in fields
        ]
        normalized_rules = {
            'message_direction': 'response',
            'primary_fields': [field_name],
            'types': [
                {
                    'type_name': code,
                    'field_values': {field_name: code},
                    'explanation': explanation,
                }
                for code, explanation in self.SMTP_REPLY_CODE_CATALOG
            ],
        }
        return normalized_fields, normalized_rules

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
        self.tree_base_path = configs.base_path / 'component' / 'tree'
        self.tree_path = self.tree_base_path / configs.pro_name
        self.ir_base_path.mkdir(parents=True, exist_ok=True)
        self.ir_path.mkdir(parents=True, exist_ok=True)
        self.tree_base_path.mkdir(parents=True, exist_ok=True)
        self.tree_path.mkdir(parents=True, exist_ok=True)

        self.poss_res: dict[str, list[str]] = {}
        self.req_dep_map: dict[str, dict[str, dict]] = {} # dependency between requests

        self.req_ir = None
        self.res_ir = None

    def run(
        self,
        use_spec_knowledge: bool = True,
    ):
        if not use_spec_knowledge:
            self.bootstrap_without_specification()
            logger.debug('RFCParser: LLM-only type bootstrap completed')
            return

        section_trees = self.parse_section_trees()
        for name, _ in section_trees:
            self._query_prepare(name)
            logger.debug('RFCParser: finish parse')

        self.rag_req_msg: fastbm25 = self.rag_init(list(self.req_doc))
        self.rag_res_msg: fastbm25 = self.rag_init(list(self.res_doc))
        self.rag_all: fastbm25 = self.rag_init(list(self.all_doc))

        # ir generation
        self.ir_generation()

    def bootstrap_without_specification(self) -> None:
        """Build minimal type metadata from model priors, never cached equipment.

        This is intentionally a separate path from RFC parsing.  In
        particular, it must not read previous generators, parsers, IR, or
        SectionTrees, otherwise the no-specification ablation leaks knowledge
        from a full run.
        """
        payload = asyncio.run(self.chater.llm_no_spec_type_bootstrap(
            pro_name=self.pro_name,
            transport=str(getattr(configs, 'trans_layer', 'tcp')),
        ))
        request = payload.get('request') if isinstance(payload, dict) else None
        response = payload.get('response') if isinstance(payload, dict) else None
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise RuntimeError('no_spec_bootstrap_failure: missing request/response catalog')

        def normalize(direction: str, catalog: dict) -> tuple[str, list[dict]]:
            field_name = str(catalog.get('field_name') or f'{direction} type').strip()
            raw_types = catalog.get('types')
            if not field_name or not isinstance(raw_types, list):
                raise RuntimeError(
                    f'no_spec_bootstrap_failure: invalid {direction} catalog'
                )
            types: list[dict] = []
            for item in raw_types:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('type_name') or '').strip()
                value = str(item.get('wire_value') or '').strip()
                if name and value:
                    types.append({
                        'type_name': name,
                        'field_values': {field_name: value},
                        'explanation': str(item.get('explanation') or ''),
                    })
            if not types:
                raise RuntimeError(
                    f'no_spec_bootstrap_failure: empty {direction} catalog'
                )
            return field_name, types

        req_field, req_rules = normalize('request', request)
        res_field, res_rules = normalize('response', response)
        self.req_fields = [req_field]
        self.res_fields = [res_field]
        self.req_type_rules = {
            'message_direction': 'request',
            'primary_fields': [req_field],
            'types': req_rules,
        }
        self.res_type_rules = {
            'message_direction': 'response',
            'primary_fields': [res_field],
            'types': res_rules,
        }
        self.req_json = [{
            'field_name': req_field,
            'position': 'protocol-defined request discriminator',
            'explanation': 'LLM-only bootstrap; no RFC or IR context used.',
            'value': [rule['field_values'][req_field] for rule in req_rules],
        }]
        self.res_json = [{
            'field_name': res_field,
            'position': str(response.get('wire_hint') or 'response discriminator'),
            'explanation': 'LLM-only bootstrap; no RFC or IR context used.',
            'value': [rule['field_values'][res_field] for rule in res_rules],
        }]
        self.req_types = self._types_from_rules(self.req_type_rules)
        self.res_types = self._types_from_rules(self.res_type_rules)
        self.req_dep_map = {}
        self.poss_res = {}

        root = etree.Element('ir')
        for rule in req_rules:
            message = etree.SubElement(
                root, 'message', name=rule['type_name'], direction='request',
            )
            etree.SubElement(
                message, 'field', name=req_field, type='constant',
                length='undefined', value=rule['field_values'][req_field],
            )
        self.req_ir = etree.ElementTree(root)
        self.res_ir = None

    def ensure_rfc_documents(
        self,
    ) -> None:
        """Download configured RFC documents when the helper is available."""
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

    def parse_section_trees(
        self,
    ) -> list[tuple[str, str]]:
        """Parse configured RFC documents into cached SectionTree objects only.

        Returns:
            A list of ``(RFC name, source)`` pairs. ``source`` is ``loaded``
            when a valid cache was reused and ``regenerated`` when the source
            document was parsed and persisted.
        """
        self.ensure_rfc_documents()
        rfc_list = (
            self.rfc_name
            if isinstance(self.rfc_name, list)
            else [self.rfc_name]
        )
        if len(self.doc_paths) != len(rfc_list):
            raise ValueError(
                'RFCParser: RFC names and document paths have different '
                f'lengths ({len(rfc_list)} != {len(self.doc_paths)})'
            )

        results: list[tuple[str, str]] = []
        for i in range(len(self.doc_paths)):
            name = str(rfc_list[i])
            logger.debug(f'create st: {name}')
            source = self.prepare_section_tree(i, name)
            logger.debug(f'RFCParser: sectiontree {source} [{name}]')
            results.append((name, source))
        return results

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

        normalized_res_json, normalized_res_type_rules = (
            self._apply_smtp_response_catalog(res_json, self.res_type_rules)
        )
        if normalized_res_json != res_json:
            with open(res_path, 'w', encoding='utf-8') as f:
                json.dump(normalized_res_json, f, indent=2)
                f.write('\n')
            self.res_json = normalized_res_json
            res_json = normalized_res_json
        if normalized_res_type_rules != self.res_type_rules:
            with open(res_type_rules_path, 'w', encoding='utf-8') as f:
                json.dump(normalized_res_type_rules, f, indent=2)
                f.write('\n')
            self.res_type_rules = normalized_res_type_rules
        self.res_fields = [str(v['field_name']) for v in res_json]

        self.req_types = self._types_from_rules(self.req_type_rules)
        self.res_types = self._types_from_rules(self.res_type_rules)

        if not self.req_types:
            self.req_types = self._types_from_field_values(req_json)
        if not self.res_types:
            self.res_types = self._types_from_field_values(res_json)

        await self._annotate_section_message_types()

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
            doc = st.fetch_node_content(node)
            for attempt in range(1, self.ANNOTATION_MAX_ATTEMPTS + 1):
                try:
                    ans = await asyncio.wait_for(
                        self.chater.llm_doc_parse(
                            rfc_num=' '.join(self.rfc_name),
                            pro_name=self.pro_name,
                            rfc_doc=doc,
                        ),
                        timeout=self.ANNOTATION_TIMEOUT_S,
                    )
                    normalized = (
                        ans.strip().lower()
                        if isinstance(ans, str)
                        else ''
                    )
                    if not normalized:
                        # An empty model answer carries no evidence that the
                        # excerpt belongs to a request or response.  Treat it
                        # as the conservative ``none`` class instead of
                        # spending the bounded retry budget on the same
                        # empty completion.
                        node.content_type = 'none'
                        logger.debug(
                            f'[Tree Annotate]: {node.name}:none '
                            '(empty response)'
                        )
                        return
                    if normalized not in {'request', 'response', 'all', 'none'}:
                        raise ValueError(
                            f'invalid document annotation: {ans!r}'
                        )
                    logger.debug(
                        f'[Tree Annotate]: {node.name}:{normalized}'
                    )
                    node.content_type = normalized
                    return
                except Exception as error:
                    if getattr(error, 'reason', None) == 'empty_response':
                        node.content_type = 'none'
                        logger.debug(
                            f'[Tree Annotate]: {node.name}:none '
                            '(empty response validation failure)'
                        )
                        return
                    logger.debug(
                        'RFCParser: specification annotation attempt '
                        f'{attempt}/{self.ANNOTATION_MAX_ATTEMPTS} failed '
                        f'[{node.name}]: {error}'
                    )

            fallback = self._document_annotation_fallback(node, doc)
            node.content_type = fallback or 'none'
            if fallback:
                logger.warning(
                    'RFCParser: document annotation exhausted; using '
                    f'local {fallback} fallback [{st.name}] [{node.name}]'
                )
                return
            logger.warning(
                'RFCParser: document annotation exhausted; using none '
                f'[{st.name}] [{node.name}]'
            )

    @staticmethod
    def _document_annotation_fallback(
            node: SectionNode,
            document: str,
    ) -> str | None:
        """Classify unambiguous wire-format sections without an LLM.

        The fallback deliberately recognizes only two forms: a numbered
        section whose title is an absolute URI (a request endpoint), and a
        section explicitly called "Sample Response" that contains an HTTP
        status line.  It is used only after all LLM annotation attempts fail,
        so normal model annotations remain authoritative.
        """
        title = str(getattr(node, 'name', '')).strip()
        content = str(document or '')

        if re.match(r'^\d+(?:\.\d+)*\s+/\S+', title):
            return 'request'

        if (
            re.search(r'\bsample\s+response\b', title, re.IGNORECASE)
            and re.search(
                r'^\s*(?:HTTP/\d(?:\.\d)?\s+\d{3}\b|\d{3}\b)',
                content,
                re.MULTILINE,
            )
        ):
            return 'response'

        return None

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
                        rfc_doc = self._field_query_context('request')
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
                        rfc_doc = self._field_query_context('response')
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
                    rfc_doc=self._field_query_context('request'),
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
                    rfc_doc=self._field_query_context('response'),
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

    async def _annotate_section_message_types(
            self
    ) -> None:
        tree_dict = getattr(self, 'tree_dict', {})
        if not tree_dict:
            return
        if not self.req_types and not self.res_types:
            return

        for st in tree_dict.values():
            self._ensure_section_tree_compat(st)
            if self._section_type_annotations_current(st):
                continue

            sem = asyncio.Semaphore(getattr(configs, 'async_sem_doc', 1))
            tasks = [
                self._annotate_section_message_types_one(st, node, sem)
                for node in st.leafs
            ]
            await tqdm_asyncio.gather(
                *tasks,
                desc=f"Section Type Annotation {st.name}"
            )
            self._mark_section_type_annotations(st)
            self.save_st(st)

    async def _annotate_section_message_types_one(
            self,
            st: SectionTree,
            node: SectionNode,
            sem: asyncio.Semaphore
    ) -> None:
        self._ensure_section_node_compat(node)
        if node.content_type == 'none':
            node.related_request_types = []
            node.related_response_types = []
            return

        request_types = sorted(self.req_types)
        response_types = sorted(self.res_types)
        allowed_request_types = set(request_types)
        allowed_response_types = set(response_types)

        async with sem:
            annotation_json = None
            for attempt in range(1, self.ANNOTATION_MAX_ATTEMPTS + 1):
                try:
                    _, annotation_json = await asyncio.wait_for(
                        self.chater.llm_section_type_annotation(
                            rfc_num=' '.join(self.rfc_name),
                            pro_name=self.pro_name,
                            request_types=json.dumps(request_types),
                            response_types=json.dumps(response_types),
                            content_type=node.content_type,
                            section_name=node.name,
                            section_content=st.fetch_node_content(node),
                        ),
                        timeout=self.ANNOTATION_TIMEOUT_S,
                    )
                    if annotation_json is None:
                        raise ValueError('empty section type annotation')
                    annotation = json.loads(annotation_json)
                    if not self._section_type_annotation_check(
                        annotation,
                        allowed_request_types,
                        allowed_response_types
                    ):
                        continue
                    node.related_request_types = list(dict.fromkeys(
                        str(item)
                        for item in annotation['request_types']
                    ))
                    node.related_response_types = list(dict.fromkeys(
                        str(item)
                        for item in annotation['response_types']
                    ))
                    return
                except Exception as e:
                    logger.debug(annotation_json)
                    logger.debug(
                        'RFCParser: section type annotation attempt '
                        f'{attempt}/{self.ANNOTATION_MAX_ATTEMPTS} failed '
                        f'[{st.name}] [{node.name}]: {e}'
                    )

            node.related_request_types = []
            node.related_response_types = []
            logger.warning(
                'RFCParser: section type annotation exhausted; using empty '
                f'associations [{st.name}] [{node.name}]'
            )
    
    async def _msg_model_gen_one(
            self,
            msg_type: str,
            sem: asyncio.Semaphore,
            field_type: str
    ):
        rfc_doc = self._message_ir_context(msg_type, field_type)
        generation_timeout_s = max(
            0.01,
            float(getattr(configs, 'ir_generation_timeout_s', 300.0)),
        )
        async with sem:
            try:
                msg_ir = await asyncio.wait_for(
                    self.chater.llm_ir_generation(
                        pro_name=self.pro_name,
                        message_name=msg_type,
                        message_direction=(
                            'request' if field_type == 'req' else 'response'
                        ),
                        rfc_doc=rfc_doc,
                    ),
                    timeout=generation_timeout_s,
                )
            except asyncio.TimeoutError as error:
                raise RuntimeError(
                    'RFCParser: message IR generation timed out '
                    f'[{field_type}] [{msg_type}] after '
                    f'{generation_timeout_s}s'
                ) from error
            last_error = 'empty IR response'
            for attempt in range(1, self.IR_REPAIR_MAX_ATTEMPTS + 1):
                if msg_ir is None or not str(msg_ir).strip():
                    last_error = 'empty IR response'
                else:
                    try:
                        return etree.fromstring(msg_ir)
                    except Exception as error:
                        last_error = str(error)
                        logger.debug(
                            'RFCParser: bad XML format '
                            f'[{msg_type}] attempt '
                            f'{attempt}/{self.IR_REPAIR_MAX_ATTEMPTS}: '
                            f'{error}'
                        )

                if attempt == self.IR_REPAIR_MAX_ATTEMPTS:
                    break
                try:
                    msg_ir = await asyncio.wait_for(
                        self.chater.llm_ir_repair(
                            ir=str(msg_ir or ''),
                            error=last_error,
                        ),
                        timeout=generation_timeout_s,
                    )
                except Exception as error:
                    last_error = str(error)
                    msg_ir = None

            raise RuntimeError(
                'RFCParser: message IR generation failed after '
                f'{self.IR_REPAIR_MAX_ATTEMPTS} attempts '
                f'[{field_type}] [{msg_type}]: {last_error}'
            )

    def _message_ir_context(
            self,
            msg_type: str,
            field_type: str
    ) -> str:
        """Collect SectionTree leaves annotated for the target message type."""
        sections = []
        fallback_sections = []

        for st in getattr(self, 'tree_dict', {}).values():
            self._ensure_section_tree_compat(st)
            for node in st.leafs:
                self._ensure_section_node_compat(node)
                content = st.fetch_node_content(node)
                if not content:
                    continue

                if field_type == 'req':
                    if msg_type in node.related_request_types:
                        sections.append(content)
                    elif node.content_type in {'request', 'all'}:
                        fallback_sections.append(content)
                elif field_type == 'res':
                    if (
                        msg_type in node.related_response_types
                        or (
                            msg_type.startswith('response message of ')
                            and node.related_response_types
                        )
                    ):
                        sections.append(content)
                    elif node.content_type in {'response', 'all'}:
                        fallback_sections.append(content)

        if not sections:
            sections = fallback_sections
        if not sections:
            if field_type == 'req':
                sections = list(self.req_doc)
            elif field_type == 'res':
                sections = list(self.res_doc)
            else:
                sections = list(self.all_doc)
        return '\n\n'.join(sections)

    def _field_query_context(self, direction: str) -> str:
        """Keep protocol-specific evidence when several RFCs share a budget.

        A global join followed by head/tail truncation can drop an entire RFC,
        especially because the coarse document sets are unordered.  Build one
        deterministic block per configured source and compact each block
        independently.  The first source is the protocol's primary document,
        so it receives half of the available context budget.
        """
        accepted_types = (
            {'request', 'all'}
            if direction == 'request'
            else {'response', 'all'}
        )
        rfc_names = [str(name) for name in self.rfc_name]
        source_blocks: list[tuple[str, str]] = []
        for name in rfc_names:
            st = self.tree_dict.get(name)
            if st is None:
                continue
            sections: list[str] = []
            seen: set[str] = set()
            for node in st.leafs:
                if node.content_type not in accepted_types:
                    continue
                content = st.fetch_node_content(node)
                if not content or content in seen:
                    continue
                seen.add(content)
                sections.append(content)
            if sections:
                source_blocks.append((name, '\n\n'.join(sections)))

        if not source_blocks:
            fallback = self.req_doc if direction == 'request' else self.res_doc
            return '\n\n'.join(sorted(fallback))

        max_chars = max(
            512,
            int(getattr(configs, 'prompt_context_max_chars', 12_000)),
        )
        if len(source_blocks) == 1:
            budgets = [max_chars]
        else:
            primary_budget = max_chars // 2
            secondary_budget = max_chars - primary_budget
            each_secondary = secondary_budget // (len(source_blocks) - 1)
            budgets = [primary_budget] + [each_secondary] * (
                len(source_blocks) - 1
            )
            budgets[-1] += max_chars - sum(budgets)

        blocks: list[str] = []
        for (name, content), budget in zip(source_blocks, budgets):
            label = f'[SOURCE {name}]\n'
            content_budget = max(1, budget - len(label) - 2)
            if len(content) > content_budget:
                marker = '\n[... source truncated ...]\n'
                retained = max(2, content_budget - len(marker))
                head_chars = retained * 2 // 3
                content = (
                    content[:head_chars]
                    + marker
                    + content[-(retained - head_chars):]
                )
            blocks.append(label + content)
        return '\n\n'.join(blocks)
    
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
                    self._msg_model_gen_one(msg_type, sem, field_type)
                    for msg_type in m_types
                ]
                
            elif field_type == 'res':
                m_types = self.res_types
                tasks = [
                    self._msg_model_gen_one(
                        f'response message of {self.pro_name} protocol',
                        sem,
                        field_type
                    )
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
            info = self._possible_response_context(req_type)
            while(True):
                ans_str = None
                try:
                    ans_str = await self.chater.llm_possible_res(
                        pro_name=self.pro_name,
                        current_request=req_type,
                        response_types=json.dumps(list(self.res_types)),
                        info=info
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
        rfc_content = self._state_dependency_context(last_req, cur_req)
        async with sem:
            while(True):
                try:
                    ans_str = await self.chater.llm_infer_dependency(
                        last_request=last_req,
                        pro_name=self.pro_name,
                        current_request=cur_req,
                        response_types=json.dumps(list(self.res_types)),
                        rfc_content=rfc_content
                    )
                    relation = json.loads(ans_str)
                    return last_req, cur_req, relation
                except Exception as e:
                    logger.debug(ans_str)
                    logger.debug(f'RFCParser: dependency failure {e}')

    def _possible_response_context(
            self,
            req_type: str
    ) -> str:
        sections = []
        fallback_sections = []

        for st in getattr(self, 'tree_dict', {}).values():
            self._ensure_section_tree_compat(st)
            for node in st.leafs:
                self._ensure_section_node_compat(node)
                content = st.fetch_node_content(node)
                if not content:
                    continue

                if (
                    req_type in node.related_request_types
                    or node.related_response_types
                ):
                    sections.append(content)
                elif node.content_type in {'response', 'all'}:
                    fallback_sections.append(content)

        if not sections:
            sections = fallback_sections
        if not sections:
            sections = list(self.res_doc)
        return '\n\n'.join(sections)

    def _state_dependency_context(
            self,
            last_req: str,
            cur_req: str
    ) -> str:
        sections = []
        fallback_sections = []

        for st in getattr(self, 'tree_dict', {}).values():
            self._ensure_section_tree_compat(st)
            for node in st.leafs:
                self._ensure_section_node_compat(node)
                content = st.fetch_node_content(node)
                if not content:
                    continue

                if (
                    last_req in node.related_request_types
                    or cur_req in node.related_request_types
                ):
                    sections.append(content)
                elif node.content_type in {'request', 'all'}:
                    fallback_sections.append(content)

        if not sections:
            sections = fallback_sections
        if not sections:
            sections = list(self.all_doc)
        return '\n\n'.join(sections)


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

    def _section_type_annotation_check(
            self,
            data: dict,
            allowed_request_types: set[str],
            allowed_response_types: set[str]
    ) -> bool:
        if not isinstance(data, dict):
            return False
        request_types = data.get('request_types')
        response_types = data.get('response_types')
        if not isinstance(request_types, list):
            return False
        if not isinstance(response_types, list):
            return False
        if not all(isinstance(item, str) for item in request_types):
            return False
        if not all(isinstance(item, str) for item in response_types):
            return False
        if not set(request_types).issubset(allowed_request_types):
            return False
        if not set(response_types).issubset(allowed_response_types):
            return False
        return True

    def _ensure_section_node_compat(
            self,
            node: SectionNode
    ) -> None:
        if not hasattr(node, 'related_request_types'):
            node.related_request_types = []
        if not hasattr(node, 'related_response_types'):
            node.related_response_types = []

    def _ensure_section_tree_compat(
            self,
            st: SectionTree
    ) -> None:
        for node in getattr(st, 'leafs', []):
            self._ensure_section_node_compat(node)
        if not hasattr(st, 'section_type_annotation_req_types'):
            st.section_type_annotation_req_types = []
        if not hasattr(st, 'section_type_annotation_res_types'):
            st.section_type_annotation_res_types = []

    def _section_type_annotations_current(
            self,
            st: SectionTree
    ) -> bool:
        self._ensure_section_tree_compat(st)
        return (
            sorted(getattr(st, 'section_type_annotation_req_types', []))
            == sorted(self.req_types)
            and sorted(getattr(st, 'section_type_annotation_res_types', []))
            == sorted(self.res_types)
            and all(
                hasattr(node, 'related_request_types')
                and hasattr(node, 'related_response_types')
                for node in st.leafs
            )
        )

    def _mark_section_type_annotations(
            self,
            st: SectionTree
    ) -> None:
        st.section_type_annotation_req_types = sorted(self.req_types)
        st.section_type_annotation_res_types = sorted(self.res_types)
    
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
        target_path = self.tree_path / f"{name}.pkl"
        with target_path.open("rb") as f:
            st = pickle.load(f)
        if not isinstance(st, SectionTree):
            raise TypeError(
                f"expected SectionTree, got {type(st).__name__}"
            )
        if not isinstance(getattr(st, "leafs", None), list):
            raise ValueError("SectionTree leaf list is missing or invalid")
        if not isinstance(getattr(st, "doc_content", None), str):
            raise ValueError("SectionTree document content is missing")
        self._ensure_section_tree_compat(st)
        self.tree_dict[name] = st
        return st

    def prepare_section_tree(
        self,
        idx: int,
        name: str,
    ) -> str:
        """Load a valid cache or regenerate it from the RFC document."""
        target_path = self.tree_path / f"{name}.pkl"
        if target_path.is_file():
            try:
                self.load_st(name)
                return "loaded"
            except Exception:
                self.tree_dict.pop(name, None)
                logger.exception(
                    f"RFCParser: damaged SectionTree cache; regenerating "
                    f"[{name}] path={target_path}"
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
        self._ensure_section_tree_compat(st)
        self.tree_path.mkdir(parents=True, exist_ok=True)
        target_path = self.tree_path / f"{st.name}.pkl"
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
    

    

    






    
