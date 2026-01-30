from voltron.configs import configs
class Conversation:
    """Record the conversation
    
    Maybe record more information in future
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
        
    def save_cons(
        self
    ):
        target_folder = configs.results_path / 'testcases'
        file_count = 0
        for item in target_folder.iterdir():
            if item.is_file():
                file_count += 1
            
        with open(target_folder / f'{'-'.join(self.res_seq)}.raw', 'ab') as f:
            for request, _ in self.content:
                if request:
                    f.write(request)
                    
                