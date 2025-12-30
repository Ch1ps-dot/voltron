from pathlib import Path



stype=''
host='127.0.0.1'
port='2200'
pro_name:str
rfc_name:str # TODO: this fields is useless
pre_script:Path = Path.cwd() / 'tests' / 'bin' / 'lightftp' / 'run.sh'
post_script:Path = Path.cwd() / 'tests' / 'bin' / 'lightftp' / 'fftpclean.sh'
pmp_path:Path = Path.cwd() / 'prompts'
doc_path:Path = Path.cwd() / 'rfcs'
script_path:Path = Path.cwd()