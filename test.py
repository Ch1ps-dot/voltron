from voltron.utils.rag import RFCAgent, SectionNode, SectionTree
import os
from pathlib import Path
from pprint import pprint
import re

def save_to_file(str):
    f = open( 'test.txt', 'w+')
    f.write(str)
    f.close()

# def test_db_query():
#     agent = RAGRfc(Path('test/docs/rfc959.txt').resolve())
#     ans = agent.db_query('QUIT')
#     pprint(ans)

def test_toc():
    # agent = RAGRfc(Path('test/docs/rfc9112.txt').resolve())
    agent = RFCAgent(Path('test/docs/rfc8010.txt').resolve())
    ans = agent.toc_extract(agent.doc_content)
    if ans is not None:
        toc = ans['toc']
        rest = ans['rest']
    save_to_file(toc)

def test_re():
    reg = r'^(?<!\S)' + r'\d+\.'+ r'\s+.*'
    reg1 = r'^(?<!\S)' + r'\d+\.'*2 + r'\s+.*'
    pattern = re.compile(reg1, re.MULTILINE)
    agent = RFCAgent(Path('test/docs/rfc8010.txt').resolve())
    ans = agent.toc_extract(agent.doc_content)

    if ans is not None:
        toc = ans['toc']
        rest = ans['rest']
    section = pattern.finditer(rest)
    if section != None:
        for s in section:
            print(s.group())

def test_section():
    agent = RFCAgent(Path('test/docs/rfc8010.txt').resolve())
    st = agent.section_split(agent.doc_content)
    if st != None:
        st.output_tree()

if __name__ == "__main__":
    # test_db_query()
    # test_re()
    test_section()