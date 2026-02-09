#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
import click, random

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option("-t", "--time", type=str, required=True, help="fuzzing time (minute)")
@click.option("-c", "--cmdline", type=str, default='auto', help="fuzzing time (minute)")
def main(
    sut: str, 
    algorithm: str, 
    time: str, 
    cmdline: str
):
    supported_sut = {'lightftp','pureftpd','kamailio', 'live555', 'exim', 'lighthttpd'}
    if sut in supported_sut:
        if cmdline == 'auto':
            with open(configs.base_path / 'input' / 'scripts' / sut / 'run.txt', 'r') as f:
                cmdline = f.read()
        fuzzer = Fuzzer(
            target_name=sut,
            cmdline=cmdline.split(' ')
        )
        fuzzer.fuzz(
            algo=algorithm,
            time_limit_min=int(time)
        )
    else:
        print('Unkown Target')

if __name__ == '__main__':
    main()