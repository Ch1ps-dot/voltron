from openai import OpenAI
from ..configs import settings

class LLM:
    def __init__(self) -> None:
    
      try:
        client = OpenAI(
          base_url=settings.base_url,
          api_key=settings.api_key
        )
      except Exception as e:
        print("Connection Error")
      self.clt = client

    def chatllm(self, msg: str = "") -> str | None:
      try:
        completion = self.clt.chat.completions.create(
          model=settings.model,
          messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": msg}
          ]
        )
      except Exception as e:
        print("Chat Error")
      
      response: str | None = completion.choices[0].message.content

      return response
  