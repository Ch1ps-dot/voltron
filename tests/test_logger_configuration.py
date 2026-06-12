from logging.handlers import RotatingFileHandler

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
