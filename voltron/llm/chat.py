from openai import OpenAI
from ..configs import settings
from ..utils.logger import logger
from .prompt import Prompter
from pathlib import Path
import re
from re import Match
import time

class Chater:
    """chat with llm through api.

    Attributes:
        clt: client for chat
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        try:
            client = OpenAI(
                base_url=settings.base_url,
                api_key=settings.api_key
            )
        except Exception as e:
            print("Connection Error")
        self.clt = client
        self.pmp = Prompter(dir)

    def chat_llm(
            self, 
            prompt: str = ""
    ) -> str | None:
        """Chat to llm with the prompt

        Args:
            prompt: prompt for llm

        Returns:
            response of llm
        """
        start = time.perf_counter()
        try:
            completion = self.clt.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": "You are a protocol fuzzer developer."},
                    {"role": "user", "content": prompt}
                ]
        )
        except Exception as e:
            print("Chat Error")
        end = time.perf_counter()
        
        response: str | None = completion.choices[0].message.content
        logger.info(f"\n[Chat]\ncost_time:{end - start}")
        return response

    def gen_input(
            self,
            pro_name: str = '',
            msg_type: str = '',
            pending: str = '',
            dir: str = ''
    ) -> str | None:
        """Generate input generator and save to target directory

        Args:
            saving directory of input 

        Returns:
            generated input
        """
        ans = self.chat_llm(
            prompt=self.pmp.msg_input_gen(
                pro_name=pro_name, 
                msg_type=msg_type, 
                pending=pending
            )
        )
        print(ans)
        reg = r'```p(?:y|ython).*```'
        pattern = re.compile(reg, re.MULTILINE)
        if ans != None:
            match: Match | None = pattern.search(ans)
        if match:
            return match.group()
        return ""
        