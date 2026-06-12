import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


_FILE_HANDLER_MARKER = '_voltron_file_handler'


def get_logger(name: str = '') -> logging.Logger:
    """Create a logger without opening a file during module import."""
    logger = logging.getLogger(name)
    if any(
        getattr(handler, '_voltron_console_handler', False)
        for handler in logger.handlers
    ):
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler._voltron_console_handler = True
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))
    logger.addHandler(console_handler)
    return logger


def configure_file_logging(
    results_path: Path,
    mode: str = 'w',
) -> None:
    """Attach rotating file handlers once the run result directory is known."""
    results_path.mkdir(parents=True, exist_ok=True)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - '
        '%(process)d:%(threadName)s - %(module)s:%(lineno)d - %(message)s'
    )

    for logger in (logger_fuzz, logger_llm):
        log_path = (results_path / f'{logger.name}.log').resolve()
        existing_handler = next(
            (
                handler
                for handler in logger.handlers
                if (
                    getattr(handler, _FILE_HANDLER_MARKER, False)
                    and Path(handler.baseFilename).resolve() == log_path
                )
            ),
            None,
        )
        if existing_handler is not None:
            continue

        for handler in list(logger.handlers):
            if getattr(handler, _FILE_HANDLER_MARKER, False):
                logger.removeHandler(handler)
                handler.close()

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=10,
            encoding='utf-8',
            mode=mode,
            delay=True,
        )
        setattr(file_handler, _FILE_HANDLER_MARKER, True)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)


logger_fuzz = get_logger(name='fuzz')
logger_llm = get_logger(name='llm')
