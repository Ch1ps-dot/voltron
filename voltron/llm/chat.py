from pathlib import Path
from openai import OpenAI
import time, re
from re import Match

from ..configs import settings
from .prompt import Prompter
from ..utils.logger import logger

class Chater:
    """Chat with llm through api and manage the context.

    Attributes:
        dir: prompt directory path
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        """Initialize the chater with prompt directory path
        Args: 
            dir: prompt directory path

        """

        client = OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key
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
            model=settings.model,
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