from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio, hashlib
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio
from urllib.parse import quote

from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.rfcparser.rfc_parser import AsyncRFCParser
from voltron.utils.logger import logger_fuzz as logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.analyzer.compliance import (
    build_compliance_prompt,
    collect_response_sections,
    parse_compliance_result,
    retrieve_response_sections,
)
from voltron.llm.chatter import AsyncChater
from voltron.learner.automata import MealyMachine
from dataclasses import dataclass, asdict, field
    


class AsyncProducer:
    """Prepare message producer, parser, mutator, and response checker.
    
    Atrributes:
        *_path: lots of file path
        chater: the chater to call LLM
        rfcp: the RFC parser to provide IR and dependency information
        req_types: the types of request messages
        res_types: the types of response messages
        req_dep: the dependency between request messages
        poss_response: possible response for each request message
        generators: the generated input generators
        parsers: the generated packet parsers
        checkers: the generated response conformance checkers
        mutators: the generated mutators
    """

    def __init__(
            self,
            chater: AsyncChater,
            rfcp: AsyncRFCParser,
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.equipment_path = configs.base_path / 'component' / 'equipment' 
        self.synthesizer_path = self.equipment_path / configs.target_name
        self.generator_path = self.synthesizer_path / 'generators'
        self.mutator_path = self.synthesizer_path / 'mutators'
        self.parser_path = self.synthesizer_path / 'parsers'
        self.checker_path = self.synthesizer_path / 'checkers'
        self.observer_path = self.synthesizer_path / 'observers'
        self.legacy_observer_path = self.synthesizer_path / 'hashers'
        self.info_path = configs.info_path
        
        self.generator_info_path = self.generator_path / 'generator_info.json'
        self.parser_info_path = self.parser_path / 'parser_info.json'
        self.checker_info_path = self.checker_path / 'checker_info.json'
        self.observer_info_path = self.observer_path / 'observer_info.json'
        self.legacy_observer_info_path = (
            self.legacy_observer_path / 'hasher_info.json'
        )
        self.mutator_info_path = self.mutator_path / 'mutator_info.json'
        
        for path in (
            self.generator_path,
            self.parser_path,
            self.checker_path,
            self.observer_path,
            self.mutator_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.chater = chater
        self.rfcp = rfcp
        
        # types of symbols
        self.req_types: set[str] = self.rfcp.req_types
        self.res_types: set[str] = self.rfcp.res_types
        self.req_dep: dict[str, dict[str, dict]] = self.rfcp.req_dep_map
        self.poss_response: dict[str, list[str]] = self.rfcp.poss_res
        
        self.generators: dict[str, list[Generator]] = {}
        self.parsers: list[Parser] = []
        self.checkers: dict[str, list[Checker]] = {}
        self.observers: dict[str, list[ResponseObserver]] = {}
        self.mutators: dict[str, list[Generator]] = {}
        self._response_sections = None
        self._ir_evolution_rounds: dict[str, int] = {}
            
    def run(
        self
    ):
        """Load or generate initial generators, parser, checker, and mutators.
        """
        # load existed generator info or generate init generators
        if(self.generator_info_path.is_file()):
            try:
                with open(self.generator_info_path, 'r', encoding='utf-8') as f:
                    generator_info = json.load(f)
                    self.generators_info_load(generator_info)
                logger.debug("Producer: load generator")
            except Exception as e:
                logger.debug(f'Producer: generator load error {e}')
                exit(1)
        else:
            if not configs.spec_knowledge:
                raise RuntimeError(
                    'Specification knowledge is disabled, but no cached '
                    f'generators exist at {self.generator_info_path}'
                )
            self.generator_gen()
        
        # load existed parser info or generate init parser
        if (self.parser_info_path.is_file()):
            try:
                with open(self.parser_info_path, 'r', encoding='utf-8') as f:
                    parser_info = json.load(f)
                    self.parsers_info_load(parser_info)
                logger.debug("Producer: load parser info")
                if (
                    configs.spec_knowledge
                    and not self._parser_cache_matches_primary_field()
                ):
                    logger.debug(
                        'Producer: parser cache does not match the primary '
                        'response field; regenerating'
                    )
                    self.parsers = []
                    self.parser_gen()
            except Exception as e:
                logger.debug(f'Producer: parser load error {e}')
        else:
            if not configs.spec_knowledge:
                raise RuntimeError(
                    'Specification knowledge is disabled, but no cached '
                    f'parser exists at {self.parser_info_path}'
                )
            self.parser_gen()

        if configs.fuzz_mode != 'replay':
            self._load_checkers()
            self._load_observers()

        # load existed parser info or generate init mutator
        if (self.mutator_info_path.is_file()):
            try:
                with open(self.mutator_info_path, 'r', encoding='utf-8') as f:
                    mutator_info = json.load(f)
                    self.mutators_info_load(mutator_info)
                logger.debug("Mutator: load mutator info")
            except Exception as e:
                logger.debug(f'Mutator: load error {e}')

        if not configs.spec_knowledge:
            self.generators = {
                msg_type: generators[:1]
                for msg_type, generators in self.generators.items()
                if generators
            }
            self.parsers = self.parsers[:1]
            self.checkers = {
                msg_type: checkers[:1]
                for msg_type, checkers in self.checkers.items()
                if checkers
            }
            self.observers = {
                msg_type: observers[:1]
                for msg_type, observers in self.observers.items()
                if observers
            }
            self.mutators = {}

    def _load_checkers(self) -> None:
        """Load or synthesize response checkers outside replay mode."""
        if self.checker_info_path.is_file():
            try:
                with open(self.checker_info_path, 'r', encoding='utf-8') as f:
                    checker_info = json.load(f)
                if isinstance(checker_info, dict):
                    self.checkers_info_load(checker_info)
                    logger.debug("Producer: load checker info")
                    if (
                        configs.spec_knowledge
                        and not self._checker_cache_matches_response_types()
                    ):
                        logger.debug(
                            'Producer: checker cache does not match response '
                            'types from the primary state field; regenerating'
                        )
                        self.checker_gen()
                elif configs.spec_knowledge:
                    logger.debug(
                        "Producer: legacy checker cache detected; regenerating"
                    )
                    self.checker_gen()
                else:
                    self.legacy_checkers_info_load(checker_info)
                    logger.debug("Producer: load legacy checker info")
            except Exception as e:
                logger.debug(f'Producer: checker load error {e}')
        elif configs.spec_knowledge:
            self.checker_gen()

    def _load_observers(self) -> None:
        """Load or synthesize response observers outside replay mode."""
        info_path = self.observer_info_path
        if not info_path.is_file() and self.legacy_observer_info_path.is_file():
            info_path = self.legacy_observer_info_path

        if info_path.is_file():
            try:
                with info_path.open('r', encoding='utf-8') as f:
                    observer_info = json.load(f)
                self.observers_info_load(observer_info)
                logger.debug("Producer: load observer info")
                if (
                    configs.spec_knowledge
                    and not self._observer_cache_matches_response_types()
                ):
                    logger.debug(
                        'Producer: observer cache does not match response types; '
                        'regenerating'
                    )
                    self.observer_gen()
            except Exception:
                logger.exception('Producer: observer load error')
                if configs.spec_knowledge:
                    self.observer_gen()
        elif configs.spec_knowledge:
            self.observer_gen()

    async def _generator_gen_one(
        self,
        msg,
        sem
    ):
        msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
        msg_type = msg.get('name')
        info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            info = f.read()
        async with sem:
            failure_count = 0
            while(True):
                try:
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_gen(
                        pro_name=self.rfcp.pro_name,
                        field_name=self.rfcp.req_fields[0],
                        msg_type=msg_type,
                        msg_ir=msg_ir,
                        info=info,
                        type_rule=self._request_type_rule_info(msg_type),
                    )
                    
                    # test generated code
                    name_space = {}
                    exec(input_code, name_space)
                    obj = name_space[f'generate']
                    obj()
                    
                    return msg_type, input_code
                except Exception as e:
                    logger.debug(f'Producer :generate error {str(e)}')

    async def _generator_gen_async(
        self
    ):
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._generator_gen_one(msg, sem)
            for msg in self.req_ir.findall("message") 
        ]
        results = await tqdm_asyncio.gather(*tasks, desc='generator')
        return results

    def generator_gen(
        self
    ) -> None:
        """Generate and save init input generator
        """
        
        results = asyncio.run(self._generator_gen_async())
        for msg_type, input_code in results:
            msg_dir = self.generator_path / f'{msg_type}'
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            init_gen_path = msg_dir / 'id0.py'
            with open(init_gen_path, 'w', encoding='utf-8') as f:
                f.write(input_code)
                info: dict = {'msg_type': msg_type, 'evolved_from': 'init', 'name': 'id0', 'path': str(init_gen_path.resolve())}
                self.generators.setdefault(msg_type, [])
                self.generators[msg_type].append(Generator(**info))
            
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)
            
        logger.debug("[Producer]: finish generator generation")
        
    async def _generator_evo_one(
        self,
        msg_type: str,
        doc_info:str,
        machine: MealyMachine,
        sem
    ):
        """Generate and save evolved input generator for one message type
        
        Attribute:
            msg_type: the message type of generator to be evolved
            doc_info: the document information to be used for generator evolution
            machine: the current MealyMachine which provides the state transition information for generator evolution
        """
        old_code = ''
        old_g_name = f'id{machine.id}.py'
        old_g_path = self.generator_path / msg_type / old_g_name
        with open(old_g_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
            
        # extract state trace of request pair which has dependency and the code of related generators 
        code_dep: list[str] = []
        trace_list: set[str] = set()
        if msg_type in self.req_dep.keys():
            for last_req, relation in self.req_dep[msg_type].items():
                trace_list.add(machine.get_relation(last_req, msg_type))
                code_dep_path = self.generator_path / last_req / old_g_name
                with open(code_dep_path, 'r', encoding='utf-8') as f:
                    code_dep.append(f.read())
        # for pair in self.req_dep.keys():
        #     last_request = pair.split('/')[0]
        #     current_request = pair.split('/')[1]
        #     if msg_type == last_request and self.req_dep[pair]['request_dependency'] == 'dependent':
        #         trace_list.add(machine.get_relation(last_request, current_request))
                
        async with sem:
            while(True):
                try:
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_evolve(
                        code=old_code,
                        pro_name=self.rfcp.pro_name,
                        field_name=self.rfcp.req_fields[0],
                        msg_type=msg_type,
                        msg_ir=self._request_ir_info(msg_type),
                        trace= '\n'.join(trace_list),
                        info=doc_info,
                        related_code='\n'.join(code_dep)
                    )
                    
                    # test generated code
                    name_space = {}
                    exec(input_code, name_space)
                    obj = name_space[f'generate']
                    obj()
                    msg: bytes | None = obj()
                    if msg == None or msg == b'':
                        raise Exception('mutate return empty')
                    with analyzer.lock:
                        analyzer.finished += 1
                    return msg_type, input_code
                except Exception as e:
                    failure_count += 1
                    if failure_count >= getattr(
                        configs,
                        'ir_evolution_failure_threshold',
                        3,
                    ):
                        await self._maybe_evolve_request_ir(
                            msg_type,
                            (
                                f'generator_evo failed {failure_count} '
                                f'time(s): {type(e).__name__}: {e}'
                            ),
                        )
                        failure_count = 0
                    logger.debug(f'Producer: generate error {e}')

    async def _generator_evo_async(
        self,
        doc_info: str,
        machine: MealyMachine
    ):
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._generator_evo_one(msg_type=msg_type, doc_info=doc_info, machine=machine, sem=sem)
            for msg_type in self.req_types
        ]
        results = await asyncio.gather(*tasks)
        return results

    def generator_evo(
            self,
            machine: MealyMachine
    ) -> None:
        """Evolve and save input generator
        
        Attribute:
            machine: the current MealyMachine which provides the state transition information for generator evolution
        """
        
        with analyzer.lock:
            analyzer.set_progress('evolve', 'evolve', len(self.req_types))
            
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new generator
        results = asyncio.run(self._generator_evo_async(doc_info, machine))
        for msg_type, input_code in results:
            msg_dir = self.generator_path / f'{msg_type}'
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            # save generator
            cur_id = len(self.generators[msg_type])
            gen_path = msg_dir / f'id{cur_id}.py'
            with open(gen_path, 'w', encoding='utf-8') as f:
                f.write(input_code)
                # construct and save information for new generator
                
                old_name = f'id{machine.id}'
                new_name = f'id{cur_id}'
                info: dict = {'msg_type': msg_type, 'evolved_from': old_name, 'name': new_name, 'path': str(gen_path.resolve())}
                self.generators.setdefault(msg_type, [])
                self.generators[msg_type].append(Generator(**info))
                
        # save the information of new generator to file   
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)
        
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug("[Producer]: finish generator generation")
                
    async def _generator_mutate_one(
        self,
        msg_type: str,
        doc_info: str,
        req_res: dict[str, set],
        sem
    ):
        """Generate and save evolved input mutator for one message type
        
        Attribute:
            msg_type: the message type of mutator to be evolved
            doc_info: the document information to be used for mutator evolution
            req_res: the actual response for each request message, which provides the information for mutator evolution
        """
        old_m = self.generators[msg_type][-1]
        old_m_path = old_m.path
        old_code = ''
        with open(old_m_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
                
        async with sem:
            while(True):
                try:
                    # generate input generator and save it
                    logger.debug(self.poss_response)
                    logger.debug(self.poss_response[msg_type])
                    mutate_code = await self.chater.llm_mutator_evolve(
                        code=old_code,
                        pro_name=self.rfcp.pro_name,
                        field_name=self.rfcp.req_fields[0],
                        msg_type=msg_type,
                        msg_ir=self._request_ir_info(msg_type),
                        info=doc_info,
                        poss_response='\n'.join(self.poss_response[msg_type]),
                        trace=json.dumps(
                            sorted(req_res.get(msg_type, set())),
                            ensure_ascii=False,
                        ),
                    )
                    
                    # berserker_code = await self.chater.llm_mutator_berserker(
                    #     code=old_code,
                    #     pro_name=self.rfcp.pro_name,
                    #     msg_type=msg_type,
                    #     info=doc_info
                    # )
                    
                    # test generated code
                    name_space = {}
                    exec(mutate_code, name_space)
                    obj = name_space[f'mutate']
                    msg: bytes | None = obj()
                    if msg == None or msg == b'':
                        raise Exception('mutate return empty')
                    
                    # exec(berserker_code, name_space)
                    # obj = name_space[f'berserker_{msg_type}']
                    # obj()
                    with analyzer.lock:
                        analyzer.finished += 1
                    return msg_type, mutate_code
                except Exception:
                    logger.exception('Producer: mutator generation failed')

    async def _generator_mutate_async(
        self,
        doc_info: str,
        req_res: dict[str, set],
        mutated_types: list[str] | None = None
    ) -> list[tuple[str, str]]:
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        req_types = (
            sorted(self.req_types)
            if mutated_types is None
            else mutated_types
        )
        tasks = [
            self._generator_mutate_one(msg_type=msg_type, doc_info=doc_info, req_res=req_res, sem=sem)
            for msg_type in req_types
        ]
        results = await asyncio.gather(*tasks)
        return results

    def _select_generator_mutate_types(self) -> list[str]:
        """Select the request types to mutate in one generator-mutation round."""
        req_types = sorted(self.req_types)
        if not req_types:
            return []

        configured_limit = getattr(configs, 'async_sem_fuzz', len(req_types))
        limit = max(1, min(configured_limit, len(req_types)))
        cursor = getattr(self, '_generator_mutate_cursor', 0) % len(req_types)
        selected = [
            req_types[(cursor + offset) % len(req_types)]
            for offset in range(limit)
        ]
        self._generator_mutate_cursor = (cursor + limit) % len(req_types)
        return selected

    def generator_mutate(
        self,
        req_res,
        iteration: int | None = None,
    ) -> None:
        """Generate and save input mutator
        
        Attribute:
            req_res: the actual response for each request message, which provides the information for mutator
        """
        mutated_types = self._select_generator_mutate_types()
        checkpoint_iteration = analyzer.iter if iteration is None else iteration
        analyzer.record_generator_checkpoint(
            phase='fuzzing',
            checkpoint_type='before_generator_mutate',
            phase_iteration=checkpoint_iteration,
            operation_id=f'mutate-{checkpoint_iteration}',
            mutated_types=mutated_types,
        )
        with analyzer.lock:
            analyzer.set_progress('evolve', 'mutate', len(mutated_types))
           
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new mutator
        results = asyncio.run(
            self._generator_mutate_async(
                doc_info,
                req_res,
                mutated_types=mutated_types,
            )
        )
        
        # resolve mutator
        for msg_type, mutate_code in results:
            msg_dir = self.mutator_path / f'{msg_type}'
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            # save mutator
            cur_id = None
            if msg_type in self.mutators.keys():
                cur_id = len(self.mutators[msg_type])
            else:
                cur_id = 0
            mut_path = msg_dir / f'id{cur_id}.py'
            with open(mut_path, 'w', encoding='utf-8') as f:
                f.write(mutate_code)
                # f.write('\n\n')
                # f.write(berserker_code)
                
                # construct and save information for new generator
                old_name = self.generators[msg_type][0].name
                new_name = f'id{cur_id}'
                info: dict = {'msg_type': f'{msg_type}', 'evolved_from': old_name, 'name': new_name, 'path': str(mut_path.resolve())}
                
                # set mutator name as {msg_type}
                self.mutators.setdefault(msg_type, [])
                self.mutators[msg_type].append(Generator(**info))
                
        # save the information of new generator to file   
        with open(self.mutator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.mutator_info(), f)
        
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug("[Producer]: finish mutator generation")

    async def _parser_gen_async(
            self
    ):
        res_info = self._primary_response_field_info()
        type_rules = self._response_type_rules_info()
        while(True):
            try:
                # generate input generator and save it
                pkt_parser_code = await self.chater.llm_parser_gen(
                    pro_name=self.rfcp.pro_name,
                    res_info=res_info,
                    type_rules=type_rules,
                )
                compile(pkt_parser_code, '<string>', 'exec')
                return pkt_parser_code
            except Exception as e:
                logger.debug(f'[Parser Generation]: syntax error {e}')
                
    def parser_gen(
            self
    ) -> None:
        """Generate and save packet parser
        """
        with tqdm(desc='Parser Gen', total=1) as pbar:
            result = asyncio.run(self._parser_gen_async())
            pbar.update(1)
        init_p_path = self.parser_path / 'id0.py'
        with open(init_p_path, 'w', encoding='utf-8') as f:
            f.write(result)
            info: dict = {
                'evolved_from': 'init',
                'name': 'id0',
                'state_field': self._primary_response_field_name()
            }
            self.parsers.append(Parser(**info))
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        logger.debug("[Producer]: finish parser generation")

    async def _checker_gen_one(
            self,
            response_type: str,
            msg,
            res_info: str,
            sem: asyncio.Semaphore
    ) -> tuple[str, str]:
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True
        ).decode('utf-8')

        async with sem:
            while True:
                try:
                    checker_code = await self.chater.llm_checker_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_ir=msg_ir,
                        res_info=res_info,
                        response_type=response_type,
                        type_rule=self._response_type_rule_info(response_type),
                    )
                    compile(checker_code, '<string>', 'exec')
                    namespace = {}
                    exec(checker_code, namespace)
                    checker_func = namespace.get('packet_checker')
                    if not callable(checker_func):
                        raise TypeError(
                            'packet_checker is missing or not callable'
                        )
                    result = checker_func(b'')
                    if not isinstance(result, bool):
                        raise TypeError('packet_checker must return bool')
                    return response_type, checker_code
                except Exception as e:
                    logger.debug(
                        f'[Checker Generation][{response_type}]: '
                        f'invalid checker {e}'
                    )

    async def _checker_gen_async(
            self
    ) -> list[tuple[str, str]]:
        if not hasattr(self, 'res_ir'):
            raise RuntimeError('Response IR is unavailable for checker generation')

        messages = self.res_ir.findall('message')
        if not messages:
            raise RuntimeError('Response IR does not contain any messages')

        response_types = self._response_types_from_primary_field()
        res_info = self._primary_response_field_info()
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._checker_gen_one(
                response_type,
                self._checker_ir_for_response_type(
                    response_type,
                    messages
                ),
                res_info,
                sem
            )
            for response_type in response_types
        ]
        return await tqdm_asyncio.gather(*tasks, desc='checker')

    def checker_gen(
            self
    ) -> None:
        """Generate one initial response checker for each response type."""
        results = asyncio.run(self._checker_gen_async())
        self.checkers = {}

        for msg_type, checker_code in results:
            msg_dir = self.checker_path / quote(msg_type, safe='._-')
            msg_dir.mkdir(parents=True, exist_ok=True)
            checker_path = msg_dir / 'id0.py'
            with open(checker_path, 'w', encoding='utf-8') as f:
                f.write(checker_code)

            checker = Checker(
                msg_type=msg_type,
                evolved_from='init',
                name='id0',
                path=str(checker_path.resolve()),
                state_field=self._primary_response_field_name()
            )
            self.checkers.setdefault(msg_type, []).append(checker)

        with open(self.checker_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.checker_info(), f)

        logger.debug("[Producer]: finish checkers generation")

    async def _observer_gen_one(
        self,
        response_type: str,
        msg,
        res_info: str,
        sem: asyncio.Semaphore
    ) -> tuple[str, str]:
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        async with sem:
            while True:
                try:
                    observer_code = await self.chater.llm_observer_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_ir=msg_ir,
                        res_info=res_info,
                        response_type=response_type,
                    )
                    compile(observer_code, '<observer_gen>', 'exec')
                    namespace = {}
                    exec(observer_code, namespace)
                    observer_func = self._observer_callable(namespace)
                    if not callable(observer_func):
                        raise TypeError(
                            'packet_observer is missing or not callable'
                        )
                    for probe in (b'', b'voltron-observer-probe'):
                        digest = observer_func(probe)
                        if not self._valid_digest(digest):
                            raise TypeError(
                                'packet_observer must return lowercase SHA-256'
                            )
                        if observer_func(probe) != digest:
                            raise ValueError(
                                'packet_observer must be deterministic'
                            )
                    return response_type, observer_code
                except Exception:
                    logger.exception(
                        f'Producer: invalid observer [{response_type}]'
                    )

    async def _observer_gen_async(self) -> list[tuple[str, str]]:
        if not hasattr(self, 'res_ir'):
            raise RuntimeError('Response IR is unavailable for observer generation')
        messages = self.res_ir.findall('message')
        if not messages:
            raise RuntimeError('Response IR does not contain any messages')
        response_types = self._response_types_from_primary_field()
        res_info = self._primary_response_field_info()
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._observer_gen_one(
                response_type,
                self._checker_ir_for_response_type(response_type, messages),
                res_info,
                sem,
            )
            for response_type in response_types
        ]
        return await tqdm_asyncio.gather(*tasks, desc='observer')

    def observer_gen(self) -> None:
        """Generate one semantic response observer for each response type."""
        results = asyncio.run(self._observer_gen_async())
        self.observers = {}
        for msg_type, observer_code in results:
            msg_dir = self.observer_path / quote(msg_type, safe='._-')
            msg_dir.mkdir(parents=True, exist_ok=True)
            observer_path = msg_dir / 'id0.py'
            with observer_path.open('w', encoding='utf-8') as f:
                f.write(observer_code)
            observer = ResponseObserver(
                msg_type=msg_type,
                name='id0',
                path=str(observer_path.resolve()),
                state_field=self._primary_response_field_name(),
                evolved_from='init',
            )
            self.observers.setdefault(msg_type, []).append(observer)
        with self.observer_info_path.open('w', encoding='utf-8') as f:
            json.dump(self.observer_info(), f, indent=2)
        logger.debug("[Producer]: finish observers generation")

    def evolve_observer(
        self,
        response_type: str,
        samples: list[bytes]
    ) -> ResponseObserver | None:
        """Evolve a response observer so same-type historical samples converge."""
        versions = self.observers.get(response_type)
        if not versions:
            logger.debug(
                f'Producer: no observer metadata to evolve [{response_type}]'
            )
            return None
        current = versions[-1]
        typed_path = (
            self.observer_path
            / quote(response_type, safe='._-')
            / f'{current.name}.py'
        )
        current_path = typed_path
        if not current_path.is_file() and current.path:
            current_path = Path(current.path)
        if not current_path.is_file():
            logger.debug(
                f'Producer: observer source missing for evolution {current_path}'
            )
            return None

        messages = self.res_ir.findall('message')
        msg = self._checker_ir_for_response_type(response_type, messages)
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        with current_path.open('r', encoding='utf-8') as f:
            original_code = f.read()

        unique_samples = list(dict.fromkeys(samples))
        observer_code = asyncio.run(
            self._observer_evolve_async(
                response_type,
                msg_ir,
                original_code,
                unique_samples,
            )
        )
        if observer_code is None:
            return None

        numeric_ids = [
            int(observer.name[2:])
            for observer in versions
            if observer.name.startswith('id') and observer.name[2:].isdigit()
        ]
        name = f'id{max(numeric_ids, default=-1) + 1}'
        target_dir = self.observer_path / quote(response_type, safe='._-')
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f'{name}.py'
        with target_path.open('w', encoding='utf-8') as f:
            f.write(observer_code)

        evolved = ResponseObserver(
            msg_type=response_type,
            name=name,
            path=str(target_path.resolve()),
            state_field=current.state_field,
            evolved_from=current.name,
            sample_observations=[
                hashlib.sha256(sample).hexdigest()
                for sample in unique_samples
            ],
        )
        versions.append(evolved)
        with self.observer_info_path.open('w', encoding='utf-8') as f:
            json.dump(self.observer_info(), f, indent=2)
        logger.debug(
            f'Producer: evolved observer [{response_type}] '
            f'{current.name} -> {name}'
        )
        return evolved

    def responses_semantically_equivalent(
        self,
        response_type: str,
        old_response: bytes,
        new_response: bytes
    ) -> bool:
        """Use the response IR and LLM to gate observer evolution."""
        try:
            messages = self.res_ir.findall('message')
            msg = self._checker_ir_for_response_type(
                response_type,
                messages,
            )
            msg_ir = etree.tostring(
                msg,
                encoding='utf-8',
                pretty_print=True,
            ).decode('utf-8')
            result = asyncio.run(
                self.chater.llm_observer_semantic_compare(
                    pro_name=self.rfcp.pro_name,
                    response_type=response_type,
                    msg_ir=msg_ir,
                    old_response=old_response,
                    new_response=new_response,
                )
            )
            analysis = json.loads(result)
            confidence = analysis.get('confidence', 0.0)
            equivalent = (
                analysis.get('semantic_equivalent') is True
                and isinstance(confidence, (int, float))
                and confidence >= 0.8
            )
            logger.debug(
                'Producer: observer semantic comparison '
                f'[{response_type}] equivalent={equivalent} '
                f'confidence={confidence} '
                f'reason={analysis.get("reason", "")}'
            )
            return equivalent
        except Exception:
            logger.exception(
                f'Producer: observer semantic comparison failed '
                f'[{response_type}]'
            )
            return False

    async def _observer_evolve_async(
        self,
        response_type: str,
        msg_ir: str,
        original_code: str,
        samples: list[bytes]
    ) -> str | None:
        sample_info = json.dumps([
            {
                'raw_sha256': hashlib.sha256(sample).hexdigest(),
                'length': len(sample),
                'repr': repr(sample),
            }
            for sample in samples
        ], indent=2)
        for _ in range(3):
            try:
                code = await self.chater.llm_observer_evolve(
                    pro_name=self.rfcp.pro_name,
                    response_type=response_type,
                    msg_ir=msg_ir,
                    original_code=original_code,
                    samples=sample_info,
                )
                compile(code, '<observer_evolve>', 'exec')
                namespace = {}
                exec(code, namespace)
                observer_func = self._observer_callable(namespace)
                if not callable(observer_func):
                    raise TypeError(
                        'packet_observer is missing or not callable'
                    )
                digests = [observer_func(sample) for sample in samples]
                if not all(self._valid_digest(digest) for digest in digests):
                    raise TypeError(
                        'packet_observer must return lowercase SHA-256'
                    )
                if len(set(digests)) != 1:
                    raise ValueError(
                        'evolved observer does not unify historical samples'
                    )
                return code
            except Exception:
                logger.exception(
                    f'Producer: observer evolution failed [{response_type}]'
                )
        return None

    @staticmethod
    def _observer_callable(namespace: dict) -> Callable | None:
        return namespace.get('packet_observer') or namespace.get('packet_hasher')

    @staticmethod
    def _valid_digest(digest) -> bool:
        return (
            isinstance(digest, str)
            and len(digest) == 64
            and digest == digest.lower()
            and all(char in '0123456789abcdef' for char in digest)
        )

    def review_nonconforming_response(
        self,
        request_type: str,
        response_type: str,
        request: bytes,
        response: bytes
    ) -> dict:
        """Use relevant response sections to distinguish bugs from checker errors."""
        if self._response_sections is None:
            self._response_sections = collect_response_sections(
                self.rfcp.tree_dict
            )
        if not self._response_sections:
            return {
                'verdict': 'uncertain',
                'confidence': 0.0,
                'summary': 'No annotated response sections are available.',
                'violations': [],
                'evidence': [],
            }

        retrieved = retrieve_response_sections(
            self._response_sections,
            request_type,
            response_type,
            request,
            response,
        )
        prompt = build_compliance_prompt(
            protocol=self.rfcp.pro_name,
            request_type=request_type,
            response_type=response_type,
            request=request,
            response=response,
            retrieved=retrieved,
        )
        model_response = asyncio.run(
            self.chater.chat_llm(
                prompt=prompt,
                usage='checker_non_compliance_review',
            )
        )
        analysis = parse_compliance_result(model_response)
        analysis['retrieved_sections'] = [
            {
                'rfc': section.rfc,
                'section': section.section,
                'content_type': section.content_type,
                'bm25_score': score,
            }
            for section, score in retrieved
        ]
        return analysis

    def evolve_checker(
        self,
        response_type: str,
        response: bytes,
        analysis: dict
    ) -> Checker | None:
        """Generate and persist a checker version that accepts a false positive."""
        checker_type = response_type
        if not self.checkers.get(checker_type):
            checker_type = '__all__'
        versions = self.checkers.get(checker_type)
        if not versions:
            logger.debug(
                f'Producer: no checker metadata to evolve [{response_type}]'
            )
            return None

        current = versions[-1]
        typed_checker_path = (
            self.checker_path
            / quote(checker_type, safe='._-')
            / f'{current.name}.py'
        )
        checker_path = typed_checker_path
        if not checker_path.is_file() and current.path:
            checker_path = Path(current.path)
        if not checker_path.is_file():
            logger.debug(
                f'Producer: checker source missing for evolution {checker_path}'
            )
            return None

        with checker_path.open('r', encoding='utf-8') as f:
            original_code = f.read()

        checker_code = asyncio.run(
            self._checker_evolve_async(
                response_type=response_type,
                original_code=original_code,
                response=response,
                analysis=analysis,
            )
        )
        if checker_code is None:
            return None

        numeric_ids = [
            int(checker.name[2:])
            for checker in versions
            if checker.name.startswith('id') and checker.name[2:].isdigit()
        ]
        name = f'id{max(numeric_ids, default=-1) + 1}'
        target_dir = self.checker_path / quote(checker_type, safe='._-')
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f'{name}.py'
        with target_path.open('w', encoding='utf-8') as f:
            f.write(checker_code)

        response_digest = hashlib.sha256(response).hexdigest()
        evolved = Checker(
            msg_type=checker_type,
            evolved_from=current.name,
            name=name,
            path=str(target_path.resolve()),
            state_field=current.state_field,
            checked_res=list(dict.fromkeys(
                [*current.checked_res, response_digest]
            )),
        )
        versions.append(evolved)
        with self.checker_info_path.open('w', encoding='utf-8') as f:
            json.dump(self.checker_info(), f, indent=2)
        logger.debug(
            f'Producer: evolved checker [{checker_type}] '
            f'{current.name} -> {name}'
        )
        return evolved

    async def _checker_evolve_async(
        self,
        response_type: str,
        original_code: str,
        response: bytes,
        analysis: dict
    ) -> str | None:
        review_summary = json.dumps(analysis, ensure_ascii=False)
        for _ in range(3):
            try:
                checker_code = await self.chater.llm_checker_evolve(
                    pro_name=self.rfcp.pro_name,
                    response_type=response_type,
                    original_code=original_code,
                    response=response,
                    review_summary=review_summary,
                )
                compile(checker_code, '<checker_evolve>', 'exec')
                namespace = {}
                exec(checker_code, namespace)
                checker_func = namespace.get('packet_checker')
                if not callable(checker_func):
                    raise TypeError(
                        'packet_checker is missing or not callable'
                    )
                result = checker_func(response)
                if result is not True:
                    raise ValueError(
                        'evolved checker still rejects reviewed response'
                    )
                probe = checker_func(b'')
                if not isinstance(probe, bool):
                    raise TypeError('packet_checker must return bool')
                return checker_code
            except Exception:
                logger.exception(
                    f'Producer: checker evolution failed [{response_type}]'
                )
        return None

    def _response_types_from_primary_field(
        self
    ) -> list[str]:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            types = [
                str(item['type_name']).strip()
                for item in rules.get('types', [])
                if (
                    isinstance(item, dict)
                    and isinstance(item.get('type_name'), str)
                    and item['type_name'].strip()
                )
            ]
            if types:
                return list(dict.fromkeys(types))

        field_info = json.loads(self._primary_response_field_info())
        if not field_info:
            raise RuntimeError(
                'Response field information is empty; checker generation '
                'requires at least one state-field descriptor'
            )
        field = field_info[0]
        values = field.get('value')
        if not isinstance(values, list) or not values:
            raise RuntimeError(
                'The first response-state field must define a non-empty '
                'value list for checker generation'
            )
        return list(dict.fromkeys(str(value) for value in values))

    def _request_ir_info(
        self,
        msg_type: str
    ) -> str:
        if not hasattr(self, 'req_ir'):
            return ''

        for message in self.req_ir.findall('message'):
            if str(message.get('name', '')) == msg_type:
                return etree.tostring(
                    message,
                    encoding='utf-8',
                    pretty_print=True,
                ).decode('utf-8')

        return etree.tostring(
            self.req_ir,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')

    def _ir_evolution_allowed(
        self
    ) -> bool:
        return (
            getattr(configs, 'ir_evolution_enabled', True)
            and getattr(configs, 'spec_knowledge', True)
            and analyzer.active_phase == 'model_learning'
        )

    def _ir_evolution_round_available(
        self,
        direction: str,
        msg_type: str
    ) -> bool:
        key = f'{direction}:{msg_type}'
        max_rounds = getattr(configs, 'ir_evolution_max_rounds_per_type', 1)
        return self._ir_evolution_rounds.get(key, 0) < max_rounds

    def _record_ir_evolution_round(
        self,
        direction: str,
        msg_type: str
    ) -> None:
        key = f'{direction}:{msg_type}'
        self._ir_evolution_rounds[key] = (
            self._ir_evolution_rounds.get(key, 0) + 1
        )

    async def _maybe_evolve_request_ir(
        self,
        msg_type: str,
        feedback: str
    ) -> bool:
        if (
            not self._ir_evolution_allowed()
            or not self._ir_evolution_round_available('request', msg_type)
        ):
            return False

        current_ir = self._request_ir_info(msg_type)
        if not current_ir:
            return False

        evolved_ir = await self.chater.llm_ir_evolve(
            pro_name=self.rfcp.pro_name,
            direction='request',
            msg_type=msg_type,
            current_ir=current_ir,
            type_rule=self._request_type_rule_info(msg_type),
            section_context=self.rfcp._message_ir_context(msg_type, 'req'),
            feedback=feedback,
        )
        if not evolved_ir:
            return False

        self._replace_request_ir(msg_type, evolved_ir)
        self._record_ir_evolution(
            direction='request',
            msg_type=msg_type,
            old_ir=current_ir,
            new_ir=evolved_ir,
            feedback=feedback,
        )
        self._record_ir_evolution_round('request', msg_type)
        logger.info(f'Producer: evolved request IR [{msg_type}]')
        return True

    async def _maybe_evolve_response_ir(
        self,
        response: bytes,
        feedback: str
    ) -> bool:
        msg_type = 'response'
        if (
            not self._ir_evolution_allowed()
            or not self._ir_evolution_round_available('response', msg_type)
            or not hasattr(self, 'res_ir')
        ):
            return False

        current_ir = etree.tostring(
            self.res_ir,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        evolved_ir = await self.chater.llm_ir_evolve(
            pro_name=self.rfcp.pro_name,
            direction='response',
            msg_type=msg_type,
            current_ir=current_ir,
            type_rule=self._response_type_rules_info(),
            section_context=self.rfcp._message_ir_context(
                f'response message of {self.rfcp.pro_name} protocol',
                'res',
            ),
            feedback=(
                f'{feedback}\n'
                f'Response bytes repr: {response!r}\n'
                f'Response bytes hex: {response.hex(" ")}'
            ),
        )
        if not evolved_ir:
            return False

        self._replace_response_ir(evolved_ir)
        self._record_ir_evolution(
            direction='response',
            msg_type=msg_type,
            old_ir=current_ir,
            new_ir=evolved_ir,
            feedback=feedback,
        )
        self._record_ir_evolution_round('response', msg_type)
        logger.info('Producer: evolved response IR')
        return True

    def _parse_evolved_ir(
        self,
        evolved_ir: str
    ):
        root = etree.fromstring(evolved_ir.encode('utf-8'))
        if root.tag == 'ir':
            return root

        wrapper = etree.Element('ir')
        wrapper.append(root)
        return wrapper

    def _replace_request_ir(
        self,
        msg_type: str,
        evolved_ir: str
    ) -> None:
        evolved_root = self._parse_evolved_ir(evolved_ir)
        replacement = None
        for message in evolved_root.findall('message'):
            if str(message.get('name', '')) == msg_type:
                replacement = message
                break

        if replacement is None:
            messages = evolved_root.findall('message')
            if len(messages) == 1:
                replacement = messages[0]

        if replacement is None:
            raise ValueError(f'evolved request IR lacks message {msg_type}')

        for index, message in enumerate(self.req_ir.findall('message')):
            if str(message.get('name', '')) == msg_type:
                parent_index = self.req_ir.index(message)
                self.req_ir[parent_index] = replacement
                break
        else:
            self.req_ir.append(replacement)

        self._write_ir_file('req', self.req_ir)
        self.rfcp.req_ir = etree.ElementTree(self.req_ir)

    def _replace_response_ir(
        self,
        evolved_ir: str
    ) -> None:
        self.res_ir = self._parse_evolved_ir(evolved_ir)
        self.rfcp.res_ir = etree.ElementTree(self.res_ir)
        self._write_ir_file('res', self.res_ir)

    def _write_ir_file(
        self,
        direction: str,
        root
    ) -> None:
        path = self.rfcp.ir_path / f'{direction}_ir.xml'
        etree.ElementTree(root).write(
            path,
            encoding='UTF-8',
            xml_declaration=True,
            pretty_print=True,
            standalone='yes',
        )

    def _record_ir_evolution(
        self,
        direction: str,
        msg_type: str,
        old_ir: str,
        new_ir: str,
        feedback: str
    ) -> None:
        log_path = self.rfcp.ir_path / 'ir_evolution_log.json'
        try:
            if log_path.is_file():
                with open(log_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            else:
                records = []

            records.append({
                'phase': analyzer.active_phase,
                'direction': direction,
                'message_type': msg_type,
                'feedback': feedback,
                'old_hash': hashlib.sha256(
                    old_ir.encode('utf-8')
                ).hexdigest(),
                'new_hash': hashlib.sha256(
                    new_ir.encode('utf-8')
                ).hexdigest(),
            })
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2)
        except Exception:
            logger.exception('Producer: failed to write IR evolution log')

    def _checker_ir_for_response_type(
        self,
        response_type: str,
        messages: list
    ):
        """Select dedicated IR when available, otherwise retain generic IR."""
        for message in messages:
            if str(message.get('name', '')) == response_type:
                return message

        state_field = self._primary_response_field_name()
        normalized_state_field = self._normalize_field_name(state_field)
        for message in messages:
            for field in message.findall('field'):
                if (
                    self._normalize_field_name(field.get('name', ''))
                    != normalized_state_field
                ):
                    continue
                if str(field.get('value', '')).strip() == response_type:
                    return message

        if len(messages) == 1:
            return messages[0]
        return self.res_ir

    @staticmethod
    def _normalize_field_name(
        field_name: str
    ) -> str:
        return ''.join(char.lower() for char in field_name if char.isalnum())

    def _checker_cache_matches_response_types(
        self
    ) -> bool:
        expected_types = set(self._response_types_from_primary_field())
        if set(self.checkers) != expected_types:
            return False
        state_field = self._primary_response_field_name()
        return all(
            checkers
            and checkers[-1].state_field == state_field
            for checkers in self.checkers.values()
        )

    def _observer_cache_matches_response_types(self) -> bool:
        expected_types = set(self._response_types_from_primary_field())
        if set(self.observers) != expected_types:
            return False
        state_field = self._primary_response_field_name()
        return all(
            observers and observers[-1].state_field == state_field
            for observers in self.observers.values()
        )
        
    async def _parser_evo_one(
        self,
        message
    ):
        res_info = self._primary_response_field_info()
        type_rules = self._response_type_rules_info()
        await self._maybe_evolve_response_ir(
            message,
            (
                'parser_evo was triggered by a response that the current '
                'parser could not classify during model learning.'
            ),
        )
        old_code = ''
        old_p_name = f'{self.parsers[-1].name}.py'
        old_p_path = self.parser_path / old_p_name
        with open(old_p_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
                
        while(True):
            try:
                # generate input generator and save it
                pkt_parser_code = await self.chater.llm_parser_evolve(
                    old_code=old_code,
                    pro_name=self.rfcp.pro_name,
                    res_info=res_info,
                    type_rules=type_rules,
                    message=message,
                )
                
                # test generated code
                with analyzer.lock:
                    analyzer.finished += 1
                compile(pkt_parser_code, '<string>', 'exec')
                return pkt_parser_code
            except Exception as e:
                logger.debug(f'Producer: generate error {e}')

    def _primary_response_field_info(
        self
    ) -> str:
        """Serialize response-state field descriptors used by parser/checkers."""
        if not self.rfcp.res_json:
            raise RuntimeError(
                'Response field information is empty; parser generation '
                'requires at least one state-field descriptor'
            )
        return json.dumps(self.rfcp.res_json)

    def _primary_response_field_name(
        self
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            primary_fields = rules.get('primary_fields')
            if isinstance(primary_fields, list) and primary_fields:
                fields = [
                    str(field)
                    for field in primary_fields
                    if str(field).strip()
                ]
                if fields:
                    return '+'.join(fields)

        field_info = json.loads(self._primary_response_field_info())
        if not field_info:
            return ''
        field = field_info[0]
        return str(field.get('field_name') or field.get('name') or '')

    def _request_type_rule_info(
        self,
        request_type: str
    ) -> str:
        rules = getattr(self.rfcp, 'req_type_rules', {})
        if not isinstance(rules, dict):
            return '{}'
        for item in rules.get('types', []):
            if (
                isinstance(item, dict)
                and str(item.get('type_name', '')).strip() == request_type
            ):
                return json.dumps(item)
        return '{}'

    def _response_type_rule_info(
        self,
        response_type: str
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if not isinstance(rules, dict):
            return '{}'
        for item in rules.get('types', []):
            if (
                isinstance(item, dict)
                and str(item.get('type_name', '')).strip() == response_type
            ):
                return json.dumps(item)
        return '{}'

    def _response_type_rules_info(
        self
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            return json.dumps(rules)
        return '{}'

    def _parser_cache_matches_primary_field(
        self
    ) -> bool:
        if not self.parsers:
            return False
        return self.parsers[-1].state_field == (
            self._primary_response_field_name()
        )

    def parser_evo(
        self,
        message
    ) -> None:
        """Generate and save parser
        """
        # produce new parser
        parser_code = asyncio.run(self._parser_evo_one(message))
        
        par_dir = self.parser_path
        if not par_dir.is_dir():
            par_dir.mkdir()
        
        # save parser
        cur_id = len(self.parsers)
        par_path = par_dir / f'id{cur_id}.py'
        with open(par_path, 'w', encoding='utf-8') as f:
            f.write(parser_code)
            # construct and save information for new parser
            
            old_name = self.parsers[-1].name
            new_name = f'id{cur_id}'
            info: dict = {
                'evolved_from': old_name,
                'name': new_name,
                'state_field': self._primary_response_field_name()
            }
            self.parsers.append(Parser(**info))
                
        # save the information of new parser to file   
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        
        logger.debug("[Producer]: finish parser evolve")

    def generator_info(
        self
    ) -> dict:
        """The information of generators
        Contains a dict to map msg_type and corresponded generator
        """
        info: dict[str, list[dict]]= {}
        for msg_type in self.generators.keys():
            for g in self.generators[msg_type]:
                info.setdefault(msg_type, [])
                info[msg_type].append(asdict(g))
        return info
    
    def mutator_info(
        self
    ) -> dict:
        """The information of mutators
        Contains a dict to map msg_type and corresponded mutator
        """
        info: dict[str, list[dict]]= {}
        for msg_type, ms in self.mutators.items():
            for m in ms:
                info.setdefault(msg_type, [])
                info[msg_type].append(asdict(m))
        return info
    
    def parser_info(
        self
    ) -> list:
        """The information of parsers
        """
        info: list[dict] = []
        for p in self.parsers:
            info.append(asdict(p))
        return info

    def checker_info(
        self
    ) -> dict:
        """Map each response type to its generated checker metadata."""
        return {
            msg_type: [asdict(checker) for checker in checkers]
            for msg_type, checkers in self.checkers.items()
        }

    def observer_info(self) -> dict:
        return {
            msg_type: [asdict(observer) for observer in observers]
            for msg_type, observers in self.observers.items()
        }
    
    def generators_info_load(
        self,
        info: dict
    ):
        try:
            for msg_type in info:
                for g in info[msg_type]:
                    self.generators.setdefault(msg_type, [])
                    self.generators[msg_type].append(Generator(**g))
        except Exception as e:
            logger.debug(f'Producer: load error {e}')
    
    def mutators_info_load(
        self,
        info: dict
    ):
        try:
            for msg_type in info:
                for g in info[msg_type]:
                    self.mutators.setdefault(msg_type, [])
                    self.mutators[msg_type].append(Generator(**g))
        except Exception as e:
            logger.debug(f'Producer: load error {e}')
        
                
    def parsers_info_load(
        self,
        info: list
    ):
        for p in info:
            self.parsers.append(Parser(**p))

    def checkers_info_load(
        self,
        info: dict
    ):
        for msg_type, checkers in info.items():
            for checker in checkers:
                checker.setdefault('msg_type', msg_type)
                checker.setdefault('state_field', '')
                self.checkers.setdefault(msg_type, [])
                self.checkers[msg_type].append(Checker(**checker))

    def observers_info_load(self, info: dict) -> None:
        self.observers = {}
        for msg_type, observers in info.items():
            for observer in observers:
                observer.setdefault('msg_type', msg_type)
                observer.setdefault('state_field', '')
                observer.setdefault('evolved_from', 'init')
                observer.setdefault(
                    'sample_observations',
                    observer.pop('sample_hashes', []),
                )
                self.observers.setdefault(msg_type, []).append(
                    ResponseObserver(**observer)
                )

    def legacy_checkers_info_load(
        self,
        info: list
    ):
        """Load the former single-checker cache as a global fallback."""
        for checker in info:
            name = checker.get('name', 'id0')
            path = self.checker_path / f'{name}.py'
            legacy = Checker(
                msg_type='__all__',
                evolved_from=checker.get('evolved_from', 'init'),
                name=name,
                path=str(path.resolve()),
                state_field='',
                checked_res=checker.get('checked_res', [])
            )
            self.checkers.setdefault('__all__', []).append(legacy)
