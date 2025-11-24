from voltron.utils.rag import RAGRfc
import os
from pathlib import Path
from pprint import pprint

def test_db_query():
    agent = RAGRfc(Path('./test/docs/rfc959.txt').resolve())
    ans = agent.db_query('QUIT')
    pprint(ans)

if __name__ == "__main__":
    test_db_query()