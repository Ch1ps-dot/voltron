#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
from voltron.rfcparser.standalone import (
    generate_target_ir,
    parse_target_section_trees,
)
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
    "--generate-ir",
    is_flag=True,
    help=(
        "Only parse the target's protocol specifications and generate its IR"
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
    generate_ir: bool,
    spec_knowledge: bool,
    state_learning: bool,
    guided_scheduling: bool,
):
    if rfc_parser and generate_ir:
        raise click.UsageError(
            "--rfc-parser and --generate-ir cannot be used together."
        )

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

    if generate_ir:
        try:
            ir_path = generate_target_ir(sut)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"IR generated for {sut} -> {ir_path}")
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
    exit_code = fuzzer.fuzz(
        algo=algorithm,
        time_limit_min=time
    )
    if exit_code:
        raise click.exceptions.Exit(exit_code)

if __name__ == '__main__':
    main()
