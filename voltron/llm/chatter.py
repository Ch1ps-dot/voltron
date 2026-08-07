from pathlib import Path
from openai import AsyncOpenAI, OpenAIError
import ast
import json
import time, re
from re import Match
from string import Template
import asyncio
from xml.etree import ElementTree

from voltron.llm.prompt import Prompter
from voltron.llm.incremental import (
    IncrementalOutputError,
    apply_ir_delta,
    apply_source_delta,
    content_sha256,
    numbered_source_context,
    parse_json_artifact,
)
from voltron.utils.logger import format_event, logger_llm as logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer


SYSTEM_PROMPT = "Follow the task contract. Return only the requested artifact."


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

    @staticmethod
    def _xml_ir_to_field_table(
        value: object,
        message_name: str | None = None,
    ) -> str:
        """Convert protoIR XML into a compact, loss-aware field table.

        Field attributes become shared columns and each field becomes one row.
        Semantic XML comments are retained as short ``note`` values.  Invalid
        or unsupported XML is returned unchanged so repair prompts can still
        receive the malformed source text that they need to fix.
        """
        source = '' if value is None else str(value)
        try:
            parser = ElementTree.XMLParser(
                target=ElementTree.TreeBuilder(insert_comments=True)
            )
            root = ElementTree.fromstring(source, parser=parser)
        except (ElementTree.ParseError, TypeError, ValueError):
            return source

        if root.tag == 'message':
            message_elements = [root]
        elif root.tag == 'ir':
            message_elements = list(root.findall('.//message'))
        else:
            return source
        if not message_elements:
            return source
        if message_name:
            matching = [
                message
                for message in message_elements
                if message.attrib.get('name') == message_name
            ]
            if matching:
                message_elements = matching

        preferred_columns = ['name', 'type', 'length', 'value']
        extra_columns: set[str] = set()
        has_notes = False
        parsed_messages: list[dict[str, object]] = []

        for message in message_elements:
            message_note: list[str] = []
            fields: list[dict[str, str]] = []
            last_field: dict[str, str] | None = None
            for child in message:
                if child.tag is ElementTree.Comment:
                    note = ' '.join((child.text or '').split())
                    if not note:
                        continue
                    has_notes = True
                    if last_field is None:
                        message_note.append(note)
                    else:
                        previous = last_field.get('note')
                        last_field['note'] = (
                            f'{previous} {note}' if previous else note
                        )
                    continue
                if child.tag != 'field':
                    continue
                last_field = dict(child.attrib)
                fields.append(last_field)
                has_notes = has_notes or 'note' in child.attrib
                extra_columns.update(
                    key
                    for key in child.attrib
                    if key not in preferred_columns and key != 'note'
                )

            record: dict[str, object] = {
                'name': message.attrib.get('name', ''),
                '_fields': fields,
            }
            extra_message_attrs = {
                key: val for key, val in message.attrib.items() if key != 'name'
            }
            if extra_message_attrs:
                record['attributes'] = extra_message_attrs
            if message_note:
                record['note'] = ' '.join(message_note)
            parsed_messages.append(record)

        columns = preferred_columns + sorted(extra_columns)
        if has_notes:
            columns.append('note')
        messages: list[dict[str, object]] = []
        for parsed in parsed_messages:
            fields = parsed.pop('_fields')
            parsed['fields'] = [
                [field.get(column) for column in columns]
                for field in fields
            ]
            messages.append(parsed)

        table: dict[str, object] = {
            'columns': columns,
            'messages': messages,
        }
        if root.tag == 'ir' and root.attrib:
            table['ir_attributes'] = dict(root.attrib)
        return json.dumps(
            table,
            ensure_ascii=False,
            separators=(',', ':'),
        )

    @classmethod
    def _fit_ir_table(
        cls,
        table: dict[str, object],
        max_chars: int,
    ) -> str:
        """Fit a field table without cutting JSON in the middle of a row."""
        marker = '[... truncated ...]'

        def shorten(item, limit=512):
            if isinstance(item, str) and len(item) > limit:
                retained = max(2, limit - len(marker))
                head = retained * 2 // 3
                return f'{item[:head]}{marker}{item[-(retained - head):]}'
            if isinstance(item, list):
                return [shorten(value, limit) for value in item]
            if isinstance(item, dict):
                return {
                    key: shorten(value, limit) for key, value in item.items()
                }
            return item

        def encode(item):
            return json.dumps(
                item,
                ensure_ascii=False,
                separators=(',', ':'),
            )

        table = shorten(table)
        encoded = encode(table)
        if len(encoded) <= max_chars:
            return encoded

        source_messages = table.get('messages', [])
        if not isinstance(source_messages, list):
            return cls._compact_context(encoded, max_chars)

        base = {key: value for key, value in table.items() if key != 'messages'}
        selected: list[tuple[int, dict[str, object]]] = []
        order: list[int] = []
        left, right = 0, len(source_messages) - 1
        while left <= right:
            order.append(left)
            if right != left:
                order.append(right)
            left += 1
            right -= 1

        def fit_fields(message: dict[str, object]) -> dict[str, object]:
            fields = message.get('fields', [])
            if not isinstance(fields, list):
                return message
            trimmed = {key: value for key, value in message.items() if key != 'fields'}
            kept: list[tuple[int, object]] = []
            field_order: list[int] = []
            left_field, right_field = 0, len(fields) - 1
            while left_field <= right_field:
                field_order.append(left_field)
                if right_field != left_field:
                    field_order.append(right_field)
                left_field += 1
                right_field -= 1
            for index in field_order:
                for field in (fields[index], shorten(fields[index], 128)):
                    candidate = sorted(kept + [(index, field)])
                    candidate_message = {
                        **trimmed,
                        'fields': [item for _, item in candidate],
                        'omitted_fields': len(fields) - len(candidate),
                    }
                    candidate_table = {
                        **base,
                        'messages': [candidate_message],
                        'omitted_messages': max(0, len(source_messages) - 1),
                    }
                    if len(encode(candidate_table)) <= max_chars:
                        kept = candidate
                        break
            return {
                **trimmed,
                'fields': [field for _, field in sorted(kept)],
                'omitted_fields': len(fields) - len(kept),
            }

        for index in order:
            message = source_messages[index]
            if not isinstance(message, dict):
                continue
            fitted = fit_fields(message)
            candidate = sorted(selected + [(index, fitted)])
            candidate_table = {
                **base,
                'messages': [message for _, message in candidate],
                'omitted_messages': len(source_messages) - len(candidate),
            }
            if len(encode(candidate_table)) <= max_chars:
                selected = candidate

        result = {
            **base,
            'messages': [message for _, message in sorted(selected)],
            'omitted_messages': len(source_messages) - len(selected),
        }
        return encode(result)

    @classmethod
    def _compact_ir_context(
        cls,
        value: object,
        message_name: str | None = None,
    ) -> str:
        source = '' if value is None else str(value)
        compact = cls._xml_ir_to_field_table(source, message_name)
        if compact == source:
            return cls._compact_context(source)
        max_chars = max(
            512,
            int(getattr(configs, 'prompt_context_max_chars', 12_000)),
        )
        if len(compact) <= max_chars:
            return compact
        return cls._fit_ir_table(json.loads(compact), max_chars)

    @staticmethod
    def _source_delta_context(source: str) -> tuple[str, str]:
        limit = max(
            512,
            int(getattr(configs, 'prompt_context_max_chars', 12_000)),
        )
        return content_sha256(source), numbered_source_context(source, limit)

    @staticmethod
    def _apply_python_delta(source: str, response: str | None) -> str:
        evolved = apply_source_delta(source, parse_json_artifact(response))
        ast.parse(evolved)
        return evolved

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
                        {"role": "system", "content": SYSTEM_PROMPT},
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
                        usage=usage,
                        model=self.model,
                        tokens_reported=completion.usage is not None,
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
            ir=self._compact_ir_context(ir),
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
        base_sha256 = content_sha256(current_ir)
        pmp = tmp.substitute(
            pro_name=pro_name,
            direction=direction,
            msg_type=msg_type,
            base_sha256=base_sha256,
            current_ir=self._compact_ir_context(current_ir, msg_type),
            type_rule=self._compact_context(type_rule),
            section_context=self._compact_context(section_context),
            feedback=self._compact_context(feedback),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="ir_evolve"
        )
        try:
            return apply_ir_delta(current_ir, parse_json_artifact(ans))
        except IncrementalOutputError as error:
            logger.debug('LLM: invalid IR delta: %s', error)
            return ''

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
            msg_ir=self._compact_ir_context(msg_ir, msg_type),
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
        base_sha256, numbered_code = self._source_delta_context(code)

        pmp = tmp.substitute(
            pro_name=pro_name,
            field_name=field_name,
            msg_type=msg_type,
            code=numbered_code,
            base_sha256=base_sha256,
            msg_ir=self._compact_ir_context(msg_ir, msg_type),
            info=self._compact_context(info),
            trace=self._compact_context(trace),
            related_code=self._compact_context(related_code),
        )
        # logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "generator_evolve"
        )

        return self._apply_python_delta(code, ans)
    
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
        base_sha256, numbered_code = self._source_delta_context(old_code)
        pmp = tmp.substitute(
            pro_name=pro_name,
            res_info=self._compact_context(res_info),
            type_rules=self._compact_context(type_rules),
            original_code=numbered_code,
            base_sha256=base_sha256,
            message=message,
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "parser_evolve"
        )

        return self._apply_python_delta(old_code, ans)
    
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
        base_sha256, numbered_code = self._source_delta_context(code)
        
        pmp = tmp.substitute(
            pro_name=pro_name,
            field_name=field_name,
            msg_type=msg_type,
            code=numbered_code,
            base_sha256=base_sha256,
            msg_ir=self._compact_ir_context(msg_ir, msg_type),
            info=self._compact_context(info),
            poss_response=self._compact_context(poss_response),
            trace=self._compact_context(trace),
        )
        # logger.debug(pmp)
        ans = await self.chat_llm(
            prompt=pmp,
            usage = "mutator_evolve"
        )

        return self._apply_python_delta(code, ans)
        
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
            msg_ir=self._compact_ir_context(msg_ir, response_type),
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
            msg_ir=self._compact_ir_context(msg_ir, response_type),
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
        base_sha256, numbered_code = self._source_delta_context(original_code)
        pmp = tmp.substitute(
            pro_name=pro_name,
            response_type=response_type,
            msg_ir=self._compact_ir_context(msg_ir, response_type),
            original_code=numbered_code,
            base_sha256=base_sha256,
            samples=self._compact_context(samples),
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="observer_evolve",
        )
        return self._apply_python_delta(original_code, ans)

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
            msg_ir=self._compact_ir_context(msg_ir, response_type),
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
        base_sha256, numbered_code = self._source_delta_context(original_code)
        pmp = tmp.substitute(
            pro_name=pro_name,
            response_type=response_type,
            original_code=numbered_code,
            base_sha256=base_sha256,
            response_repr=repr(response),
            response_hex=response.hex(' '),
            review_summary=self._compact_context(review_summary)
        )
        ans = await self.chat_llm(
            prompt=pmp,
            usage="checker_evolve"
        )
        return self._apply_python_delta(original_code, ans)
    
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
