class Conversation:
    """Record the conversation
    
    Maybe record more information in future
    """
    def __init__(self) -> None:
        self.content: list[list[bytes | None]] = []
        self.trans: list[list[str | None]] = []
        
    def add_data(
        self,
        request: bytes | None,
        response: bytes | None
    ):
        self.content.append([request, response])
        
    def add_state(
        self,
        req_code: str | None,
        res_code: str | None
    ):
        self.trans.append([req_code, res_code])