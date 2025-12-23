from string import Template
import textwrap
from pathlib import Path
from ..utils.logger import logger
import re

class Prompter:
    """Construct prompt for client
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        
        self._path_rfc_query = dir / "rfc_query.md"
        self._path_gen_input = dir / "input_generation.md"
        self._path_req_query = dir / "request_query.md"
        self._path_res_query = dir / "response_query.md"
        self._path_doc_analyze = dir / "doc_analyze.md"
        self._path_ir_generation = dir / "ir_generation.md"
        self._path_ir_repair = dir / "ir_repair.md"

        self._tem_rfc_query = ''
        self._tem_gen_input = ''
        self._tem_res_query = ''
        self._tem_req_query = ''
        self._tem_doc_analyze = ''
        self._tem_ir_generation = ''
        self._tem_ir_repair = ''


        if dir.is_dir():
            with self._path_gen_input.open('r+') as f:
                self._tem_gen_input = f.read()
            # with self._path_rfc_query.open('r+') as f:
            #     self._tem_rfc_query = f.read()
            # with self._path_msg_type.open('r+') as f:
            #     self._tem_msg_type = f.read()
            # with self._path_rfc_summary.open('r+') as f:
            #     self._tem_rfc_summary = f.read()
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = f.read()
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = f.read()
            with self._path_doc_analyze.open('r+') as f:
                self._tem_doc_analyze = f.read()
            with self._path_ir_generation.open('r+') as f:
                self._tem_ir_generation = f.read()
            with self._path_ir_repair.open('r+') as f:
                self._tem_ir_repair = f.read()
        else:
            logger.info("[prompter]: template directory error")
    
    def msg_rfc_query(
            self, 
            pro_name:str
    ) -> str:
        raw_msg = self._tem_rfc_query
        msg = Template(raw_msg)
        return msg.substitute(pro_name = pro_name)
    
    # def msg_rfc_summary(
    #         self,
    #         rfc_toc: str = '',
    #         rfc_doc: str = '',
    #         rfc_num: str = '', 
    #         pro_name: str = ''
    # ) -> str:
    #     raw_msg = self._tem_rfc_summary
    #     msg = Template(raw_msg)
    #     return msg.substitute(rfc_toc = rfc_toc, rfc_doc = rfc_doc, rfc_num = rfc_num, pro_name = pro_name)
    
    # def msg_type_query(
    #         self,
    #         rfc_doc: str = '',
    #         rfc_num: str = '', 
    #         pro_name: str = ''
    # ) -> str:
    #     raw_msg = self._tem_msg_type
    #     msg = Template(raw_msg)
    #     return msg.substitute(rfc_doc = rfc_doc, rfc_num = rfc_num, pro_name = pro_name)
    
    def input_gen(
            self,
            pro_name: str = '',
            msg_type: str = '',
            msg_ir: str = ''
    ) -> str:
        msg = Template(self._tem_gen_input)
        return msg.substitute(msg_type = msg_type, pro_name = pro_name, msg_ir=msg_ir)
        
    def req_query(
            self,
            rfc_num:str,
            pro_name:str,
            rfc_doc:str
    ) -> str:
        msg = Template(self._tem_req_query)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name, rfc_doc = rfc_doc)
    
    def res_query(
            self,
            rfc_num:str,
            pro_name:str,
            rfc_doc:str
    ) -> str:
        msg = Template(self._tem_res_query)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name, rfc_doc = rfc_doc)
    
    def doc_analyze(
            self,
            rfc_num:str = '',
            pro_name:str = '',
            rfc_doc:str = ''
    ) -> str:
        msg = Template(self._tem_doc_analyze)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name, rfc_doc = rfc_doc)
    
    def ir_generation(
            self,
            pro_name: str = '',
            message_name: str = '',
            rfc_doc: str = ''
    ) -> str:
        msg = Template(self._tem_ir_generation)
        return msg.substitute(pro_name = pro_name, message_name = message_name, rfc_doc = rfc_doc)

    def ir_repair(
            self,
            pro_name: str = '',
            message_name: str = '',
            ir: str = ''
    ) -> str:
        msg = Template(self._tem_ir_repair)
        return msg.substitute(pro_name = pro_name, message_name = message_name, ir = ir)