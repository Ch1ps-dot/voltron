from voltron.configs import configs
class Conversation:
    """Record the conversation
    
    Maybe record more information in future
    
    Attributes:
        content: A list of tuples containing the raw request and response data in bytes.
        req_seq: A list of strings representing the sequence of request codes sent to the SUT.
        res_seq: A list of strings representing the sequence of response codes received from the SUT
    """
    def __init__(self) -> None:
        self.content: list[tuple[bytes, bytes]] = []
        self.req_seq: list[str] = []
        self.res_seq: list[str] = []
        
    def add_data(
        self,
        request: bytes,
        response: bytes
    ):
        self.content.append((request, response))
        
    def add_state(
        self,
        req_code: str,
        res_code: str
    ):
        self.req_seq.append(req_code)
        self.res_seq.append(res_code)
        
    def merge_extra_state(
        self,
        extra_res: str
    ):
        self.res_seq[-1] = f'{self.res_seq[-1]}/{extra_res}'
        
                    
                