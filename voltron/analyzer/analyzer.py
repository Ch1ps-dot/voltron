import threading, time
from pathlib import Path
from voltron.utils.logger import logger
from voltron.producer.AsyncProducer import Generator, Parser

class Analyzer:
    def __init__(
            self,
            target_name,
            pro_name
    ) -> None:
        
        # counter for metric
        self.req_types_cnt: dict[str, int] = {}
        self.res_types_cnt: dict[str, int] = {}
        self.trans_types_cnt: dict[str, int] = {}
        self.req_num = 0
        self.res_num = 0
        self.path_num = 0

        # information of fuzzer
        self.target_name = target_name
        self.pro_name = pro_name
        self.start_time: float
        self.strategy = ''

        self.autamata = None
        self.lock: threading.Lock = threading.Lock()
        self.last_sent = '-'
        self.last_recv = '-'
        
        self.last_generator: Generator | None = None # last executed generator
        self.last_parser: Parser | None = None # last executed parser

    def collect_results(
            self
    ):  
        current_time_struct = time.localtime()
        formatted_time = time.strftime("%m%d_%H_%M_%S", current_time_struct)
        results_dir = Path.cwd() / f'out-{self.target_name}-voltron-{formatted_time}'
        if not results_dir.is_dir():
            results_dir.mkdir()

        results_file = results_dir / f'fuzzer_stats'
        try:
            with results_file.open(mode='w', encoding='utf-8') as f:
                f.write(f'{"start_time":<15}: {self.start_time}')
                f.write(f'{"running_time":<15}: {self.seconds_to_hms(time.time() - self.start_time)}')
                f.write(f'{"target_name":<15}: {self.target_name}')
                f.write(f'{"protocol_name":<15}: {self.pro_name}')
                f.write(f'{"exec_path_num":<15}: {self.path_num}')
                f.write(f'{"sent_request":<15}: {self.req_num}')
                f.write(f'{"distinct_resp":<15}: {self.res_types_num()}')
                f.write(f'{"req/res_pair":<15}: {self.trans_types_num()}')
        except Exception as e:
            logger.debug('Analyzer: collect results failure')

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
            logger.debug(f'Analyzer: new reply {res_code}')
        else:
            self.res_types_cnt[res_code] = 1
        
        self.trans_types_update(f'{self.last_sent}/{self.last_recv}')

    def trans_types_update(
            self,
            trans: str
    ):
        if trans in self.trans_types_cnt.keys():
            self.trans_types_cnt[trans] += self.trans_types_cnt[trans] + 1
        else:
            self.trans_types_cnt[trans] = 1
            logger.debug(f'Analyzer: new transition {trans}')

    
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
    
    def unseen_res_types(
        self
    ) -> list:
        return [res_type for res_type in self.req_types_cnt if self.req_types_cnt[res_type] == 0]
    
    def seconds_to_hms(
            self, 
            seconds: float
        ) -> str:
        total_seconds = int(seconds)
        remaining_seconds = seconds - total_seconds
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if remaining_seconds > 0:
            return f"{hours:02d}:{minutes:02d}:{secs + remaining_seconds:.1f}"
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
