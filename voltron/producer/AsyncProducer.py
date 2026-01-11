from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio
from dataclasses import dataclass, asdict

from voltron.rfcparser.AsyncRFCparser import AsyncRFCParser
from voltron.utils.logger import logger
from voltron.llm.AsyncChat import AsyncChater

@dataclass
class Generator:
    """Generator of request message

    msg_type: message type
    """
    msg_type: str
    path: Path
    evolved_from: str
    cur_res: list[str] = []
    pre_res: list[str] = []
    fut_res: list[str] = []
    was_used: int = 0
    
@dataclass
class Parser:
    """Generator of request message

    msg_type: message type
    """
    path: Path
    parsed_res: list[str] = []

class AsyncProducer:
    """Prepare message Producer (input generator and packet parser).
    """

    def __init__(
            self,
            chater: AsyncChater,
            rfcp: AsyncRFCParser,
            base_path: Path
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.producer_path = base_path / 'tools' / rfcp.pro_name
        self.generator_path = self.producer_path / 'generators'
        self.parser_path = self.producer_path / 'parsers'
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
        self.generator_code: dict[str, str] = {}
        self.pkt_parser_code: str

        # function instance
        # self.inputs: dict[str, Callable] = {}
        self.pkt_parser: Callable | None = None

        # types of symbols
        self.req_types: list[str] = rfcp.req_types
        self.res_types: list[str] = rfcp.res_types
        
        self.generators: dict[str, list[Generator]] = {}
        self.parsers: list[Parser] = []

        # prepare tools
        if(self.generator_info_path.is_file()):
            try:
                with open(self.generator_info_path, 'r', encoding='utf-8') as f:
                    generator_info = json.load(f)
                    self.setup_generator()
                logger.debug("Producer: load generator")
            except Exception as e:
                logger.debug(f'Producer: generator load error {e}')
        else:
            self.generator_gen()
            
        if (self.parser_info_path.is_file()):
            try:
                with open(self.parser_info_path, 'r', encoding='utf-8') as f:
                    parser_info = json.load(f)
                    self.setup_parser()
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
                    # generate input generator and save it
                    input_code = await self.chater.llm_generator_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        msg_ir=msg_ir
                    )
                    compile(input_code, '<string>', "exec")
                    return msg_type, input_code
                except SyntaxError as e:
                    logger.debug(f'Producer :syntax error {e}')

    async def _generator_gen_async(
            self
    ):
        sem = asyncio.Semaphore(8)
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
            self.generator_code[msg_type] = input_code
            with open(msg_dir / f'initial.py', 'w', encoding='utf-8') as f:
                f.write(input_code)
            info = {'msg_type': msg_type, 'evolved_from': 'init'}
            self.generator_info[msg_type].append(info)
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info, f)
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
            except SyntaxError as e:
                logger.debug(f'[Parser Generation]: syntax error {e}')

    def parser_gen(
            self
    ) -> None:
        """Generate and save packet parser
        """
        result = asyncio.run(self._parser_gen_async())
        with open(self.parser_path / 'initial.py', 'w', encoding='utf-8') as f:
            f.write(result)
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info, f)
        logger.debug("[Producer]: finish parser generation")

    def setup_generator(
        self
    ):
        for msg_type in self.generator_info.keys():
            for g in self.generator_info[msg_type]:
                self.generators[msg_type].append(Generator(**g))
    
    def setup_parser(
        self
    ):
        for p in self.parser_info:
            self.parsers.append(Parser(**p))
