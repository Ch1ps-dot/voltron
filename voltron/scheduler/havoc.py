from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
from voltron.executor.executor import Executor, Conversation
from voltron.analyzer.analyzer import analyzer
from voltron.scheduler.automata import MealyMachine
from voltron.utils.logger import logger
import random, time, threading, os



class Havoc:
    def __init__(
        self,
        mapper: Mapper,
        exe: Executor,
        machine: MealyMachine
    ) -> None:
        self.res_trans_types: dict[str, int] = {}
        self.mapper = mapper
        self.exe = exe
        self.alphabet = mapper.request_types
        self.rand = random.Random( time.time_ns() ^ os.getpid() ^ threading.get_ident())
        if machine:
            self.machine = machine
            self.table = machine.table
            self.E = list(self.table[1])
            self.T = self.table[2]
            self.S = []
            for p in list(self.table[0]):
                if len(p) == 1:
                    self.S.append(p)
                elif len(p) > 1 and self.T[p[:-1]][p[-1:]] != 'CRASH' and self.T[p[:-1]][p[-1:]] != 'TIMEOUT':
                    self.S.append(p)
            
        else:
            self.machine = None

    def select_prefix(
        self
    ) -> list[tuple[str, bytes]]:
        p = self.rand.choice(self.S)
        logger.debug(f'p: {p}')
        w = list(p)
        gs = self.mapper.select_generators(w)
        return gs
    
    def select_mutators(
        self
    ) -> list[tuple[str, bytes]]:
        scope = self.rand.randint(1, 10)
        logger.debug(scope)
        req_seq = []
        for i in range(scope):
            a = self.rand.choice(self.alphabet)
            logger.debug(f'a: {a}')
            req_seq.append(a)
        logger.debug(f'mutators: {req_seq}')
        ms = self.mapper.select_mutators(req_seq)
        ms = [(f'{msg_type}*', data) for msg_type, data in ms]
        return ms
    
    def run(
        self,
        times: int
    ):
        logger.debug(self.S)
        logger.debug(self.alphabet)
        analyzer.set_progress('havoc', 'havoc fuzz', times)
        for i in range(times):
            last_resp_num = analyzer.res_types_num()
            last_trans_nums = analyzer.resp_trans_num()
            
            prefix = self.select_prefix()
            ms = self.select_mutators()
            req_seq = prefix + ms

            flag, cons = self.exe.interact(req_seq, poll_wait_ms=3000)
            if cons != None:
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = '/'.join(cons.res_seq)
            else:
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = 'None'
            analyzer.finished += 1
            
            cur_trans_nums = analyzer.resp_trans_num()
            cur_resp_num = analyzer.res_types_num()
            if flag and self.is_interesting(cur_trans_nums - last_trans_nums, cur_resp_num - last_resp_num) and cons != None:
                cons.save_cons()
        analyzer.clean_progress()
        
    def is_interesting(
        self,
        trans_inc: int,
        type_inc: int
    ) -> bool:
        if trans_inc > 0 or type_inc > 0:
            return True
        else:
            return False