from openai import OpenAI
from ..configs import ftp, llm

class LLM:
  def __init__(
      self
      ) -> None:
  
    try:
      client = OpenAI(
        base_url=llm.base_url,
        api_key=llm.api_key
      )
    except Exception as e:
      print("Connection Error")
    self.clt = client

  def chatllm(self, msg: str = "") -> str | None:
    try:
      completion = self.clt.chat.completions.create(
        model=llm.model,
        messages=[
          {"role": "system", "content": "You are a protocol fuzzer developer."},
          {"role": "user", "content": msg}
        ]
      )
    except Exception as e:
      print("Chat Error")
    
    response: str | None = completion.choices[0].message.content

    return response
  