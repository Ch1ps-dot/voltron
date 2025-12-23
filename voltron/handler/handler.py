from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm

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

        self.chater = chater
        self.rfcp = rfcp

        self.input_gen()

        logger.debug("[Handler]: finish input generation")
    
    def input_gen(
            self
    ) -> None:
        with tqdm(total=len(self.req_ir.findall("message")), desc='[Input Generation]', unit='type') as pbar:
            for msg in self.req_ir.findall("message"):
                msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
                msg_code = self.chater.llm_input_gen(
                    pro_name=self.rfcp.pro_name,
                    msg_type=msg.get('name'),
                    msg_ir=msg_ir
                )
                logger.debug(msg_code)
                pbar.update(1)

    def parser_gen(
            self
    ) -> None:
        res = self.rfcp.res

