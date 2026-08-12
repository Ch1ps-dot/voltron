import asyncio
from pathlib import Path
from string import Template
from types import SimpleNamespace

import pytest

from voltron.llm.chatter import AsyncChater
from voltron.llm.response_validation import LLMResponseValidationError


def make_chatter(response: str) -> AsyncChater:
    chatter = AsyncChater.__new__(AsyncChater)
    template = Template((Path(__file__).resolve().parents[1] / 'skills' /
                         'evolver' / 'generator_mutate.md').read_text())
    chatter.pmp = SimpleNamespace(_tem_mutator_evolve=template)

    async def chat_llm(*, prompt, usage):
        assert usage == 'mutator_evolve'
        return response

    chatter.chat_llm = chat_llm
    return chatter


def evolve(chatter):
    return asyncio.run(chatter.llm_mutator_evolve(
        pro_name='ftp', field_name='command', msg_type='USER',
        code="def generate():\n    return b'USER x\\r\\n'\n",
        msg_ir='{}', info='', poss_response='331', trace='[]',
    ))


def test_mutator_evolve_accepts_complete_python_source():
    result = evolve(make_chatter("def mutate() -> bytes:\n    return b'USER !\\r\\n'\n"))
    assert result == "def mutate() -> bytes:\n    return b'USER !\\r\\n'\n"


def test_mutator_evolve_rejects_incremental_json_response():
    with pytest.raises(LLMResponseValidationError):
        evolve(make_chatter('{"base_sha256":"0"}'))
