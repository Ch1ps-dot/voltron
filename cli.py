#!/bin/python3

from voltron.fuzz import Fuzzer
import click, random

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option("-t", "--time", type=str, required=True, help="fuzzing time (minute)")
@click.option("-c", "--cmdline", type=str, required=True, help="fuzzing time (minute)")
def main(
    sut, 
    algorithm, 
    time, 
    cmdline: str
):
    supported_sut = {'lightftp','pureftpd','kamailio', 'live555', 'exim'}
    if sut in supported_sut:
        fuzzer = Fuzzer(
            target_name=sut,
            cmdline=cmdline.split(' ')
        )
        fuzzer.fuzz(
            algo=algorithm,
            time_limit_min=time
        )
    else:
        print('Unkown Target')

if __name__ == '__main__':
    main()