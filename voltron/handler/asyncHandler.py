from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio

from voltron.rfcparser.asyncRFCparser import asyncRFCParser
from voltron.utils.logger import logger
from voltron.llm.asyncChat import asyncChater

class asyncHandler:
    """Prepare message handler (input generator and packet parser).

    Attributes:
        inputs: dict of {msg_type : function of generator}
        pkt_parser: function of packet parser
    """

    def __init__(
            self,
            chater: asyncChater,
            rfcp: asyncRFCParser,
            base_path: Path
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.handler_path = base_path / 'tools' / rfcp.pro_name
        self.inputs_path = self.handler_path / 'inputs'
        self.parser_path = self.handler_path / 'packet_parser'

        if (not self.handler_path.is_dir()):
            self.handler_path.mkdir()

        if not self.inputs_path.is_dir():
            self.inputs_path.mkdir()

        if not self.parser_path.is_dir():
            self.parser_path.mkdir()

        self.chater = chater
        self.rfcp = rfcp
        self.inputs_code: dict[str, str] = {}
        self.pkt_parser_code: str

        self.inputs_info = None
        self.parser_info = None

        # function instance
        # self.inputs: dict[str, Callable] = {}
        self.pkt_parser: Callable | None = None

        # types of symbols
        self.req_types: list[str] = rfcp.req_types
        self.res_types: list[str] = rfcp.res_types

        # generate handler
        self.input_gen()
        self.parser_gen()

    async def _input_gen_one(
            self,
            msg,
            sem
    ):
        async with sem:
            while(True):
                try:
                    msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
                    msg_type = msg.get('name')
                    name = 'init'
                    # generate input generator and save it
                    input_code = await self.chater.llm_input_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_type=msg_type,
                        msg_ir=msg_ir,
                        name=name
                    )
                    compile(input_code, '<string>', "exec")
                    return msg_type, input_code
                except SyntaxError as e:
                    logger.debug(f'Handler :syntax error {e}')

    async def _input_gen_async(
            self
    ):
        sem = asyncio.Semaphore(8)
        tasks = [
            self._input_gen_one(msg, sem)
            for msg in self.req_ir.findall("message") 
        ]
        results = await tqdm_asyncio.gather(*tasks, desc='generator')
        return results

    def input_gen(
            self
    ) -> None:
        """Generate and save input generator
        """
        inputs_info_path = self.inputs_path / 'input_info.json'
        if(inputs_info_path.is_file()):
            try:
                with open(inputs_info_path, 'r', encoding='utf-8') as f:
                    self.inputs_info = f.read()
                logger.debug("[Handler]: load inputs")
            except Exception as e:
                logger.debug(f'Handler: input load error {e}')
        else:
            results = asyncio.run(self._input_gen_async())
            for msg_type, input_code in results:
                msg_dir = self.inputs_path / f'{msg_type}'
                if not msg_dir.is_dir():
                    msg_dir.mkdir()
                self.inputs_code[msg_type] = input_code
                with open(msg_dir / f'initial.py', 'w', encoding='utf-8') as f:
                    f.write(input_code)
            with open(inputs_info_path, 'w', encoding='utf-8') as f:
                f.write('init')
        logger.debug("[Handler]: finish inputs generation")

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
        parser_info_path = self.parser_path / 'parser_info.json'
        if (parser_info_path.is_file()):
            with open(parser_info_path, 'r', encoding='utf-8') as f:
                self.parser_info = f.read()
        else:
            result = asyncio.run(self._parser_gen_async())
            with open(self.parser_path / 'initial.py', 'w', encoding='utf-8') as f:
                f.write(result)
        logger.debug("[Handler]: finish parser generation")

    def parser_instance(
            self
    ) -> Callable:
        if(self.pkt_parser):
            return self.pkt_parser
        else:
            name_space = {}
            exec(self.pkt_parser_code, name_space)
            self.pkt_parser = name_space['packet_parser']
            if self.pkt_parser is None:
                logger.debug('parser instance failure')
                raise Exception
            else:
                return self.pkt_parser

