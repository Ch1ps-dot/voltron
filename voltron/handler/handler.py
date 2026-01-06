from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json
from collections.abc import Callable

from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from voltron.llm.chat import Chater

class Handler:
    """Prepare message handler (input generator and packet parser).

    Attributes:
        inputs: dict of {msg_type : function of generator}
        pkt_parser: function of packet parser
    """

    def __init__(
            self,
            chater: Chater,
            rfcp: RFCParser,
            base_path: Path
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.handler_path = base_path / 'tools' / rfcp.pro_name

        if (not self.handler_path.is_dir()):
            self.handler_path.mkdir()

        self.chater = chater
        self.rfcp = rfcp
        self.inputs_code: dict[str, str] = {}
        self.pkt_parser_code: str

        # function instance
        # self.inputs: dict[str, Callable] = {}
        self.pkt_parser: Callable | None = None

        # types of symbols
        self.input_types: list[str] = []
        self.output_types: list[str] = []

        # generate handler
        self.input_gen()
        self.parser_gen()

        # symbol prepare
        self.symbols_extract()

    def symbols_extract(
            self
    ) -> None:
        """Collect input and output symbols from message types
        """

        for msg in self.req_ir.findall("message"):
            self.input_types.append(msg.get('name'))
        for msg in self.res_ir.findall('message'):
            self.output_types.append(msg.get('name'))

    
    def input_gen(
            self
    ) -> None:
        """Generate and save input generator
        """

        # load the cached code if it exists
        inputs_path = self.handler_path / 'inputs.json'
        if(inputs_path.is_file()):
            with open(inputs_path, 'r', encoding='utf-8') as f:
                self.inputs_code = json.load(f)
            logger.debug("[Handler]: load inputs")

        else:
            with tqdm(total=len(self.req_ir.findall("message")), desc='[Input Generation]', unit='type') as pbar:
                for msg in self.req_ir.findall("message"):
                    try_times = 0

                    # retry generation until the generated code can be compiled successfully
                    while(True):
                        try:
                            msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
                            msg_type = msg.get('name')

                            # generate input generator and save it
                            input_code = self.chater.llm_input_gen(
                                pro_name=self.rfcp.pro_name,
                                msg_type=msg.get('name'),
                                msg_ir=msg_ir
                            )[9:-4]

                            compile(input_code, '<string>', "exec")
                            with open(self.handler_path / msg_type / '.py', 'w', encoding='utf-8') as f:
                                f.write(input_code)

                            # save the code in a in-memory data structure
                            self.inputs_code[msg_type] = input_code
                            break
                        except SyntaxError as e:
                            try_times += 1
                            logger.debug(f'[Input Generation]:{try_times} syntax error')
                            

                    logger.debug(input_code)
                    pbar.update(1)

            logger.debug("[Handler]: finish inputs generation")

            # save the code base as a json file
            with open(inputs_path, 'w', encoding='utf-8') as f:
                json.dump(self.inputs_code, f)

    def parser_gen(
            self
    ) -> None:
        """Generate and save packet parser
        """
        # load the cached code if it exists
        parser_path = self.handler_path / 'pkt_parser.py'
        if (parser_path.is_file()):
            with open(parser_path, 'r', encoding='utf-8') as f:
                self.pkt_parser_code = f.read()
        else:
            
            # use the info of response field as augmentaion information
            res_info = json.dumps(self.rfcp.res_doc)
            try_times = 0

            # retry generation until the generated code can be compiled successfully
            while(True):
                try:

                    # generate input generator and save it
                    pkt_parser_code = self.chater.llm_parser_gen(
                        pro_name=self.rfcp.pro_name,
                        res_info=res_info
                    )[9:-4]
                    compile(pkt_parser_code, '<string>', 'exec')
                    self.pkt_parser_code = pkt_parser_code
                    break
                except SyntaxError as e:
                    try_times += 1
                    logger.debug(f'[Parser Generation]:{try_times} syntax error')

            with open(parser_path, 'w', encoding='utf-8') as f:
                f.write(self.pkt_parser_code)
                logger.debug(self.pkt_parser_code)
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

