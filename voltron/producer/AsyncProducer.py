from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio
from dataclasses import dataclass, asdict, field

from voltron.rfcparser.AsyncRFCparser import AsyncRFCParser
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.llm.AsyncChat import AsyncChater

@dataclass
class Generator:
    """Generator of request message

    msg_type: message type
    """
    msg_type: str
    name: str
    evolved_from: str
    cur_res: list[str] = field(default_factory=list)
    pre_res: list[str] = field(default_factory=list)
    fut_res: list[str] = field(default_factory=list)
    was_used: int = 0
    
    # def __post_init__(self):
    #     if self.cur_res is None:
    #         self.cur_res = []
    #     if self.pre_res is None:
    #         self.pre_res = []
    #     if self.fut_res is None:
    #         self.fut_res = []
    
@dataclass
class Parser:
    """Generator of request message

    msg_type: message type
    """
    evolved_from: str
    name: str
    parsed_res: list[str] = field(default_factory=list)
    
    # def __post_init__(self):
    #     if self.cur_res is None:
    #         self.cur_res = []

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

        self.producer_path = configs.base_path / 'output' / 'equipment' / rfcp.pro_name
        self.generator_path = self.producer_path / 'generators'
        self.parser_path = self.producer_path / 'parsers'
        self.info_path = configs.info_path
        
        self.generator_info_path = self.generator_path / 'generator_info.json'
        self.parser_info_path = self.parser_path / 'parser_info.json'

        if (not self.producer_path.is_dir()):
            self.producer_path.mkdir()

        if not self.generator_path.is_dir():
            self.generator_path.mkdir()

        if not self.parser_path.is_dir():
            self.parser_path.mkdir()

        self.chater = chater
        self.rfcp = rfcp
        
        # types of symbols
        self.req_types: list[str] = self.rfcp.req_types
        self.res_types: list[str] = self.rfcp.res_types
        
        self.generators: dict[str, list[Generator]] = {}
        self.parsers: list[Parser] = []
            
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
        async with sem:
            while(True):
                try:
                    msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
                    msg_type = msg.get('name')
                    info = ''
                    with open(self.info_path, 'r', encoding='utf-8') as f:
                        info = f.read()
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        msg_ir=msg_ir,
                        info=info
                    )
                    compile(input_code, '<string>', "exec")
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
                info: dict = {'msg_type': msg_type, 'evolved_from': 'init', 'name': 'id0'}
                self.generators.setdefault(msg_type, [])
                self.generators[msg_type].append(Generator(**info))
            
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)
            
        logger.debug("[Producer]: finish generator generation")
        
    async def _generator_evo_one(
            self,
            msg_type: str,
            gs: list[Generator],
            trace: str,
            sem
    ):
        async with sem:
            while(True):
                try:
                    info = ''
                    code = ''
                    g_path = self.generator_path / msg_type / f'{gs[-1].name}.py'
                    with open(self.info_path, 'r', encoding='utf-8') as f:
                        info = f.read()
                    with open(g_path, 'r', encoding='utf-8') as f:
                        code = f.read()
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_evolve(
                        code=code,
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        trace=trace,
                        info=info
                    )
                    compile(input_code, '<string>', "exec")
                    with analyzer.lock:
                        analyzer.finished += 1
                    return msg_type, input_code
                except Exception as e:
                    logger.debug(f'Producer :generate error {e}')

    async def _generator_evo_async(
            self,
            trace: str
    ):
        sem = asyncio.Semaphore(configs.async_sem)
        tasks = [
            self._generator_evo_one(msg_type, gs, trace, sem)
            for msg_type, gs in self.generators.items()
        ]
        results = await asyncio.gather(*tasks)
        return results

    def generator_evo(
            self,
            trace: str
    ) -> None:
        """Generate and save input generator
        """
        with analyzer.lock:
            analyzer.set_progress('evolve', len(self.req_types))
            analyzer.stage = 'fuzzer evolve'
        results = asyncio.run(self._generator_evo_async(trace))
        for msg_type, input_code in results:
            msg_dir = self.generator_path / f'{msg_type}'
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            init_gen_path = msg_dir / f'id{len(self.generators[msg_type])}.py'
            with open(init_gen_path, 'w', encoding='utf-8') as f:
                f.write(input_code)
                
                # construct and save information for new generator
                info: dict = {'msg_type': msg_type, 'evolved_from': f'id{len(self.generators[msg_type])-1}', 'name': f'id{len(self.generators[msg_type])}'}
                self.generators.setdefault(msg_type, [])
                self.generators[msg_type].append(Generator(**info))
            
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
        with tqdm(desc='Parser Gen') as pbar:
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