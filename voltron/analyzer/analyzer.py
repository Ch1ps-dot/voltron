import threading, time, pprint
from pathlib import Path
from voltron.utils.logger import logger
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.configs import configs

class Analyzer:
    def __init__(
            self
    ) -> None:
        
        # counters for metric
        self.req_types_cnt: dict[str, int] = {}
        self.res_types_cnt: dict[str, int] = {}
        self.resp_trans_cnt: dict[str, int] = {}
        self.req_num = 0
        self.res_num = 0
        self.path_num = 0
        self.timeout_num = 0
        self.pollerr_num = 0
        self.crash_num = 0
        self.crash_num = 0
        self.rclose_num = 0

        # information of fuzzer
        self.target_name: str
        self.pro_name: str
        self.start_time: float
        self.strategy = ''
        self.stage = ''
        # self.prefix = ''
        # self.suffix = ''
        # self.out = ''
        self.sent = ''
        self.recv = ''

        self.autamata = None
        self.lock: threading.Lock = threading.Lock()
        self.last_sent = '-'
        self.last_recv = '-'
        
        self.last_generator: Generator | None = None # last executed generator
        self.last_parser: Parser | None = None # last executed parser
        
        # UI progress
        self.show_progress: bool = False

    def collect_results(
            self
    ):  
        

        status_file = configs.results_path / f'fuzzer_status'
        try:
            with status_file.open(mode='w', encoding='utf-8') as f:
                f.write(f'{"start_time":<15}: {self.start_time}\n')
                f.write(f'{"running_time":<15}: {self.seconds_to_hms(time.time() - self.start_time)}\n')
                f.write(f'{"target_name":<15}: {self.target_name}\n')
                f.write(f'{"protocol_name":<15}: {self.pro_name}\n')
                f.write(f'{"exec_path_num":<15}: {self.path_num}\n')
                f.write(f'{"sent_request":<15}: {self.req_num}\n')
                f.write(f'{"distinct_resp":<15}: {self.res_types_num()}\n')
                f.write(f'{"resp_transitions":<15}: {self.resp_trans_num()}\n')
        except Exception as e:
            logger.debug('Analyzer: collect results failure')
            
        states_file = configs.results_path / f'states_info'
        try:
            with states_file.open(mode='w', encoding='utf-8') as f:
                f.write(f'{"response types":<15}:\n')
                pprint.pprint(
                    self.res_types_cnt.keys(),
                    stream=f
                )
                f.write(f'{"response transitions":<15}:\n')
                pprint.pprint(
                    self.resp_trans_cnt.keys(),
                    stream=f
                )
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
        else:
            self.res_types_cnt[res_code] = 1
            logger.debug(f'Analyzer: new reply {res_code}')

    def resp_trans_update(
            self,
            trans: str
    ):
        if trans in self.resp_trans_cnt.keys():
            self.resp_trans_cnt[trans] += self.resp_trans_cnt[trans] + 1
        else:
            self.resp_trans_cnt[trans] = 1
            logger.debug(f'Analyzer: new transition {trans}')

    
    def req_types_num(
            self
    ):
        return len(self.req_types_cnt.keys())
    
    def res_types_num(
            self
    ):
        return len(self.res_types_cnt.keys())
    
    def resp_trans_num(
            self
    ):
        return len(self.resp_trans_cnt.keys())
    
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
        
analyzer = Analyzer()
    
