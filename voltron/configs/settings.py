from pathlib import Path

base_url='https://xiaoai.plus/v1'
api_key='sk-3aNTqYiVNoiOsKXJMUsfmpTEEIdVbS4YXrHhheHRYTsNbMD9'
model="gpt-4o"

stype=''
host=''
port=''
pro_name:str
rfc_name:str # TODO: this fields is useless
sut_path:Path = Path.cwd()
pmp_path:Path = Path.cwd() / 'prompts'
doc_path:Path = Path.cwd() / 'tests' / 'docs'
script_path:Path = Path.cwd()