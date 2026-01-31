#!/bin/python3

from voltron.fuzz import Fuzzer
import click, random
    
def test_lightftp():
    fuzzer = Fuzzer(
        target_name='lightftp',
        time_limit_min=10
    )
    fuzzer.fuzz(
        algo='state'
    )
    
def test_pureftpd():
    fuzzer = Fuzzer(
        target_name='pureftpd',
        time_limit_min=1440
    )
    fuzzer.fuzz(
        algo='state'
    )
    
def test_kamailio():
    fuzzer = Fuzzer(
        target_name='kamailio',
        time_limit_min=1440
    )
    fuzzer.fuzz(
        algo='state'
    )
    
def test_live555():
    fuzzer = Fuzzer(
        target_name='live555',
        time_limit_min=1440
    )
    fuzzer.fuzz(
        algo='state'
    )

@click.command(help='fuzzer')
@click.option("-t", "--target", type=str, required=True, help="fuzzing target")
def main(target):
    supported_set = {'lightftp','pureftpd','kamailio', 'live555'}
    if target in supported_set:
        fuzzer = Fuzzer(
            target_name=target,
            time_limit_min=1440
        )
        fuzzer.fuzz(
            algo='state'
        )
    else:
        print('Unkown Target')

if __name__ == '__main__':
    main()