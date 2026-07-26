#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
from voltron.rfcparser.standalone import parse_target_section_trees
import click

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option("-t", "--time", type=int, help="fuzzing time (minute)")
@click.option("-c", "--cmdline", type=str, default='auto', help="cmd line to invoke target")
@click.option("-o", "--output", type=str, default='default', help="output path for fuzzing results")
@click.option(
    "--rfc-parser",
    is_flag=True,
    help=(
        "Only parse the target's configured RFC documents into SectionTree "
        "cache files"
    ),
)
@click.option(
    "--spec-knowledge/--no-spec-knowledge",
    default=True,
    show_default=True,
    help="Enable RFC/IR knowledge. Disabled mode requires cached seed generators and parser.",
)
@click.option(
    "--state-learning/--no-state-learning",
    default=True,
    show_default=True,
    help="Enable active Mealy-machine learning before fuzzing.",
)
@click.option(
    "--guided-scheduling/--no-guided-scheduling",
    default=True,
    show_default=True,
    help="Enable state/dependency-guided scheduling and feedback-based energy.",
)
def main(
    sut: str, 
    algorithm: str, 
    time: int | None,
    cmdline: str,
    output: str,
    rfc_parser: bool,
    spec_knowledge: bool,
    state_learning: bool,
    guided_scheduling: bool,
):
    if rfc_parser:
        try:
            results = parse_target_section_trees(sut)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        for result in results:
            click.echo(
                f'{result.rfc_name}: {result.source} -> '
                f'{result.output_path}'
            )
        return

    if time is None:
        raise click.UsageError(
            'Missing option "-t" / "--time" for fuzzing mode.'
        )
    if cmdline == 'auto':
        with open(configs.base_path / 'config' / 'subjects' / sut / 'run.sh', 'r') as f:
            cmdline = f.read()
    fuzzer = Fuzzer(
        target_name=sut,
        cmdline=cmdline.split(' '),
        output=output,
        spec_knowledge=spec_knowledge,
        state_learning=state_learning,
        guided_scheduling=guided_scheduling,
    )
    fuzzer.fuzz(
        algo=algorithm,
        time_limit_min=time
    )

if __name__ == '__main__':
    main()
