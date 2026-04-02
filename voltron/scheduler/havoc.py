from voltron.mapper.mapper import Mapper
from voltron.producer.producer import Generator
from voltron.executor.executor import Executor, Conversation
from voltron.analyzer.analyzer import analyzer
from voltron.scheduler.automata import MealyMachine
from voltron.utils.logger import logger
import random, time, threading, os, math

class Havoc:
    """Havoc scheduler implementation for fuzzing the system under test (SUT) with random sequences of requests, aiming to explore the state space and find interesting behaviors.
    
    Attributes:
        unique_resp: A set of unique responses observed during fuzzing.
        max_unique_resp_num: The maximum number of unique responses observed so far.
        unique_resp_trans: A set of unique response transitions observed during fuzzing.
        useful_msg: A list of useful messages (request-response pairs) that have been observed during fuzzing.
        useful_seq: A list of useful sequences of request-response pairs that have been observed during fuzzing.
        max_seq_len: The maximum length of request-response sequences observed so far.
        mapper: An instance of the Mapper class for selecting generators and mutators based on request sequences.
        exe: An instance of the Executor class for interacting with the SUT and obtaining responses.
        alphabet: A list of request types that can be used for generating test sequences.
        req_dep: A dictionary representing the dependencies between requests and their possible responses, used for generating dependent sequences.
        dep_alphabet: A list of request types that have dependencies, used for generating dependent sequences.
        req_res: A dictionary mapping request types to the set of response types observed for those requests
    """
    def __init__(
        self,
        mapper: Mapper,
        exe: Executor,
        machine: MealyMachine
    ) -> None:
        self.unique_resp: set[str] = set()
        self.max_unique_resp_num = 0
        self.unique_resp_trans: set[str] = set()
        self.useful_msg: list[tuple[str, bytes]] = []
        self.useful_seq: list[list[tuple[str, bytes]]] = []
        self.max_seq_len = 0
        
        self.mapper = mapper
        self.exe = exe
        self.alphabet = list(mapper.request_types)
        self.req_dep: dict[str, dict[str, dict]] = mapper.req_dep
        self.dep_alphabet = list(self.req_dep.keys())
        
        self.req_res: dict[str, set[str]] = {}
        
        self.rand = random.Random( time.time_ns() ^ os.getpid() ^ threading.get_ident())
        
        # Define the methods and modes for selecting prefixes, mutators, and suffixes during fuzzing
        # cat: concatenate prefix, mutators, and suffix; 
        # int: interleave prefix and mutators, then concatenate with suffix
        self.methods = ['cat', 'int']
        
         # new: select new sequences or messages that have not been observed before; 
        # generic: select from the useful sequences or messages observed so far; 
        # dependent: select sequences or messages based on the dependencies between requests
        self.mutator_mode = ['new', 'generic', 'dependent']
        self.prefix_mode = ['new', 'generic', 'dependent']
        self.suffix_mode = ['new', 'generic']
        
        # Initialize the automaton and related sets based on the provided Mealy machine, if available
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
        """Select a prefix sequence of requests to be used for generating test sequences, based on the observed useful sequences and the dependencies between requests.
        """
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
            scope = self.rand.randint(1, 8)
            gs = []
            for i in range(scope):
                gs += self.rand.choice(self.useful_seq)
            
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
                gs = self.mapper.select_generators(req_seq)
            else:
                gs = self.rand.choice(self.useful_seq)
        logger.debug(f'select prefix[{mode}]: {'/'.join([g[0] for g in gs])}')
        return gs
    
    def select_suffix(
        self
    ) -> list[tuple[str, bytes]]:
        p = self.rand.choice(self.E)
        w = list(p)
        gs = self.mapper.select_generators(w)
        return gs
    
    def select_mutators(
        self
    ) -> list[tuple[str, bytes]]:
        scope = self.rand.randint(1, 42)
        mut = self.rand.choice([True, False])
        ms = []
        mode = ''
        if len(self.useful_msg) == 0:
            mode = 'new'
        else:
            mode = self.rand.choice(self.mutator_mode)
            
        if mode == 'new':
            req_seq = []
            for i in range(scope):
                a = self.rand.choice(self.alphabet)
                req_seq.append(a)
                
            if mut:
                ms = self.mapper.select_mutators(req_seq)
            else:
                ms = self.mapper.select_generators(req_seq)
                
        elif mode == 'generic':
            for i in range(scope):
                a = self.rand.choice(self.useful_msg)
                ms.append(a)
            
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
                if mut:
                    ms = self.mapper.select_mutators(req_seq)
                else:
                    ms = self.mapper.select_generators(req_seq)
            else:
                for i in range(scope):
                    a = self.rand.choice(self.useful_msg)
                    ms.append(a)
                    
        logger.debug(f'select mutators[{mode}]: {'/'.join([m[0] for m in ms])}')
        return ms
    
    def analyze_cons(
        self,
        cons: Conversation,
        trans_inc: int,
        type_inc: int
    ):
        """Analyze the conversation obtained from interacting with the SUT.
        
        Args:
            cons: The conversation object containing the request and response sequences, as well as the content of the responses
            trans_inc: The increment in the number of response transitions observed compared to the last interaction
            type_inc: The increment in the number of unique response types observed compared to the last interaction
        """
        seq = []
        for i in range(len(cons.res_seq)):
            req = cons.req_seq[i]
            res = cons.res_seq[i]
            if res == '-' or res == '-':
                continue
            
            if res == 'TIMEOUT' or res == 'CRASH':
                break
            
            if res not in self.unique_resp:
                self.unique_resp.add(res)
                self.useful_msg.append((req, cons.content[i][0]))
                seq = []
                for j in range(i+1):
                    if cons.req_seq[j] != '-':
                        seq.append((cons.req_seq[j], cons.content[j][0]))
                self.useful_seq.append(seq)
            
            if req != '-':
                map = self.req_res.setdefault(req, set())
                map.add(res)
            
        seq_len = len(cons.res_seq)
        unique_res_num = len(set(cons.res_seq))
        unique_res_inc = unique_res_num - self.max_unique_resp_num
            
        len_inc = seq_len - self.max_seq_len
        self.max_seq_len = max(seq_len, self.max_seq_len)
        self.max_unique_resp_num = max(unique_res_num, self.max_unique_resp_num)
        
        if self.is_interesting(trans_inc, type_inc, len_inc, unique_res_inc):         
            self.exe.save_cons(cons)
        # seq = []
        # if len(cons.res_seq) > self.max_seq_len:
        #     for i in range(len(cons.res_seq)):
        #         if cons.req_seq[i] != '-':
        #             seq.append((cons.req_seq[i], cons.content[i][0]))
        #     self.useful_seq.append(seq)
        
    def run(
        self,
        times: int
    ) -> dict[str, set[str]]:
        """fuzing the SUT with random sequences of requests.
        """
        logger.debug(self.S)
        logger.debug(self.alphabet)
        analyzer.set_progress('havoc', 'fuzz energy', times)
        energy = times
        analyzer.finished = energy
        
        # fuzzing the SUT until the energy is depleted, where energy is increased when new behaviors are observed and decreased when no new behaviors are found
        while energy >= 0:
            last_resp_num = analyzer.res_types_num()
            last_trans_nums = analyzer.resp_trans_num()
            
            ms = []
            prefix = self.select_prefix()
            if self.mapper.mutators != {}:
                ms = self.select_mutators()
            suffix = self.select_suffix()
            ms = ms + suffix
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
            cur_trans_nums = analyzer.resp_trans_num()
            cur_resp_num = analyzer.res_types_num()
            
            if cons != None:
                self.analyze_cons(cons, cur_trans_nums - last_trans_nums, cur_resp_num - last_resp_num)
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq]) + f'({method})'
                analyzer.recv = '/'.join(cons.res_seq)
                logger.debug(f'sent({method}) -> {analyzer.sent}')
                logger.debug(f'recv({method}) <- {analyzer.recv}')
            else:
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = 'None'
            
            if cur_trans_nums <= last_trans_nums:
                energy -= 1
                with analyzer.lock:
                    analyzer.finished -= 1
            else:
                energy += 1
                with analyzer.lock:
                    analyzer.finished += 1
                
        
        analyzer.clean_progress()
        return self.req_res
        
    def is_interesting(
        self,
        trans_inc: int,
        type_inc: int,
        len_inc: int,
        unique_res_inc: int
    ) -> bool:
        """Check if the current conversation is interesting based on the increments in response transitions, response types, sequence length, and unique response types.
        
        Args:
            trans_inc: The increment in the number of response transitions observed.
            type_inc: The increment in the number of unique response types observed.
            len_inc: The increment in the length of the request-response sequence observed.
            unique_res_inc: The increment in the number of unique response types observed.
        """
        if trans_inc > 0 or type_inc > 0 or len_inc > 0 or unique_res_inc > 0:
            with analyzer.lock:
                analyzer.useful_cons += 1
            logger.debug(f'{trans_inc} {type_inc} {len_inc}')
            return True
        else:
            return False
        