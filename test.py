from voltron.utils.rag import RFCRag
from voltron.utils.setciontree import SectionNode, SectionTree
import os
import re
import time
from pathlib import Path
from pprint import pprint
import cProfile


def save_to_file(str):
    f = open( 'test.txt', 'w+')
    f.write(str)
    f.close()

# def test_db_query():
#     agent = RAGRfc(Path('test/docs/rfc959.txt').resolve())
#     ans = agent.db_query('QUIT')
#     pprint(ans)

# def test_toc():
#     # agent = RAGRfc(Path('test/docs/rfc9112.txt').resolve())
#     agent = RFCAgent(Path('test/docs/rfc8010.txt').resolve())
#     ans = agent.doc_toc
#     if ans is not None:
#         save_to_file(ans)

# def test_re():
#     reg = r'^(?<!\S)' + r'\d+\.'+ r'\s+.*'
#     reg1 = r'^(?<!\S)' + r'\d+\.'*2 + r'\s+.*'
#     pattern = re.compile(reg1, re.MULTILINE)
#     agent = RFCAgent(Path('test/docs/rfc8010.txt').resolve())
#     ans = agent._toc_extract(agent.doc_content)

#     if ans is not None:
#         toc = ans['toc']
#         rest = ans['rest']
#     section = pattern.finditer(rest)
#     if section != None:
#         for s in section:
#             print(s.group())

def test_section():
    agent = RFCRag(Path('test/docs/rfc9110.txt').resolve())
    st = agent.st
    if st != None:
        print(st.fetch_toc())
        # pprint(st.tree)

def test_promt():
    from voltron.llm.prompt import Prompter
    pt = Prompter(Path('./prompts').resolve())
    print(pt.msg_input_gen("ftp", "GET", "test")) 

def test_gen():
    from  voltron.llm.chat import Chater
    ct = Chater(Path('./prompts').resolve())
    print(ct.gen_input("ftp", "CWD", "test"))

if __name__ == "__main__":
    # cProfile.run("test_section()", sort=1)
    # test_promt()
    test_gen()