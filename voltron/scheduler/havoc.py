from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
from voltron.executor.executor import Executor, Conversation
from voltron.analyzer.analyzer import analyzer
from voltron.scheduler.automata import MealyMachine
from voltron.utils.logger import logger
import random, time, threading, os, math



class Havoc:
    def __init__(
        self,
        mapper: Mapper,
        exe: Executor,
        machine: MealyMachine
    ) -> None:
        self.unique_resp: set[str] = set()
        self.unique_resp_trans: set[str] = set()
        self.useful_msg: list[tuple[str, bytes]] = []
        self.useful_seq: list[list[tuple[str, bytes]]] = []
        
        self.mapper = mapper
        self.exe = exe
        self.alphabet = mapper.request_types
        self.rand = random.Random( time.time_ns() ^ os.getpid() ^ threading.get_ident())
        self.methods = ['cat', 'inter']
        self.mutator_mode = ['new', 'generic']
        self.prefix_mode = ['new', 'generic']
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
        mode = self.rand.choice(self.prefix_mode)
        gs = []
        
        if mode == 'new' or len(self.useful_seq) == 0:
            p = self.rand.choice(self.S)
            w = list(p)
            gs = self.mapper.select_generators(w)
           
        elif mode == 'generic':
            gs = self.rand.choice(self.useful_seq)

        return gs
    
    def select_suffix(
        self
    ) -> list[tuple[str, bytes]]:
        s = self.rand.choice(self.E)
        w = list(s)
        gs = self.mapper.select_generators(w)
        return gs
    
    def select_mutators(
        self
    ) -> list[tuple[str, bytes]]:
        scope = self.rand.randint(1, 5)
        ms = []
        mode = self.rand.choice(self.mutator_mode)
        if mode == 'new' or len(self.useful_msg) == 0:
            req_seq = []
            for i in range(scope):
                a = self.rand.choice(self.alphabet)
                req_seq.append(a)
            ms = self.mapper.select_mutators(req_seq)
            ms = [(f'{msg_type}*', data) for msg_type, data in ms]
                
        elif mode == 'generic':
            for i in range(scope):
                a = self.rand.choice(self.useful_msg)
                ms.append(a)
            ms = [(f'{msg_type}*', data) for msg_type, data in ms]
        return ms
    
    def analyze_cons(
        self,
        cons: Conversation
    ):
        seq = []
        for i in range(len(cons.res_seq)):
            if cons.res_seq[i] == '-':
                continue
            if cons.res_seq[i] == 'TIMEOUT':
                break
            if cons.res_seq[i] not in self.unique_resp:
                self.unique_resp.add(cons.res_seq[i])
                self.useful_msg.append((cons.req_seq[i], cons.content[i][0]))
                seq.append((cons.req_seq[i], cons.content[i][0]))
        self.useful_seq.append(seq)
        
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
            suffix = self.select_suffix()
            req_seq = []
            
            method = self.rand.choice(self.methods)
            if (method == 'cat'):
                req_seq = prefix + ms + suffix
            elif (method == 'inter'):
                len_p = len(prefix)
                len_m = len(ms)
                max_len = max(len_p, len_m)
                for i in range(max_len):
                    if (i < len_p):
                        req_seq.append(prefix[i])
                    if (i < len_m):
                        req_seq.append(ms[i])

            flag, cons = self.exe.interact(req_seq, poll_wait_ms=3000)
            if cons != None:
                self.analyze_cons(cons)
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = '/'.join(cons.res_seq)
                logger.debug(f'sent -> {analyzer.sent}')
                logger.debug(f'recv <- {analyzer.recv}')
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