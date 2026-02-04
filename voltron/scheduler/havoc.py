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
        self.alphabet = list(mapper.request_types)
        self.req_dep: dict[str, dict[str, dict]] = mapper.req_dep
        self.dep_alphabet = list(self.req_dep.keys())
        
        self.req_res: dict[str, set[str]] = {}
        
        self.rand = random.Random( time.time_ns() ^ os.getpid() ^ threading.get_ident())
        self.methods = ['cat', 'int']
        self.mutator_mode = ['new', 'generic', 'dependent']
        self.prefix_mode = ['new', 'generic', 'dependent']
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
        mode = ''
        if len(self.useful_seq) == 0:
            mode = 'new'
        else:
            mode = self.rand.choice(self.prefix_mode)
        gs = []
        
        if mode == 'new':
            p = self.rand.choice(self.S)
            w = list(p)
            gs = self.mapper.select_generators(w)
           
        elif mode == 'generic':
            gs = self.rand.choice(self.useful_seq)
            
        elif mode == 'dependent':
            if len(self.dep_alphabet) > 0:
                cur_req = self.rand.choice(self.dep_alphabet)
                req_seq = []
                while True:
                    if cur_req in req_seq or cur_req not in self.dep_alphabet:
                        req_seq = [cur_req] + req_seq
                        break
                    req_seq = [cur_req] + req_seq
                gs = self.mapper.select_generators(req_seq)
            else:
                gs = self.rand.choice(self.useful_seq)
        logger.debug(f'select prefix[{mode}]: {'/'.join([g[0] for g in gs])}')
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
        mode = ''
        if len(self.useful_msg) == 0:
            mode = 'new'
        else:
            mode = self.rand.choice(self.prefix_mode)
            
        if mode == 'new':
            req_seq = []
            for i in range(scope):
                a = self.rand.choice(self.alphabet)
                req_seq.append(a)
            ms = self.mapper.select_mutators(req_seq)
            ms = [(f'{msg_type}', data) for msg_type, data in ms]
                
        elif mode == 'generic':
            for i in range(scope):
                a = self.rand.choice(self.useful_msg)
                ms.append(a)
            ms = [(f'{msg_type}', data) for msg_type, data in ms]
            
        elif mode == 'dependent':
            if len(self.dep_alphabet) > 0:
                cur_req = self.rand.choice(self.dep_alphabet)
                req_seq = []
                while True:
                    if cur_req in req_seq or cur_req not in self.dep_alphabet:
                        req_seq = [cur_req] + req_seq
                        break
                    req_seq = [cur_req] + req_seq
                    
                    last_dict: dict[str, dict] = self.req_dep[cur_req]
                    last_req = self.rand.choice(list(last_dict.keys()))
                    cur_req = last_req
                ms = self.mapper.select_mutators(req_seq)
                ms = [(f'{msg_type}', data) for msg_type, data in ms]
            else:
                for i in range(scope):
                    a = self.rand.choice(self.useful_msg)
                    ms.append(a)
                    ms = [(f'{msg_type}', data) for msg_type, data in ms]
        logger.debug(f'select mutators[{mode}]: {'/'.join([m[0] for m in ms])}')
        return ms
    
    def analyze_cons(
        self,
        cons: Conversation
    ):
        seq = []
        for i in range(len(cons.res_seq)):
            req = cons.req_seq[i]
            res = cons.res_seq[i]
            if res == '-':
                continue
            if res == 'TIMEOUT':
                break
            if res not in self.unique_resp:
                self.unique_resp.add(res)
                self.useful_msg.append((res, cons.content[i][0]))
                seq.append((req, cons.content[i][0]))
            
            if req == '-':
                continue
            else:
                map = self.req_res.setdefault(req, set())
                map.add(res)
        self.useful_seq.append(seq)
        
    def run(
        self,
        times: int
    ) -> dict[str, set[str]]:
        logger.debug(self.S)
        logger.debug(self.alphabet)
        analyzer.set_progress('havoc', 'fuzz energy', times)
        energy = times
        analyzer.finished = energy
        while energy >= 0:
            last_resp_num = analyzer.res_types_num()
            last_trans_nums = analyzer.resp_trans_num()
            
            ms = []
            prefix = self.select_prefix()
            if self.mapper.mutators != {}:
                ms = self.select_mutators()
            suffix = self.select_suffix()
            req_seq = []
            
            method = self.rand.choice(self.methods)
            if (method == 'cat'):
                req_seq = prefix + ms + suffix
            elif (method == 'int'):
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
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq]) + f'({method})'
                analyzer.recv = '/'.join(cons.res_seq)
                logger.debug(f'sent({method}) -> {analyzer.sent}')
                logger.debug(f'recv({method}) <- {analyzer.recv}')
            else:
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = 'None'
            
            cur_trans_nums = analyzer.resp_trans_num()
            cur_resp_num = analyzer.res_types_num()
            if cur_trans_nums <= last_trans_nums:
                energy -= 1
                analyzer.finished -= 1
            else:
                energy += 1
                analyzer.finished += 1
                
            if flag and self.is_interesting(cur_trans_nums - last_trans_nums, cur_resp_num - last_resp_num) and cons != None:
                cons.save_cons()
        
        analyzer.clean_progress()
        return self.req_res
        
    def is_interesting(
        self,
        trans_inc: int,
        type_inc: int
    ) -> bool:
        if trans_inc > 0 or type_inc > 0:
            return True
        else:
            return False
        