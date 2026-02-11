from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio

from voltron.producer.generator import Generator
from voltron.producer.parser import Parser
from voltron.rfcparser.AsyncRFCparser import AsyncRFCParser
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.llm.AsyncChat import AsyncChater
from voltron.scheduler.automata import MealyMachine
from dataclasses import dataclass, asdict, field
    


class AsyncProducer:
    """Prepare message Producer (input generator and packet parser).
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

        self.equipment_path = configs.base_path / 'output' / 'equipment' 
        self.producer_path = self.equipment_path / configs.target_name
        self.generator_path = self.producer_path / 'generators'
        self.mutator_path = self.producer_path / 'mutators'
        self.parser_path = self.producer_path / 'parsers'
        self.info_path = configs.info_path
        
        self.generator_info_path = self.generator_path / 'generator_info.json'
        self.parser_info_path = self.parser_path / 'parser_info.json'
        self.mutator_info_path = self.mutator_path / 'mutator_info.json'
        
        if (not self.equipment_path.is_dir()):
            self.equipment_path.mkdir()
            
        if (not self.producer_path.is_dir()):
            self.producer_path.mkdir()

        if not self.generator_path.is_dir():
            self.generator_path.mkdir()

        if not self.parser_path.is_dir():
            self.parser_path.mkdir()
            
        if not self.mutator_path.is_dir():
            self.mutator_path.mkdir()

        self.chater = chater
        self.rfcp = rfcp
        
        # types of symbols
        self.req_types: set[str] = self.rfcp.req_types
        self.res_types: set[str] = self.rfcp.res_types
        self.req_dep: dict[str, dict[str, dict]] = self.rfcp.req_dep_map
        self.poss_response: dict[str, list[str]] = self.rfcp.poss_res
        
        self.generators: dict[str, list[Generator]] = {}
        self.parsers: list[Parser] = []
        self.mutators: dict[str, list[Generator]] = {}
            
    def run(
        self
    ):

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
            self.generator_gen()
        
        # load existed parser info or generate init parser
        if (self.parser_info_path.is_file()):
            try:
                with open(self.parser_info_path, 'r', encoding='utf-8') as f:
                    parser_info = json.load(f)
                    self.parsers_info_load(parser_info)
                logger.debug("Producer: load parser info")
            except Exception as e:
                logger.debug(f'Producer: parser load error {e}')
        else:
            self.parser_gen()
            
        if (self.mutator_info_path.is_file()):
            try:
                with open(self.mutator_info_path, 'r', encoding='utf-8') as f:
                    mutator_info = json.load(f)
                    self.mutators_info_load(mutator_info)
                logger.debug("Mutator: load mutator info")
            except Exception as e:
                logger.debug(f'Mutator: load error {e}')

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
            while(True):
                try:
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        msg_ir=msg_ir,
                        info=info
                    )
                    
                    # test generated code
                    name_space = {}
                    exec(input_code, name_space)
                    obj = name_space[f'generate_{msg_type}']
                    obj()
                    
                    return msg_type, input_code
                except Exception as e:
                    logger.debug(f'Producer :generate error {e}')

    async def _generator_gen_async(
            self
    ):
        sem = asyncio.Semaphore(configs.async_sem)
        tasks = [
            self._generator_gen_one(msg, sem)
            for msg in self.req_ir.findall("message") 
        ]
        results = await tqdm_asyncio.gather(*tasks, desc='generator')
        return results

    def generator_gen(
            self
    ) -> None:
        """Generate and save input generator
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
        old_code = ''
        old_g_name = f'id{machine.id}.py'
        old_g_path = self.generator_path / msg_type / old_g_name
        with open(old_g_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
            
        # extract state trace of request pair which has dependency
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
                        msg_type=msg_type,
                        trace= '\n'.join(trace_list),
                        info=doc_info,
                        related_code='\n'.join(code_dep)
                    )
                    
                    # test generated code
                    name_space = {}
                    exec(input_code, name_space)
                    obj = name_space[f'generate_{msg_type}']
                    obj()
                    with analyzer.lock:
                        analyzer.finished += 1
                    return msg_type, input_code
                except Exception as e:
                    logger.debug(f'Producer: generate error {e}')

    async def _generator_evo_async(
        self,
        doc_info: str,
        machine: MealyMachine
    ):
        sem = asyncio.Semaphore(configs.async_sem)
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
        """Generate and save input generator
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
        old_m = None
        if msg_type in self.mutators.keys():
            old_m = self.mutators[msg_type][-1]
        else:
            old_m = self.generators[msg_type][-1]
        old_m_path = old_m.path
        old_code = ''
        with open(old_m_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
                
        async with sem:
            while(True):
                try:
                    # generate input generator and save it
                    
                    mutate_code = await self.chater.llm_mutator_evolve(
                        code=old_code,
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        info=doc_info,
                        poss_response='\n'.join(self.poss_response[msg_type]),
                        trace='\n'.join(req_res[msg_type])
                    )
                    
                    # havoc_code = await self.chater.llm_mutator_havoc(
                    #     code=old_code,
                    #     pro_name=self.rfcp.pro_name,
                    #     msg_type=msg_type,
                    #     info=doc_info
                    # )
                    
                    # test generated code
                    name_space = {}
                    exec(mutate_code, name_space)
                    obj = name_space[f'mutate_{msg_type}']
                    obj()
                    
                    # exec(havoc_code, name_space)
                    # obj = name_space[f'havoc_{msg_type}']
                    # obj()
                    with analyzer.lock:
                        analyzer.finished += 1
                    return msg_type, mutate_code
                except Exception as e:
                    logger.debug(f'Producer :generate error {e}')

    async def _generator_mutate_async(
        self,
        doc_info: str,
        req_res
    ) -> list[tuple[str, str]]:
        sem = asyncio.Semaphore(configs.async_sem)
        tasks = [
            self._generator_mutate_one(msg_type=msg_type, doc_info=doc_info, req_res=req_res, sem=sem)
            for msg_type in self.req_types
        ]
        results = await asyncio.gather(*tasks)
        return results

    def generator_mutate(
        self,
        req_res
    ) -> None:
        """Generate and save input generator
        """
        with analyzer.lock:
            analyzer.set_progress('evolve', 'mutate', len(self.req_types))
           
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new mutator
        results = asyncio.run(self._generator_mutate_async(doc_info, req_res))
        
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
                # f.write(havoc_code)
                
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
        res_info = json.dumps(list(self.rfcp.res_doc))
        while(True):
            try:
                # generate input generator and save it
                pkt_parser_code = await self.chater.llm_parser_gen(
                    pro_name=self.rfcp.pro_name,
                    res_info=res_info
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
            info: dict = {'evolved_from': 'init', 'name': 'id0'}
            self.parsers.append(Parser(**info))
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        logger.debug("[Producer]: finish parser generation")
        
    async def _parser_evo_one(
        self,
        message
    ):
        res_info = json.dumps(list(self.rfcp.res_doc))
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
                    message=message,
                )
                
                # test generated code
                with analyzer.lock:
                    analyzer.finished += 1
                compile(pkt_parser_code, '<string>', 'exec')
                return pkt_parser_code
            except Exception as e:
                logger.debug(f'Producer: generate error {e}')

    def parser_evo(
        self,
        message
    ) -> None:
        """Generate and save input generator
        """
        
        # produce new generator
        parser_code = asyncio.run(self._parser_evo_one(message))
        
        par_dir = self.parser_path
        if not par_dir.is_dir():
            par_dir.mkdir()
        
        # save generator
        cur_id = len(self.parsers)
        par_path = par_dir / f'id{cur_id}.py'
        with open(par_path, 'w', encoding='utf-8') as f:
            f.write(parser_code)
            # construct and save information for new generator
            
            old_name = self.parsers[-1].name
            new_name = f'id{cur_id}'
            info: dict = {'evolved_from': old_name, 'name': new_name}
            self.parsers.append(Parser(**info))
                
        # save the information of new generator to file   
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        
        with analyzer.lock:
            analyzer.delete_progress_bar('parser evolve')
        logger.debug("[Producer]: finish generator generation")

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
        Contains a dict to map msg_type and corresponded generator
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
        info: list[dict] = []
        for p in self.parsers:
            info.append(asdict(p))
        return info
    
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