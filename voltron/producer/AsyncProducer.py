from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio
import random

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
        self.mutator_path = self.producer_path / 'mutator'
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
        self.req_types: list[str] = self.rfcp.req_types
        self.res_types: list[str] = self.rfcp.res_types
        self.req_dep = self.rfcp.req_dep_map
        
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
        trace_list = []
        for pair in self.req_dep.keys():
            last_request = pair.split('/')[0]
            current_request = pair.split('/')[1]
            if msg_type == last_request and self.req_dep[pair]['request_dependency'] == 'dependent':
                trace_list.append(machine.get_relation(last_request, current_request))
                
        async with sem:
            while(True):
                try:
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_evolve(
                        code=old_code,
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        trace= '\n'.join(trace_list),
                        info=doc_info
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
            for msg_type, gs in self.generators.items()
        ]
        results = await asyncio.gather(*tasks)
        return results

    def generator_evo(
            self,
            machine: MealyMachine,
            id: str
    ) -> None:
        """Generate and save input generator
        """
        with analyzer.lock:
            analyzer.set_progress('evolve', 'evolve', len(self.req_types))
            analyzer.stage = 'fuzzer evolve'
            
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
            gen_path = msg_dir / f'id{int(machine.id) + 1}.py'
            with open(gen_path, 'w', encoding='utf-8') as f:
                f.write(input_code)
                
                # construct and save information for new generator
                old_name = f'id{machine.id}'
                new_name = f'id{id}'
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
            doc_info:str,
            machine: MealyMachine,
            sem
    ):
        old_code = ''
        old_g_name = f'id{machine.id}.py'
        old_g_path = self.generator_path / msg_type / old_g_name
        with open(old_g_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
                
        async with sem:
            while(True):
                try:
                    # generate input generator and save it
                    input_code = ''
                    if (random.random() > 0.5):
                        input_code = await self.chater.llm_mutator_evolve(
                            code=old_code,
                            pro_name=self.rfcp.pro_name,
                            msg_type=msg_type,
                            info=doc_info
                        )
                    else:
                        input_code = await self.chater.llm_mutator_havoc(
                            code=old_code,
                            pro_name=self.rfcp.pro_name,
                            msg_type=msg_type,
                            info=doc_info
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
                    logger.debug(f'Producer :generate error {e}')

    async def _generator_mutate_async(
        self,
        doc_info: str,
        machine: MealyMachine
    ):
        sem = asyncio.Semaphore(configs.async_sem)
        tasks = [
            self._generator_mutate_one(msg_type=msg_type, doc_info=doc_info, machine=machine, sem=sem)
            for msg_type, gs in self.generators.items()
        ]
        results = await asyncio.gather(*tasks)
        return results

    def generator_mutate(
            self,
            machine: MealyMachine,
            id: str
    ) -> None:
        """Generate and save input generator
        """
        with analyzer.lock:
            analyzer.set_progress('evolve', 'mutate', len(self.req_types))
           
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new mutator
        results = asyncio.run(self._generator_mutate_async(doc_info, machine))
        
        # resolve mutator
        for msg_type, input_code in results:
            msg_dir = self.mutator_path / f'{msg_type}'
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            # save mutator
            mut_path = msg_dir / f'id{len(self.mutators[msg_type])}.py'
            with open(mut_path, 'w', encoding='utf-8') as f:
                f.write(input_code)
                
                # construct and save information for new generator
                old_name = f'id{machine.id}'
                new_name = f'id{id}'
                info: dict = {'msg_type': msg_type, 'evolved_from': old_name, 'name': new_name, 'path': str(mut_path.resolve())}
                
                # set mutator name as {msg_type}[m]
                self.mutators.setdefault(f'{msg_type}[m]', [])
                self.mutators[f'{msg_type}[m]'].append(Generator(**info))
                
        # save the information of new generator to file   
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)
        
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug("[Producer]: finish generator generation")

    async def _parser_gen_async(
            self
    ):
        res_info = json.dumps(self.rfcp.res_doc)
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
        
                
    def parsers_info_load(
        self,
        info: list
    ):
        for p in info:
            self.parsers.append(Parser(**p))