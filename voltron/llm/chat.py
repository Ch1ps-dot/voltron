from openai import OpenAI
from ..configs import settings
from ..utils.logger import logger

class Chater:
    """chat with llm through api.

    Attributes:
        clt: client for chat
    """
    def __init__(
            self
    ) -> None:
        try:
            client = OpenAI(
                base_url=settings.base_url,
                api_key=settings.api_key
            )
        except Exception as e:
            print("Connection Error")
        self.clt = client

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
        
        response: str | None = completion.choices[0].message.content

        return response

    def gen_input(
            self,
            dir: str = '../input'
    ) -> str | None:
        """Generate input generator and save to target directory

        Args:

        Returns:
            path of generated results
        """
        pass