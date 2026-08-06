from pathlib import Path
from openai import AsyncOpenAI, OpenAIError
import time, re
from re import Match
from string import Template
import asyncio

from voltron.llm.prompt import Prompter
from voltron.utils.logger import format_event, logger_llm as logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer


class LLMDeadlineExceeded(RuntimeError):
    """Raised when an LLM request would outlive the fuzzing deadline."""


class AsyncChater:
    """Chat with llm through api and manage the context.
    """
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str
    ) -> None:
        self.configs = configs
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model = model

        self.clt = client
        self.pmp = Prompter(configs.pmp_path)

    @staticmethod
    def _remaining_fuzz_time_s() -> float | None:
        """Return the remaining fuzzing budget, if a fuzzing run is active."""
        time_limit_s = getattr(configs, 'time_limit_s', None)
        start_time = getattr(analyzer, 'start_time', None)
        if not isinstance(time_limit_s, (int, float)):
            return None
        if not isinstance(start_time, (int, float)):
            return None
        return time_limit_s - (time.time() - start_time)

    @staticmethod
    def _stop_for_deadline() -> None:
        request_stop = getattr(analyzer, 'request_stop', None)
        if callable(request_stop):
            request_stop('deadline')
        else:
            stop_event = getattr(analyzer, 'stop_event', None)
            if stop_event is not None:
                stop_event.set()
        logger.debug('LLM: fuzzing deadline reached; cancelling request')

    @staticmethod
    def _compact_context(value: object, limit: int | None = None) -> str:
        """Keep both ends of variable prompt context within a fixed budget.

        Prompt templates contain the instructions and are never truncated.
        Keeping the beginning and end of RFC/IR/code context preserves its
        identifier/definition and trailing constraints while preventing one
        large context from dominating a component-generation request.
        """
        text = '' if value is None else str(value)
        max_chars = (
            getattr(configs, 'prompt_context_max_chars', 12_000)
            if limit is None
            else limit
        )
        max_chars = max(512, int(max_chars))
        if len(text) <= max_chars:
            return text

        marker = '\n\n[... Voltron context truncated ...]\n\n'
        retained = max_chars - len(marker)
        head_chars = max(1, retained * 2 // 3)
        tail_chars = max(1, retained - head_chars)
        return f'{text[:head_chars]}{marker}{text[-tail_chars:]}'

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
                remaining_s = self._remaining_fuzz_time_s()
                if remaining_s is not None and remaining_s <= 0:
                    self._stop_for_deadline()
                    raise LLMDeadlineExceeded(
                        'fuzzing deadline reached before LLM request'
                    )

                request = self.clt.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a protocol analyzer."},
                        {"role": "user", "content": prompt}
                    ]
                )
                if remaining_s is None:
                    completion = await request
                else:
                    completion = await asyncio.wait_for(
                        request,
                        timeout=remaining_s,
                    )
                if completion == None:
                    logger.debug("Chat Error")
                end = time.perf_counter()
                
                response = completion.choices[0].message.content

                logger.debug(
                    '%s\nPROMPT\n%s\nRESPONSE\n%s',
                    format_event(
                        'llm.complete',
                        usage=usage,
                        model=self.model,
                        duration_s=round(end - start, 3),
                        tokens=(
                            completion.usage.total_tokens
                            if completion.usage is not None
                            else None
                        ),
                    ),
                    prompt,
                    response,
                )
                with analyzer.lock:
                    analyzer.chat_time_s += end - start
                    if completion.usage != None:
                        analyzer.chat_token += completion.usage.total_tokens
                    analyzer.record_llm_usage(
                        duration_s=end - start,
                        prompt_tokens=(
                            getattr(completion.usage, 'prompt_tokens', 0)
                            if completion.usage is not None
                            else 0
                        ),
                        completion_tokens=(
                            getattr(
                                completion.usage,
                                'completion_tokens',
                                0
                            )
                            if completion.usage is not None
                            else 0
                        ),
                        total_tokens=(
                            getattr(completion.usage, 'total_tokens', 0)
                            if completion.usage is not None
                            else 0
                        ),
                    )
                break
            except asyncio.TimeoutError as exc:
                self._stop_for_deadline()
                raise LLMDeadlineExceeded(
                    'LLM request exceeded remaining fuzzing time'
                ) from exc
            except OpenAIError as e:
                remaining_s = self._remaining_fuzz_time_s()
                if remaining_s is not None and remaining_s <= 0:
                    self._stop_for_deadline()
                    raise LLMDeadlineExceeded(
                        'fuzzing deadline reached while retrying LLM request'
                    )
                await asyncio.sleep(
                    0.5 if remaining_s is None else min(0.5, remaining_s)
                )
                logger.debug(
                    format_event(
                        'llm.api_error',
                        usage=usage,
                        error_type=type(e).__name__,
                        error=str(e),
                    )
                )
        return response

    def llm_query_rfc(
            self
    ) -> str | None:
        pass

    async def llm_doc_parse(
            self,
            rfc_num: str,
            pro_name: str,
            rfc_doc: str,
            error_msg: str = ""
    ) -> str | None:
        tmp = self.pmp._tem_doc_analyze
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            rfc_doc=self._compact_context(rfc_doc),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "doc_parse"
        )
        return ans
    
    async def llm_ir_generation(
        self,
        pro_name: str,
        message_name: str,
        rfc_doc: str
    ):
        tmp = self.pmp._tem_ir_generation
        pmp = tmp.substitute(
            pro_name=pro_name,
            message_name=message_name,
            rfc_doc=self._compact_context(rfc_doc),
        )
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
        pmp = tmp.substitute(
            ir=self._compact_context(ir),
            error=self._compact_context(error),
        )
        # logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "ir_repair"
        )
        # IR repair responses are XML, not Python source.  Keeping an XML
        # markdown fence here causes the RFC parser to retry the same invalid
        # payload forever because ``etree.fromstring`` receives the fence.
        return self.xml_extract(ans)

    async def llm_ir_evolve(
            self,
            pro_name: str,
            direction: str,
            msg_type: str,
            current_ir: str,
            type_rule: str,
            section_context: str,
            feedback: str
    ) -> str:
        tmp = self.pmp._tem_ir_evolve
        pmp = tmp.substitute(
            pro_name=pro_name,
            direction=direction,
            msg_type=msg_type,
            current_ir=self._compact_context(current_ir),
            type_rule=self._compact_context(type_rule),
            section_context=self._compact_context(section_context),
            feedback=self._compact_context(feedback),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="ir_evolve"
        )
        return self.xml_extract(ans)

    async def llm_generator_gen(
            self,
            pro_name: str,
            field_name: str,
            msg_type: str,
            msg_ir: str,
            info: str,
            type_rule: str = "{}"
    ) -> str:
        """Generate python code as fuzzer generator

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_gen_generator
        pmp = tmp.substitute(
            pro_name=pro_name,
            field_name=field_name,
            msg_type=msg_type,
            msg_ir=self._compact_context(msg_ir),
            info=self._compact_context(info),
            type_rule=self._compact_context(type_rule),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "generator_gen"
        )

        return self.code_extract(ans)

    async def llm_code_repair(
            self,
            code: str,
            error: str,
            function_name: str,
    ) -> str:
        """Repair generated Python code using its local validation error."""
        tmp = self.pmp._tem_code_repair
        pmp = tmp.substitute(
            code=self._compact_context(code),
            error=self._compact_context(error),
            function_name=function_name,
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage='code_repair',
        )
        return self.code_extract(ans)
        
    async def llm_generator_evolve(
            self,
            pro_name: str,
            field_name: str,
            msg_type: str,
            code: str,
            msg_ir: str,
            info: str,
            trace: str,
            related_code: str
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type
            code: the original generator code to be evolved
            info: the information to be used for generator evolution
            trace: the execution trace of the current generator, which provides the information for generator evolution
            related_code: the related generator code which provides the information for generator evolution

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_generator_evolve

        pmp = tmp.substitute(
            pro_name=pro_name,
            field_name=field_name,
            msg_type=msg_type,
            code=self._compact_context(code),
            msg_ir=self._compact_context(msg_ir),
            info=self._compact_context(info),
            trace=self._compact_context(trace),
            related_code=self._compact_context(related_code),
        )
        # logger.debug(pmp)
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
            message: bytes,
            type_rules: str = "{}"
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated generator
        """
        tmp = self.pmp._tem_parser_evolve
        if len(message) > 100:
            message = message[:99]
        pmp = tmp.substitute(
            pro_name=pro_name,
            res_info=self._compact_context(res_info),
            type_rules=self._compact_context(type_rules),
            original_code=self._compact_context(old_code),
            message=message,
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "parser_evolve"
        )

        return self.code_extract(ans)
    
    async def llm_mutator_evolve(
            self,
            pro_name: str,
            field_name: str,
            msg_type: str,
            code: str,
            msg_ir: str,
            info: str,
            poss_response: str,
            trace: str
    ) -> str:
        """Repair teh python code

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type
            code: saved best generator code used as the mutation baseline
            info: the information to be used for mutator evolution
            poss_response: the possible response for the current request message, which provides the information for mutator evolution
            trace: JSON list of response types observed for the current
                request type during fuzzing

        Returns:
            generated mutator
        """
        tmp = self.pmp._tem_mutator_evolve
        
        pmp = tmp.substitute(
            pro_name=pro_name,
            field_name=field_name,
            msg_type=msg_type,
            code=self._compact_context(code),
            msg_ir=self._compact_context(msg_ir),
            info=self._compact_context(info),
            poss_response=self._compact_context(poss_response),
            trace=self._compact_context(trace),
        )
        # logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "mutator_evolve"
        )

        return self.code_extract(ans)
        
    async def llm_parser_gen(
            self,
            pro_name: str,
            res_info: str,
            type_rules: str = "{}"
    ) -> str:
        """Generate python code as fuzzer parser

        Args:
            pro_name: name of protocol
            msg_type: required protocol message type

        Returns:
            generated parser
        """
        tmp = self.pmp._tem_gen_parser
        pmp = tmp.substitute(
            pro_name=pro_name,
            res_info=self._compact_context(res_info),
            type_rules=self._compact_context(type_rules),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "parser_gen"
        )

        return self.code_extract(ans)

    async def llm_checker_gen(
            self,
            pro_name: str,
            msg_ir: str,
            res_info: str,
            response_type: str,
            type_rule: str = "{}"
    ) -> str:
        """Generate a response conformance checker from response-message IR."""
        tmp = self.pmp._tem_gen_checker
        pmp = tmp.substitute(
            pro_name=pro_name,
            msg_ir=self._compact_context(msg_ir),
            res_info=self._compact_context(res_info),
            response_type=response_type,
            type_rule=self._compact_context(type_rule),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="checker_gen"
        )

        return self.code_extract(ans)

    async def llm_observer_gen(
            self,
            pro_name: str,
            msg_ir: str,
            res_info: str,
            response_type: str
    ) -> str:
        """Generate a semantic response observer from response-message IR."""
        tmp = self.pmp._tem_gen_observer
        pmp = tmp.substitute(
            pro_name=pro_name,
            msg_ir=self._compact_context(msg_ir),
            res_info=self._compact_context(res_info),
            response_type=response_type,
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="observer_gen",
        )
        return self.code_extract(ans)

    async def llm_observer_evolve(
            self,
            pro_name: str,
            response_type: str,
            msg_ir: str,
            original_code: str,
            samples: str
    ) -> str:
        """Evolve a observer using same-type responses with different observations."""
        tmp = self.pmp._tem_observer_evolve
        pmp = tmp.substitute(
            pro_name=pro_name,
            response_type=response_type,
            msg_ir=self._compact_context(msg_ir),
            original_code=self._compact_context(original_code),
            samples=self._compact_context(samples),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="observer_evolve",
        )
        return self.code_extract(ans)

    async def llm_observer_semantic_compare(
            self,
            pro_name: str,
            response_type: str,
            msg_ir: str,
            old_response: bytes,
            new_response: bytes
    ) -> str:
        """Judge whether two responses have the same protocol semantics."""
        tmp = self.pmp._tem_observer_semantic_compare
        pmp = tmp.substitute(
            pro_name=pro_name,
            response_type=response_type,
            msg_ir=self._compact_context(msg_ir),
            old_response=repr(old_response),
            new_response=repr(new_response),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="observer_semantic_compare",
        )
        return self.json_extract(ans)

    async def llm_checker_evolve(
            self,
            pro_name: str,
            response_type: str,
            original_code: str,
            response: bytes,
            review_summary: str
    ) -> str:
        """Relax a checker after RFC review confirms a false positive."""
        tmp = self.pmp._tem_checker_evolve
        pmp = tmp.substitute(
            pro_name=pro_name,
            response_type=response_type,
            original_code=self._compact_context(original_code),
            response_repr=repr(response),
            response_hex=response.hex(' '),
            review_summary=self._compact_context(review_summary)
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="checker_evolve"
        )
        return self.code_extract(ans)
    
    async def llm_request_query(
            self,
            rfc_num:str,
            pro_name: str,
            rfc_doc: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_req_query
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            rfc_doc=self._compact_context(rfc_doc),
        )
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
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            rfc_doc=self._compact_context(rfc_doc),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "res_query"
        )

        return pmp, self.json_extract(ans)

    async def llm_request_type_rules(
            self,
            rfc_num: str,
            pro_name: str,
            field_info: str,
            rfc_doc: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_req_type_rules
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            field_info=self._compact_context(field_info),
            rfc_doc=self._compact_context(rfc_doc),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="req_type_rules"
        )
        return pmp, self.json_extract(ans)

    async def llm_response_type_rules(
            self,
            rfc_num: str,
            pro_name: str,
            field_info: str,
            rfc_doc: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_res_type_rules
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            field_info=self._compact_context(field_info),
            rfc_doc=self._compact_context(rfc_doc),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="res_type_rules"
        )
        return pmp, self.json_extract(ans)

    async def llm_section_type_annotation(
            self,
            rfc_num: str,
            pro_name: str,
            request_types: str,
            response_types: str,
            content_type: str,
            section_name: str,
            section_content: str
    ) -> tuple[str, str]:
        tmp = self.pmp._tem_section_type_annotation
        pmp = tmp.substitute(
            rfc_num=rfc_num,
            pro_name=pro_name,
            request_types=self._compact_context(request_types),
            response_types=self._compact_context(response_types),
            content_type=content_type,
            section_name=section_name,
            section_content=self._compact_context(section_content),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="section_type_annotation"
        )
        return pmp, self.json_extract(ans)
    
    async def llm_possible_res(
            self,
            pro_name: str,
            current_request: str,
            response_types: str,
            info: str = ""
    ) -> str:
        tmp = self.pmp._tem_possible_response
        pmp = tmp.substitute(
            pro_name=pro_name,
            current_request=current_request,
            response_types=self._compact_context(response_types),
            info=self._compact_context(info),
        )
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
