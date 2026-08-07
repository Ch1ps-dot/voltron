from voltron.synthesizer.code_validation import validate_generated_code


def test_observer_validation_accepts_deterministic_sha256():
    code = '''import hashlib
def packet_observer(response: bytes) -> str:
    return hashlib.sha256(response if isinstance(response, bytes) else b"").hexdigest()
'''
    assert validate_generated_code(
        code, 'packet_observer', 'observer', timeout_s=1
    ).ok


def test_observer_validation_rejects_missing_function_and_side_effects():
    missing = validate_generated_code(
        'def wrong(_response): return "x"',
        'packet_observer',
        'observer',
    )
    forbidden = validate_generated_code(
        'import socket\ndef packet_observer(response): return "0" * 64',
        'packet_observer',
        'observer',
    )
    assert missing.error.startswith('missing_function:')
    assert forbidden.error.startswith('forbidden_import:')


def test_mutator_validation_isolates_timeout_and_output_contract():
    timeout = validate_generated_code(
        'def mutate():\n    while True:\n        pass\n',
        'mutate',
        'mutator',
        timeout_s=0.2,
    )
    oversized = validate_generated_code(
        'def mutate():\n    return b"A" * 20\n',
        'mutate',
        'mutator',
        timeout_s=1,
        max_output_bytes=10,
    )
    assert timeout.error.startswith('execution_timeout:')
    assert 'output_too_large:' in oversized.error


def test_checker_validation_isolates_timeout_and_requires_boolean():
    timeout = validate_generated_code(
        'def packet_checker(response):\n    while True:\n        pass\n',
        'packet_checker',
        'checker',
        timeout_s=0.2,
    )
    wrong_type = validate_generated_code(
        'def packet_checker(response):\n    return "yes"\n',
        'packet_checker',
        'checker',
        timeout_s=1,
    )
    valid = validate_generated_code(
        'def packet_checker(response):\n    return isinstance(response, bytes)\n',
        'packet_checker',
        'checker',
        timeout_s=1,
    )

    assert timeout.error.startswith('execution_timeout:')
    assert 'checker must return bool' in wrong_type.error
    assert valid.ok


def test_parser_base_probes_may_be_unclassified():
    parser = '''def packet_parser(response: bytes) -> bytes:
    if response.startswith(b"220"):
        return b"220"
    return b""
'''
    assert validate_generated_code(
        parser,
        'packet_parser',
        'parser',
        timeout_s=1,
    ).ok


def test_parser_requires_nonempty_only_for_explicit_runtime_samples():
    parser = '''def packet_parser(response: bytes) -> bytes:
    if response.startswith(b"220"):
        return b"220"
    return b""
'''
    valid = validate_generated_code(
        parser,
        'packet_parser',
        'parser',
        timeout_s=1,
        runtime_samples=(b'220 service ready\r\n',),
        require_nonempty_samples=True,
    )
    invalid = validate_generated_code(
        parser,
        'packet_parser',
        'parser',
        timeout_s=1,
        runtime_samples=(b'unclassified real response',),
        require_nonempty_samples=True,
    )
    permissive = validate_generated_code(
        parser,
        'packet_parser',
        'parser',
        timeout_s=1,
        runtime_samples=(b'unclassified real response',),
        require_nonempty_samples=False,
    )

    assert valid.ok
    assert 'could not classify runtime sample' in invalid.error
    assert permissive.ok


def test_observer_evolution_validation_requires_samples_to_converge():
    distinct = '''import hashlib
def packet_observer(response: bytes) -> str:
    data = response if isinstance(response, bytes) else b""
    return hashlib.sha256(data).hexdigest()
'''
    unified = '''import hashlib
def packet_observer(response: bytes) -> str:
    return hashlib.sha256(b"stable").hexdigest()
'''
    options = {
        'observer_samples': (b'first', b'second'),
        'require_equal_observations': True,
        'timeout_s': 1,
    }
    failed = validate_generated_code(
        distinct, 'packet_observer', 'observer', **options
    )
    passed = validate_generated_code(
        unified, 'packet_observer', 'observer', **options
    )

    assert 'does not unify historical samples' in failed.error
    assert passed.ok
