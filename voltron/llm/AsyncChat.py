from pathlib import Path
from openai import AsyncOpenAI, OpenAIError
import time, re
from re import Match
from string import Template
import asyncio

from voltron.llm.prompt import Prompter
from voltron.utils.logger import logger
from voltron.configs import configs

class AsyncChater:
    """Chat with llm through api and manage the context.
    """
    def __init__(
            self
    ) -> None:
        self.configs = configs
        client = AsyncOpenAI(
            base_url=configs.base_url,
            api_key=configs.api_key
        )

        self.clt = client
        self.pmp = Prompter(configs.pmp_path)

    async def chat_llm(
            self, 
            prompt: str,
            usage: str
    ) -> str | None:
        """Chat to llm with the prompt

        Args:
            prompt: prompt for llm
            usage: usage of this chat

        Returns:
            response of llm
        """
        response = ''
        
        # try many time to avoid api error
        for _ in range(50):
            try:
                start = time.perf_counter()
                completion = await self.clt.chat.completions.create(
                    model=configs.model,
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
                break
            except OpenAIError as e:
                await asyncio.sleep(0.5)
                logger.debug(f'Chat: API problem {e}')
        return response

    def llm_query_rfc(
            self
    ) -> str | None:
        pass

    async def llm_doc_parse(
            self,
            rfc_num: str,
            pro_name: str,
            rfc_doc: str
    ) -> str | None:
        tmp = self.pmp._tem_doc_analyze
        pmp = tmp.substitute(rfc_num = rfc_num, pro_name = pro_name, rfc_doc = rfc_doc)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "doc_parse"
        )
        return ans
    
    async def llm_try_again(
        self,
        last_question: str,
        last_answer: str,
        current_question: str
    ) -> str | None:
        tmp = self.pmp._tem_try_again
        pmp = tmp.substitute(last_question=last_question, last_answer=last_answer, current_question=current_question)
        ans = await self.chat_llm(
            prompt=pmp,
            usage="try again"
        )
        return ans
    
    async def llm_ir_generation(
        self,
        pro_name: str,
        message_name: str,
        rfc_doc: str
    ):
        tmp = self.pmp._tem_ir_generation
        pmp = tmp.substitute(pro_name=pro_name, message_name=message_name, rfc_doc=rfc_doc)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "ir_generation"
        )
        return self.xml_extract(ans)
    
    async def llm_ir_repair(
            self,
            ir: str,
            error: str
    ):
        tmp = self.pmp._tem_ir_repair
        pmp = tmp.substitute(ir=ir, error=error)
        logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "ir_repair"
        )
        return self.code_extract(ans)

    async def llm_generator_gen(
            self,
            pro_name: str,
            msg_type: str,
            msg_ir: str,
            info: str
    ) -> str:
        """Generate python code as fuzzer generator

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_gen_generator
        pmp = tmp.substitute(pro_name=pro_name, msg_type=msg_type, msg_ir=msg_ir, info=info)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "generator_gen"
        )

        return self.code_extract(ans)
        
    async def llm_generator_evolve(
            self,
            pro_name: str,
            msg_type: str,
            code: str,
            info: str,
            trace: str,
            related_code: str
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_generator_evolve
        # logger.debug(trace)
        pmp = tmp.substitute(pro_name=pro_name, msg_type=msg_type, code=code, info=info, trace=trace, related_code=related_code)
        logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "generator_evolve"
        )

        return self.code_extract(ans)
    
    async def llm_parser_evolve(
            self,
            pro_name: str,
            res_info: str,
            old_code: str,
            message: bytes
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_parser_evolve
        # logger.debug(trace)
        pmp = tmp.substitute(pro_name=pro_name, res_info=res_info, original_code=old_code, message=message)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "generator_evolve"
        )

        return self.code_extract(ans)
    
    async def llm_mutator_evolve(
            self,
            pro_name: str,
            msg_type: str,
            code: str,
            info: str
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_mutator_evolve
        # logger.debug(trace)
        pmp = tmp.substitute(pro_name=pro_name, msg_type=msg_type, code=code, info=info)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "mutator_evolve"
        )

        return self.code_extract(ans)
    
    async def llm_mutator_havoc(
            self,
            pro_name: str,
            msg_type: str,
            code: str,
            info: str
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_mutator_havoc
        # logger.debug(trace)
        pmp = tmp.substitute(pro_name=pro_name, msg_type=msg_type, code=code, info=info)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "mutator_havoc"
        )

        return self.code_extract(ans)
        
    async def llm_parser_gen(
            self,
            pro_name: str,
            res_info: str
    ) -> str:
        """Generate python code as fuzzer parser

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated parser
        """
        tmp = self.pmp._tem_gen_parser
        pmp = tmp.substitute(pro_name=pro_name, res_info=res_info)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "parser_gen"
        )

        return self.code_extract(ans)
    
    async def llm_request_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_req_query
        pmp = tmp.substitute(rfc_num=rfc_num, pro_name=pro_name, rfc_doc=rfc_doc)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "req_query"
        )

        return pmp, self.json_extract(ans)
    
    async def llm_response_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_res_query
        pmp = tmp.substitute(rfc_num=rfc_num, pro_name=pro_name, rfc_doc=rfc_doc)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "res_query"
        )

        return pmp, self.json_extract(ans)
    
    async def llm_possible_res(
            self,
            pro_name: str,
            current_request: str,
            response_types: str
    ) -> str:
        tmp = self.pmp._tem_possible_response
        pmp = tmp.substitute(pro_name=pro_name, current_request=current_request, response_types=response_types)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "possible_res"
        )

        return self.json_extract(ans)
    
    async def llm_infer_dependency(
            self,
            pro_name: str,
            last_request: str,
            current_request: str,
            response_types: str,
            rfc_content: str
    ) -> str:
        tmp = self.pmp._tem_infer_dependency
        pmp = tmp.substitute(
            pro_name=pro_name, 
            current_request=current_request, 
            last_request=last_request, 
            response_types=response_types, 
            rfc_content=rfc_content
        )
        ans = await self.chat_llm(
            prompt=pmp,
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
