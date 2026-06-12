from logging.handlers import RotatingFileHandler
import logging

from voltron.utils import logger as logger_module


def test_logger_creation_does_not_open_a_file(tmp_path):
    logger = logger_module.get_logger('voltron-test-import')

    assert not any(
        isinstance(handler, RotatingFileHandler)
        for handler in logger.handlers
    )
    assert list(tmp_path.iterdir()) == []


def test_configured_logs_are_delayed_and_written_to_results(tmp_path):
    logger_module.configure_file_logging(tmp_path)

    assert not (tmp_path / 'fuzz.log').exists()
    assert not (tmp_path / 'llm.log').exists()

    logger_module.logger_fuzz.debug('fuzz detail')
    logger_module.logger_llm.debug('llm detail')

    assert 'fuzz detail' in (
        tmp_path / 'fuzz.log'
    ).read_text(encoding='utf-8')
    assert 'llm detail' in (
        tmp_path / 'llm.log'
    ).read_text(encoding='utf-8')


def test_reconfiguration_moves_future_logs_to_new_results(tmp_path):
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    logger_module.configure_file_logging(first)
    logger_module.logger_fuzz.debug('first run')

    logger_module.configure_file_logging(second)
    logger_module.logger_fuzz.debug('second run')

    assert 'first run' in (first / 'fuzz.log').read_text(encoding='utf-8')
    assert 'second run' not in (first / 'fuzz.log').read_text(
        encoding='utf-8'
    )
    assert 'second run' in (second / 'fuzz.log').read_text(encoding='utf-8')


def test_reconfiguration_to_same_results_does_not_truncate(tmp_path):
    logger_module.configure_file_logging(tmp_path)
    logger_module.logger_fuzz.debug('before reconfigure')

    logger_module.configure_file_logging(tmp_path)
    logger_module.logger_fuzz.debug('after reconfigure')

    content = (tmp_path / 'fuzz.log').read_text(encoding='utf-8')
    assert 'before reconfigure' in content
    assert 'after reconfigure' in content


def test_exception_records_traceback(tmp_path):
    logger_module.configure_file_logging(tmp_path)
    try:
        raise RuntimeError('context failure')
    except RuntimeError:
        logger_module.logger_fuzz.exception('operation failed')

    content = (tmp_path / 'fuzz.log').read_text(encoding='utf-8')
    assert 'operation failed' in content
    assert 'Traceback (most recent call last)' in content
    assert 'RuntimeError: context failure' in content


def test_file_log_uses_aligned_structured_columns(tmp_path):
    logger_module.configure_file_logging(tmp_path)
    logger_module.logger_fuzz.debug(
        logger_module.format_event(
            'checker.reject',
            response_type='500',
            length=12,
        )
    )

    line = (tmp_path / 'fuzz.log').read_text(
        encoding='utf-8'
    ).splitlines()[-1]
    assert ' | DEBUG    | fuzz ' in line
    assert 'pid=' in line
    assert 'thread=' in line
    assert '[CHECKER.REJECT]' in line
    assert "response_type='500'" in line


def test_multiline_log_content_is_indented():
    formatter = logger_module.ReadableFormatter(
        '%(levelname)s | %(message)s'
    )
    record = logging.LogRecord(
        name='test',
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg='header\nbody\nlast',
        args=(),
        exc_info=None,
    )

    assert formatter.format(record) == (
        'DEBUG | header\n'
        '    | body\n'
        '    | last'
    )
