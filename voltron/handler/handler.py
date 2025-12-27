from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json
from collections.abc import Callable

from ..rfcparser.rfcparser import RFCParser
from ..utils.logger import logger
from ..llm.chat import Chater


class Handler:
    """Prepare message handler (input generator and packet parser).

    Attributes:
        inputs: dict of {msg_type : code of generator}
        pkt_parser: code of packet parser
    """

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
        self.inputs_code: dict[str, str] = {}
        self.pkt_parser_code: str

        self.inputs: dict[str, Callable] = {}
        self.pkt_parser: Callable | None = None

        # generate handler
        self.input_gen()
        self.parser_gen()
    
    def input_gen(
            self
    ) -> None:
        """Generate and save input generator
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
                            self.inputs_code[msg_type] = input_code
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
        """Generate and save packet parser
        """
        parser_path = self.handler_path / 'pkt_parser.py'
        if (parser_path.is_file()):
            with open(parser_path, 'r', encoding='utf-8') as f:
                self.pkt_parser_code = f.read()
        else:
            
            res_info = json.dumps(self.rfcp.res)

            try_times = 0
            while(True):
                try:
                    pkt_parser_code = self.chater.llm_parser_gen(
                        pro_name=self.rfcp.pro_name,
                        res_info=res_info
                    )[9:-4]
                    compile(self.pkt_parser_code, '<string>', 'exec')
                    self.pkt_parser_code = pkt_parser_code
                    break
                except SyntaxError as e:
                    try_times += 1
                    logger.debug(f'[Parser Generation]:{try_times} syntax error')

            with open(parser_path, 'w', encoding='utf-8') as f:
                f.write(self.pkt_parser_code)
                logger.debug(self.pkt_parser_code)
                logger.debug("[Handler]: finish parser generation")

    def input_instance(
            self,
            msg_type: str
    ) -> Callable:
        """Execute message input generator

        Args:
            msg_type: name of message type
        
        Return:
            generated message
        """
        if(msg_type not in self.inputs):
            name_space = {}
            code = self.inputs_code[msg_type]
            exec(code, name_space)
            self.inputs[msg_type] = name_space[f'input_{msg_type}']
        return self.inputs[msg_type]

    def parser_instance(
            self
    ) -> Callable | None:
        if(self.pkt_parser == None):
            name_space = {}
            exec(self.pkt_parser_code, name_space)
            self.pkt_parser = name_space['packet_parser']
        return self.pkt_parser

