import ast
import inspect
import multiprocessing as mp
import traceback
from dataclasses import dataclass


BANNED_IMPORT_ROOTS = {
    'asyncio',
    'http',
    'multiprocessing',
    'os',
    'pathlib',
    'requests',
    'shutil',
    'socket',
    'subprocess',
    'sys',
    'tempfile',
    'urllib.request',
}
BANNED_CALLS = {'__import__', 'compile', 'eval', 'exec', 'open'}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: str = ''


def _static_validation(code: str, function_name: str) -> ValidationResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return ValidationResult(False, f'SyntaxError: syntax_error: {error}')

    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if not functions:
        return ValidationResult(False, f'missing_function: {function_name}')
    if isinstance(functions[0], ast.AsyncFunctionDef):
        return ValidationResult(False, f'wrong_signature: {function_name} must be synchronous')

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [node.module or '']
        else:
            roots = []
        for module_name in roots:
            if any(
                module_name == banned or module_name.startswith(f'{banned}.')
                for banned in BANNED_IMPORT_ROOTS
            ):
                return ValidationResult(False, f'forbidden_import: {module_name}')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BANNED_CALLS:
                return ValidationResult(False, f'forbidden_call: {node.func.id}')
    return ValidationResult(True)


def _validation_worker(
    connection,
    code: str,
    function_name: str,
    contract: str,
    max_output_bytes: int,
    observer_samples: tuple[bytes, ...],
    require_equal_observations: bool,
    runtime_samples: tuple[bytes, ...],
    require_nonempty_samples: bool,
) -> None:
    try:
        namespace: dict = {}
        exec(code, namespace)
        function = namespace.get(function_name)
        if not callable(function):
            raise TypeError(f'{function_name} is missing or not callable')
        signature = inspect.signature(function)

        if contract == 'observer':
            try:
                signature.bind(b'probe')
            except TypeError as error:
                raise TypeError(f'wrong observer signature: {error}') from error
            base_probes = (b'', b'voltron-observer-probe', b'\x00\xff', None)
            probes = (*base_probes, *observer_samples)
            sample_digests = []
            for index, probe in enumerate(probes):
                first = function(probe)
                second = function(probe)
                if not (
                    isinstance(first, str)
                    and len(first) == 64
                    and first == first.lower()
                    and all(char in '0123456789abcdef' for char in first)
                ):
                    raise TypeError('invalid_return_type: observer must return lowercase SHA-256')
                if first != second:
                    raise ValueError('nondeterministic: observer changed for identical input')
                if index >= len(base_probes):
                    sample_digests.append(first)
            if (
                require_equal_observations
                and observer_samples
                and len(set(sample_digests)) != 1
            ):
                raise ValueError(
                    'evolved observer does not unify historical samples'
                )
        elif contract == 'checker':
            try:
                signature.bind(b'probe')
            except TypeError as error:
                raise TypeError(f'wrong checker signature: {error}') from error
            for probe in (
                b'', b'voltron-checker-probe', b'\x00\xff', None,
                *runtime_samples,
            ):
                first = function(probe)
                second = function(probe)
                if not isinstance(first, bool):
                    raise TypeError(
                        'invalid_return_type: checker must return bool'
                    )
                if first != second:
                    raise ValueError(
                        'nondeterministic: checker changed for identical input'
                    )
        elif contract == 'mutator':
            try:
                signature.bind()
            except TypeError as error:
                raise TypeError(f'wrong mutator signature: {error}') from error
            for _ in range(3):
                result = function()
                if not isinstance(result, bytes):
                    raise TypeError('invalid_return_type: mutator must return bytes')
                if not result:
                    raise ValueError('empty_result: mutator returned empty bytes')
                if len(result) > max_output_bytes:
                    raise ValueError(
                        f'output_too_large: {len(result)} > {max_output_bytes}'
                    )
        elif contract == 'generator':
            try:
                signature.bind()
            except TypeError as error:
                raise TypeError(f'wrong generator signature: {error}') from error
            for _ in range(3):
                result = function()
                if not isinstance(result, bytes):
                    raise TypeError('invalid_return_type: generator must return bytes')
                if not result:
                    raise ValueError('empty_result: generator returned empty bytes')
                if len(result) > max_output_bytes:
                    raise ValueError(
                        f'output_too_large: {len(result)} > {max_output_bytes}'
                    )
        elif contract == 'parser':
            try:
                signature.bind(b'probe')
            except TypeError as error:
                raise TypeError(f'wrong parser signature: {error}') from error
            base_probes = (b'', b'voltron-parser-probe', b'\x00\xff')
            for index, probe in enumerate((*base_probes, *runtime_samples)):
                result = function(probe)
                if not isinstance(result, bytes):
                    raise TypeError('invalid_return_type: parser must return bytes')
                if len(result) > max_output_bytes:
                    raise ValueError(
                        f'output_too_large: {len(result)} > {max_output_bytes}'
                    )
                if index > 0 and not result:
                    raise ValueError(
                        'empty_result: parser could not classify a '
                        'non-empty validation sample'
                    )
                if (
                    require_nonempty_samples
                    and index >= len(base_probes)
                    and not result
                ):
                    raise ValueError(
                        'empty_result: parser could not classify runtime sample'
                    )
        else:
            raise ValueError(f'unknown validation contract: {contract}')
        connection.send((True, ''))
    except BaseException as error:
        connection.send((False, f'{type(error).__name__}: {error}\n{traceback.format_exc()}'))
    finally:
        connection.close()


def validate_generated_code(
    code: str,
    function_name: str,
    contract: str,
    timeout_s: float = 2.0,
    max_output_bytes: int = 1024 * 1024,
    observer_samples: tuple[bytes, ...] = (),
    require_equal_observations: bool = False,
    runtime_samples: tuple[bytes, ...] = (),
    require_nonempty_samples: bool = False,
) -> ValidationResult:
    """Validate generated code without executing it in the caller process."""
    static_result = _static_validation(code, function_name)
    if not static_result.ok:
        return static_result

    context = mp.get_context('spawn')
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_validation_worker,
        args=(
            child_connection,
            code,
            function_name,
            contract,
            max_output_bytes,
            observer_samples,
            require_equal_observations,
            runtime_samples,
            require_nonempty_samples,
        ),
        daemon=True,
    )
    try:
        process.start()
        child_connection.close()
        if not parent_connection.poll(timeout_s):
            process.kill()
            process.join(timeout=1)
            return ValidationResult(
                False,
                f'execution_timeout: {function_name} exceeded {timeout_s}s',
            )
        ok, error = parent_connection.recv()
        process.join(timeout=1)
        return ValidationResult(ok, error)
    except BaseException as error:
        if process.is_alive():
            process.kill()
        process.join(timeout=1)
        return ValidationResult(False, f'validation_worker_error: {error}')
    finally:
        parent_connection.close()


RAW_SHA256_OBSERVER = '''import hashlib

def packet_observer(response: bytes) -> str:
    data = response if isinstance(response, bytes) else b""
    return hashlib.sha256(data).hexdigest()
'''
