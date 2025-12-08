from string import Template
import textwrap
from pathlib import Path
from ..utils.logger import logger
import re

class Prompter:

    def __init__(
            self,
            dir: Path
    ) -> None:
        
        self.rfc_query_path = dir / "rfc_query.md"
        self.gen_input_path = dir / "gen_input.md"
        self.msg_type_path = dir / "msg_type.md"

        self.gen_input_tem = ''
        self.msg_type_tem = ''
        self.rfc_query_tem = ''

        if dir.is_dir():
            with self.gen_input_path.open('r+') as f:
                self.gen_input_tem = f.read()
            with self.rfc_query_path.open('r+') as f:
                self.rfc_query_tem = f.read()
            with self.msg_type_path.open('r+') as f:
                self.msg_type_tem = f.read()
        else:
            logger.info("[prompter]: template directory error")
    
    def rfc_query(
            self, 
            pro_name:str
    ) -> str:
        raw_msg = self.rfc_query_tem
        msg = Template(raw_msg)
        return msg.substitute(pro_name = pro_name)
    
    def msg_type_query(
            self, 
            pro_name: str
    ) -> str:
        raw_msg = self.msg_type_tem
        msg = Template(raw_msg)
        return msg.substitute(pro_name = pro_name)
    
    def msg_input_gen(
            self,
            pro_name: str = '',
            msg_type: str = '',
            pending: str = ''
    ) -> str:
        msg = Template(self.gen_input_tem)
        return msg.substitute(msg_type = msg_type, pro_name = pro_name, pending=pending)