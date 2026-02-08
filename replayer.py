#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
import click, random
from pathlib import Path

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-d", "--dir", type=str, required=True, help="testcase input direcotory")
@click.option("-f", "--cov_file", type=str, required=True, help="input direcotory")
def main(
    sut: str, 
    dir: str, 
    cov_folder: str
):
    supported_sut = {'lightftp','pureftpd','kamailio', 'live555', 'exim'}
    if sut in supported_sut:
        cmdline = ''
        with open(configs.base_path / 'input' / 'scripts' / sut / 'run.txt', 'r') as f:
            cmdline = f.read()
        replayer = Fuzzer(
            target_name=sut,
            cmdline=cmdline.split(' ')
        )
        replayer.replay(
            res_dir=Path(dir),
            cov_folder=Path(cov_folder)
        )
    else:
        print('Unkown Target')

if __name__ == '__main__':
    main()