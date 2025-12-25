from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json

from ..rfcparser.rfcparser import RFCParser
from ..utils.logger import logger
from ..llm.chat import Chater


class Handler:
    def __init__(
            self,
            chater: Chater,
            rfcp: RFCParser
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.handler_path = Path.cwd() / 'handler' / rfcp.pro_name

        self.chater = chater
        self.rfcp = rfcp
        self.inputs: dict[str, str] = {}
        self.pkt_parser: str

        self.input_gen()
        self.parser_gen()
    
    def input_gen(
            self
    ) -> None:
        """Generate message input
        """

        inputs_path = self.handler_path / 'inputs.json'
        if(inputs_path.is_file()):
            with open(inputs_path, 'r', encoding='utf-8') as f:
                self.inputs = json.load(f)
            logger.info("[Handler]: load inputs")

        else:
            with tqdm(total=len(self.req_ir.findall("message")), desc='[Input Generation]', unit='type') as pbar:
                for msg in self.req_ir.findall("message"):
                    try_times = 0
                    while(True):
                        try:
                            msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
                            msg_type = msg.get('name')

                            input_code = self.chater.llm_input_gen(
                                pro_name=self.rfcp.pro_name,
                                msg_type=msg.get('name'),
                                msg_ir=msg_ir
                            )[9:-4]
                            compile(input_code, '<string>', "exec")
                            self.inputs[msg_type] = input_code
                            break
                        except SyntaxError as e:
                            try_times += 1
                            logger.debug(f'[Input Generation]:{try_times} syntax error')
                            

                    logger.debug(input_code)
                    pbar.update(1)

            logger.info("[Handler]: finish inputs generation")

            with open(inputs_path, 'w', encoding='utf-8') as f:
                json.dump(self.inputs, f)

    def parser_gen(
            self
    ) -> None:
        """Generate packet parser
        """
        parser_path = self.handler_path / 'pkt_parser.py'
        if (parser_path.is_file()):
            with open(parser_path, 'r', encoding='utf-8') as f:
                self.pkt_parser = f.read()
        else:
            
            res_info = json.dumps(self.rfcp.res)

            try_times = 0
            while(True):
                try:
                    pkt_parser = self.chater.llm_parser_gen(
                        pro_name=self.rfcp.pro_name,
                        res_info=res_info
                    )[9:-4]
                    compile(self.pkt_parser, '<string>', 'exec')
                    self.pkt_parser = pkt_parser
                    break
                except SyntaxError as e:
                    try_times += 1
                    logger.debug(f'[Parser Generation]:{try_times} syntax error')

            with open(parser_path, 'w', encoding='utf-8') as f:
                f.write(self.pkt_parser)
                logger.debug(self.pkt_parser)
                logger.debug("[Handler]: finish parser generation")

    def message_gen(
            self,
            msg_type: str
    ) -> str:
        """Execute message input generator

        Args:
            msg_type: message type
        
        Return:
            generated message
        """
        name_space = {}
        input_code = self.inputs[msg_type]
        exec(input_code, name_space)
        msg_gen = name_space[f'input_{msg_type}']
        return msg_gen()

    def message_parse(
            self,
            msg: str
    ) -> str:
        name_space = {}
        parser_code = self.pkt_parser
        exec(parser_code, name_space)
        pkt_parser = name_space['packet_parser']
        return pkt_parser(msg)

