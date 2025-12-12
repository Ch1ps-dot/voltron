from string import Template
import textwrap
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

class Prompter:
    """Construct prompt for client
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        
        self._path_rfc_query = dir / "rfc_query.md"
        self._path_gen_input = dir / "gen_input.md"
        self._path_msg_type = dir / "msg_type.md"
        self._path_rfc_summary = dir / "rfc_summary.md"
        self._path_req_query = dir / "request_query.md"
        self._path_res_query = dir / "response_query.md"

        self._tem_rfc_query = ''
        self._tem_gen_input = ''
        self._tem_msg_type = ''
        self._tem_rfc_summary = ''
        self._tem_res_query = ''
        self._tem_req_query = ''


        if dir.is_dir():
            with self._path_gen_input.open('r+') as f:
                self._tem_gen_input = f.read()
            with self._path_rfc_query.open('r+') as f:
                self._tem_rfc_query = f.read()
            with self._path_msg_type.open('r+') as f:
                self._tem_msg_type = f.read()
            with self._path_rfc_summary.open('r+') as f:
                self._tem_rfc_summary = f.read()
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = f.read()
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = f.read()
        else:
            logger.info("[prompter]: template directory error")

        self.gen_input = self.msg_input_gen
    
    def msg_rfc_query(
            self, 
            pro_name:str
    ) -> str:
        raw_msg = self._tem_rfc_query
        msg = Template(raw_msg)
        return msg.substitute(pro_name = pro_name)
    
    def msg_rfc_summary(
            self,
            rfc_toc: str = '',
            rfc_doc: str = '',
            rfc_num: str = '', 
            pro_name: str = ''
    ) -> str:
        raw_msg = self._tem_rfc_summary
        msg = Template(raw_msg)
        return msg.substitute(rfc_toc = rfc_toc, rfc_doc = rfc_doc, rfc_num = rfc_num, pro_name = pro_name)
    
    def msg_type_query(
            self,
            rfc_doc: str = '',
            rfc_num: str = '', 
            pro_name: str = ''
    ) -> str:
        raw_msg = self._tem_msg_type
        msg = Template(raw_msg)
        return msg.substitute(rfc_doc = rfc_doc, rfc_num = rfc_num, pro_name = pro_name)
    
    def msg_input_gen(
            self,
            pro_name: str = '',
            msg_type: str = '',
            pending: str = ''
    ) -> str:
        msg = Template(self._tem_gen_input)

        if pending == '':
            return msg.substitute(msg_type = msg_type, pro_name = pro_name, pending=f'{pro_name}_{msg_type}')
        else:
            return msg.substitute(msg_type = msg_type, pro_name = pro_name, pending=pending)
        
    def msg_req_query(
            self,
            rfc_num:str = '',
            pro_name:str = ''
    ) -> str:
        msg = Template(self._tem_req_query)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name)
    
    def msg_res_query(
            self,
            rfc_num:str = '',
            pro_name:str = ''
    ) -> str:
        msg = Template(self._tem_res_query)
        return msg.substitute(rfc_num = rfc_num, pro_name = pro_name)

