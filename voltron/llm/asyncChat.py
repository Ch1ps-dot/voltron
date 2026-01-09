from pathlib import Path
from openai import OpenAI, AsyncOpenAI
import time, re
from re import Match

from voltron.llm.prompt import Prompter
from voltron.utils.logger import logger

class asyncChater:
    """Chat with llm through api and manage the context.
    """
    def __init__(
            self,
            dir: Path,
            configs
    ) -> None:
        self.configs = configs
        client = AsyncOpenAI(
            base_url=configs['llm']['base_url'],
            api_key=configs['llm']['api_key']
        )

        self.clt = client
        self.pmp = Prompter(dir)

    async def chat_llm(
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
        completion = await self.clt.chat.completions.create(
            model=self.configs['llm']['model'],
            messages=[
                {"role": "system", "content": "You are a protocol analyzer."},
                {"role": "user", "content": prompt}
            ]
        )
        if completion == None:
            logger.debug("Chat Error")
        end = time.perf_counter()
        
        response = completion.choices[0].message.content
        logger.debug(f"[Chat]:{usage} cost_time:{end - start} resp: {response}")
        return response

    def llm_query_rfc(
            self
    ) -> str | None:
        pass

    async def llm_doc_parse(
            self,
            rfc_num: str = '',
            pro_name: str = '',
            rfc_doc: str = ''
    ) -> str | None:
        ans = await self.chat_llm(
            prompt=self.pmp.doc_analyze(
                pro_name=pro_name, 
                rfc_num=rfc_num, 
                rfc_doc=rfc_doc
            ),
            usage = "doc_parse"
        )
        return ans
    
    async def llm_ir_generation(
            self,
            pro_name: str = '',
            message_name: str = '',
            rfc_doc: str = ''
    ):
        ans = await self.chat_llm(
            prompt=self.pmp.ir_generation(
                pro_name=pro_name, 
                message_name=message_name, 
                rfc_doc=rfc_doc
            ),
            usage = "ir_generation"
        )
        return self.xml_extract(ans)
    
    async def llm_ir_repair(
            self,
            pro_name: str = '',
            message_name: str = '',
            ir: str = ''
    ):
        ans = await self.chat_llm(
            prompt=self.pmp.ir_repair(
                pro_name=pro_name, 
                message_name=message_name, 
                ir = ir
            ),
            usage = "ir_repair"
        )
        return self.code_extract(ans)

    async def llm_input_gen(
            self,
            pro_name: str,
            msg_type: str,
            msg_ir: str,
            name: str
    ) -> str:
        """Generate python code as fuzzer input

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated input
        """
        ans = await self.chat_llm(
            prompt=self.pmp.input_gen(
                pro_name=pro_name, 
                msg_type=msg_type, 
                msg_ir=msg_ir,
                name=name
            ),
            usage = "input_gen"
        )

        return self.code_extract(ans)
        
    async def llm_input_repair(
            self,
            pro_name: str = '',
            msg_type: str = '',
            code: str = '',
            info: str = ''
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated input
        """
        ans = await self.chat_llm(
            prompt=self.pmp.input_repair(
                pro_name=pro_name, 
                msg_type=msg_type, 
                code=code
            ),
            usage = "input_gen"
        )

        return self.code_extract(ans)
        
    async def llm_parser_gen(
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
        ans = await self.chat_llm(
            prompt=self.pmp.parser_gen(
                pro_name=pro_name, 
                res_info=res_info
            ),
            usage = "input_gen"
        )

        return self.code_extract(ans)
    
    async def llm_request_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> str:
        ans = await self.chat_llm(
            prompt=self.pmp.req_query(
                rfc_num=rfc_num,
                pro_name=pro_name,
                rfc_doc=rfc_doc
            ),
            usage = "req_query"
        )

        return self.json_extract(ans)
    
    async def llm_response_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> str:
        ans = await self.chat_llm(
            prompt=self.pmp.res_query(
                rfc_num=rfc_num,
                pro_name=pro_name,
                rfc_doc=rfc_doc
            ),
            usage = "res_query"
        )

        return self.json_extract(ans)
    
    async def llm_possible_res(
            self,
            pro_name: str,
            current_request: str,
            response_types: str
    ) -> str:
        ans = await self.chat_llm(
            prompt=self.pmp.possible_response(
                pro_name=pro_name,
                current_request=current_request,
                response_types=response_types
            ),
            usage = "possible_res"
        )

        return self.json_extract(ans)
    
    async def llm_infer_dependency(
            self,
            pro_name: str,
            current_request: str,
            last_response: str,
            response_types: str,
            rfc_content: str
    ) -> str:
        ans = await self.chat_llm(
            prompt=self.pmp.infer_dependency(
                pro_name=pro_name,
                current_request=current_request,
                last_response=last_response,
                response_types=response_types,
                rfc_content=rfc_content
            ),
            usage = "infer_dependency"
        )

        return self.json_extract(ans)
    
    def code_extract(
            self,
            ans
    ) -> str:
        pattern = re.compile(
            r'```(?:python)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()[9:-4]
            else:
                return ans
        return ""

    def json_extract(
            self,
            ans
    ) -> str:
        pattern = re.compile(
            r'```(?:json)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()[7:-4]
            else:
                return ans
        return ""

    def xml_extract(
            self,
            ans
    ) -> str:
        pattern = re.compile(
            r'```(?:xml)\s*\n(.*?)\n\s*```',
            re.DOTALL | re.IGNORECASE
        )

        if ans != None:
            match: Match | None = pattern.search(ans)
            if match:
                return match.group()[6:-4]
            else:
                return ans
        return ""
