from pathlib import Path
from openai import OpenAI
import time, re
from re import Match

from ..configs import ftp, llm
from .prompt import Prompter
from ..utils.logger import logger

class Chater:
    """Chat with llm through api and manage the context.
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        client = OpenAI(
            base_url=llm.base_url,
            api_key=llm.api_key
        )

        self.clt = client
        self.pmp = Prompter(dir)

    def chat_llm(
            self, 
            prompt: str = "",
            usage: str = ""
    ) -> str | None:
        """Chat to llm with the prompt

        Args:
            prompt: prompt for llm
            usage: usage of this chat

        Returns:
            response of llm
        """
        start = time.perf_counter()
        completion = self.clt.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "You are a protocol analyzer."},
                {"role": "user", "content": prompt}
            ]
        )
        if completion == None:
            logger.debug("Chat Error")
        end = time.perf_counter()
        
        response: str | None = completion.choices[0].message.content
        logger.debug(f"[Chat]:{usage} cost_time:{end - start}")
        return response

    def llm_query_rfc(
            self
    ) -> str | None:
        pass

    def llm_doc_parse(
            self,
            rfc_num: str = '',
            pro_name: str = '',
            rfc_doc: str = ''
    ) -> str | None:
        ans = self.chat_llm(
            prompt=self.pmp.doc_analyze(
                pro_name=pro_name, 
                rfc_num=rfc_num, 
                rfc_doc=rfc_doc
            ),
            usage = "doc_parse"
        )
        return ans
    
    def llm_ir_generation(
            self,
            pro_name: str = '',
            message_name: str = '',
            rfc_doc: str = ''
    ):
        ans = self.chat_llm(
            prompt=self.pmp.ir_generation(
                pro_name=pro_name, 
                message_name=message_name, 
                rfc_doc=rfc_doc
            ),
            usage = "ir_generation"
        )
        return ans
    
    def llm_ir_repair(
            self,
            pro_name: str = '',
            message_name: str = '',
            ir: str = ''
    ):
        ans = self.chat_llm(
            prompt=self.pmp.ir_repair(
                pro_name=pro_name, 
                message_name=message_name, 
                ir = ir
            ),
            usage = "ir_repair"
        )
        return ans

    def llm_input_gen(
            self,
            pro_name: str = '',
            msg_type: str = '',
            msg_ir: str = ''
    ) -> str:
        """Generate python code as fuzzer input

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated input
        """
        ans = self.chat_llm(
            prompt=self.pmp.input_gen(
                pro_name=pro_name, 
                msg_type=msg_type, 
                msg_ir=msg_ir
            ),
            usage = "input_gen"
        )

        pattern = re.compile(
            r'```(?:python|py)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid python code')
        if ans != None:
            return ans
        else:
            return ''
        
    def llm_parser_gen(
            self,
            pro_name: str,
            res_info: str
    ) -> str:
        """Generate python code as fuzzer input

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated input
        """
        ans = self.chat_llm(
            prompt=self.pmp.parser_gen(
                pro_name=pro_name, 
                res_info=res_info
            ),
            usage = "input_gen"
        )

        pattern = re.compile(
            r'```(?:python|py)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid python code')
        if ans != None:
            return ans
        else:
            return ''

    def llm_request_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> str:
        ans = self.chat_llm(
            prompt=self.pmp.req_query(
                rfc_num=rfc_num,
                pro_name=pro_name,
                rfc_doc=rfc_doc
            ),
            usage = "req_query"
        )

        pattern = re.compile(
            r'```(?:json)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid json')
        return ""
    
    def llm_response_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> str:
        ans = self.chat_llm(
            prompt=self.pmp.res_query(
                rfc_num=rfc_num,
                pro_name=pro_name,
                rfc_doc=rfc_doc
            ),
            usage = "res_query"
        )

        pattern = re.compile(
            r'```(?:json)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid python code')
        return ""
    
    def llm_possible_res(
            self,
            pro_name: str,
            current_request: str,
            response_types: str
    ) -> str:
        ans = self.chat_llm(
            prompt=self.pmp.possible_response(
                pro_name=pro_name,
                current_request=current_request,
                response_types=response_types
            ),
            usage = "possible_res"
        )

        pattern = re.compile(
            r'```(?:json)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid python code')
        return ""
    
    def llm_infer_dependency(
            self,
            pro_name: str,
            current_request: str,
            response_type: str,
            request_types: str,
            rfc_content: str
    ) -> str:
        ans = self.chat_llm(
            prompt=self.pmp.infer_dependency(
                pro_name=pro_name,
                current_request=current_request,
                response_type=response_type,
                request_types=request_types,
                rfc_content=rfc_content
            ),
            usage = "possible_res"
        )

        logger.debug(rfc_content)

        pattern = re.compile(
            r'```(?:json)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()
            else:
                logger.debug(f'[Chat]: didn\'t match valid python code')
        return ""