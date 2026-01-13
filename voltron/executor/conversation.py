class Conversation:
    """Record the conversation
    
    Maybe record more information in future
    """
    def __init__(self) -> None:
        self.cons: list[list[bytes]] = []
        self.trans: list[list[str]] = []
        
    def add_data(
        self,
        request,
        response
    ):
        self.cons.append([request, response])
        
    def add_state(
        self,
        req_code,
        res_code
    ):
        self.trans.append([req_code, res_code])