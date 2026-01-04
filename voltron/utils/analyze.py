import threading
from .logger import logger
class Analyzer:
    def __init__(
            self,
            target_name,
            pro_name
    ) -> None:
        self.req_types_cnt: dict[str, int] = {}
        self.res_types_cnt: dict[str, int] = {}
        self.trans_types_cnt: dict[str, int] = {}
        self.autamata = None
        self.req_num = 0
        self.path_num = 0
        self.target_name = target_name
        self.pro_name = pro_name
        self.start_time: float
        self.strategy = ''
        self.lock: threading.Lock = threading.Lock()

    def req_types_update(
            self,
            req_code: str
    ):
        if req_code in self.req_types_cnt.keys():
            self.req_types_cnt[req_code] += self.req_types_cnt[req_code] + 1
        else:
            self.req_types_cnt[req_code] = 1

    def res_types_update(
            self,
            res_code: str
    ):
        if res_code in self.res_types_cnt.keys():
            self.res_types_cnt[res_code] += self.res_types_cnt[res_code] + 1
            logger.debug(f'new reply: {res_code}')
        else:
            self.res_types_cnt[res_code] = 1

    def trans_types_update(
            self,
            trans: str
    ):
        if trans in self.trans_types_cnt.keys():
            self.trans_types_cnt[trans] += self.trans_types_cnt[trans] + 1
            logger.debug(f'new transition: {trans}')
        else:
            self.trans_types_cnt[trans] = 1

    
    def req_types_num(
            self
    ):
        return len(self.req_types_cnt.keys())
    
    def res_types_num(
            self
    ):
        return len(self.res_types_cnt.keys())
    
    def trans_types_num(
            self
    ):
        return len(self.trans_types_cnt.keys())