class Analyzer:
    def __init__(
            self
    ) -> None:
        self.req_cnt: set[str] = set()
        self.res_cnt: set[str] = set()
        self.trans_cnt: dict[str, int] = {}

    def req_update(
            self,
            req_code: str
    ):
        self.req_cnt.add(req_code)

    def res_update(
            self,
            res_code: str
    ):
        self.res_cnt.add(res_code)

    def trans_update(
            self,
            trans: str
    ):
        if trans in self.trans_cnt.keys():
            self.trans_cnt[trans] += self.trans_cnt[trans] + 1
        else:
            self.trans_cnt[trans] = 1

    
    def req_num(
            self
    ):
        return len(self.req_cnt)
    
    def res_num(
            self
    ):
        return len(self.res_cnt)
    
    def trans_num(
            self
    ):
        return len(self.trans_cnt.keys())