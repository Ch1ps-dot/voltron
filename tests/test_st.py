from pathlib import Path
from pprint import pprint

from voltron.utils.logger import logger

def test_section():
    from voltron.utils.rfcparser import RFCParser
    agent = RFCParser(Path('./tests/docs/rfc9110.txt').resolve())
    st = agent.st
    if st != None:
        print(st.fetch_toc())
        # pprint(st.tree)

def test_apx():
    from voltron.utils.rfcparser import RFCParser
    agent = RFCParser(Path('./tests/docs/rfc9110.txt').resolve())
    st = agent.st
    logger.debug(st.doc_apx)
