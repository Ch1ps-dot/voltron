from string import Template
import textwrap
from pathlib import Path
from voltron.utils.logger import logger
import re

class Prompter:
    """Construct prompt for client
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        
        # path of prompts
        self._path_rfc_query = dir / "rfc_query.md"

        self._path_gen_input = dir / "input_generation.md"
        self._path_repair_input = dir / "input_repair.md"
        self._path_gen_parser = dir / "parser_generation.md"

        self._path_req_query = dir / "request_query.md"
        self._path_res_query = dir / "response_query.md"
        self._path_doc_analyze = dir / "doc_analyze.md"

        self._path_ir_generation = dir / "ir_generation.md"
        self._path_ir_repair = dir / "ir_repair.md"

        self._path_initial_symbols = dir / "initial_symbols.md"
        self._path_possible_response = dir / "possible_response.md"
        self._path_infer_dependency = dir / "infer_dependency.md"

        # template of prompts
        self._tem_rfc_query = ''

        self._tem_gen_input = ''
        self._tem_gen_parser = ''
        self._tem_repair_input = ''

        self._tem_res_query = ''
        self._tem_req_query = ''
        self._tem_doc_analyze = ''

        self._tem_ir_generation = ''
        self._tem_ir_repair = ''

        self._tem_initial_symbols = ''
        self._tem_possible_response = ''
        self._tem_infer_dependency = ''


        if dir.is_dir():
            with self._path_gen_input.open('r+') as f:
                self._tem_gen_input = f.read()
            with self._path_gen_parser.open('r+') as f:
                self._tem_gen_parser = f.read()
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
            with self._path_initial_symbols.open('r+') as f:
                self._tem_initial_symbols = f.read()
            with self._path_possible_response.open('r+') as f:
                self._tem_possible_response = f.read()
            with self._path_infer_dependency.open('r+') as f:
                self._tem_infer_dependency = f.read()
            with self._path_repair_input.open('r+') as f:
                self._tem_input_repair = f.read()
        else:
            logger.info("[prompter]: template directory error")
    
    def msg_rfc_query(
            self, 
            pro_name:str
    ) -> str:
        raw_msg = self._tem_rfc_query
        msg = Template(raw_msg)
        return msg.substitute(pro_name = pro_name)
    
    def input_gen(
            self,
            pro_name: str,
            msg_type: str,
            msg_ir: str
    ) -> str:
        msg = Template(self._tem_gen_input)
        return msg.substitute(msg_type = msg_type, pro_name = pro_name, msg_ir=msg_ir)
    
    def input_repair(
            self,
            pro_name: str,
            msg_type: str,
            code: str
    ) -> str:
        msg = Template(self._tem_repair_input)
        return msg.substitute(msg_type = msg_type, pro_name = pro_name, code=code, )
    
    def parser_gen(
            self,
            pro_name: str,
            res_info: str
    ) -> str:
        msg = Template(self._tem_gen_parser)
        return msg.substitute(pro_name = pro_name, res_info=res_info)
        
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
            rfc_num:str,
            pro_name:str,
            rfc_doc:str
    ) -> str:
        msg = Template(self._tem_doc_analyze)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name, rfc_doc = rfc_doc)
    
    def ir_generation(
            self,
            pro_name: str,
            message_name: str,
            rfc_doc: str
    ) -> str:
        msg = Template(self._tem_ir_generation)
        return msg.substitute(pro_name = pro_name, message_name = message_name, rfc_doc = rfc_doc)

    def ir_repair(
            self,
            pro_name: str,
            message_name: str,
            ir: str
    ) -> str:
        msg = Template(self._tem_ir_repair)
        return msg.substitute(pro_name = pro_name, message_name = message_name, ir = ir)
    
    def initial_symbols(
            self,
            pro_name: str,
            msg_types: str
    ) -> str:
        msg = Template(self._tem_initial_symbols)
        return msg.substitute(pro_name = pro_name, msg_types = msg_types)
    
    def possible_response(
            self,
            pro_name: str,
            current_request: str,
            response_types: str
    ) -> str:
        msg = Template(self._tem_possible_response)
        return msg.substitute(pro_name = pro_name, current_request = current_request, response_types = response_types)
    
    def infer_dependency(
            self,
            pro_name: str,
            current_request: str,
            response_type: str,
            request_types: str,
            rfc_content: str
    ) -> str:
        msg = Template(self._tem_infer_dependency)
        return msg.substitute(
            pro_name = pro_name, 
            current_request=current_request, 
            response_type=response_type, 
            request_types=request_types,
            rfc_content=rfc_content
            )