
from pathlib import Path
from pprint import pprint

from ..voltron.utils.logger import logger

def save_to_file(str):
    f = open( 'test.txt', 'w+')
    f.write(str)
    f.close()

def test_promt():
    from voltron.llm.prompt import Prompter
    pt = Prompter(Path('../prompts').resolve())
    print(pt.msg_input_gen("ftp", "GET", "test")) 

def test_gen():
    from  voltron.llm.chat import Chater
    ct = Chater(Path('../prompts').resolve())
    print(ct.llm_gen_input(pro_name="MQTT", msg_type="publish"))

def test_rfc_summary():
    from voltron.llm.chat import Chater
    from voltron.utils.rag import RFCAgent

    ra= RFCAgent(Path('/docs/rfc959.txt').resolve())
    ct = Chater(Path('../prompts').resolve())

    logger.debug(ct.llm_rfc_summary(rfc_toc= ra.st.doc_toc, rfc_doc = ra.st.doc_content, rfc_num='959', pro_name='ftp'))

def test_message_type():
    from voltron.llm.chat import Chater
    from voltron.utils.rag import RFCAgent

    ra= RFCAgent(Path('/docs/rfc7826.txt').resolve())
    ct = Chater(Path('../prompts').resolve())
    summary = ct.llm_rfc_summary(rfc_toc= ra.st.doc_toc, rfc_doc = ra.st.doc_content, rfc_num='7826', pro_name='rtsp')
    logger.debug(summary)
    if (summary != None):
        logger.debug(ct.llm_query_type(rfc_doc = summary, rfc_num='7826', pro_name='rtsp'))

if __name__ == "__main__":
    test_message_type()