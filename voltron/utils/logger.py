import logging
from logging.handlers import RotatingFileHandler
from logging import Logger
import os

def get_logger(
        mode, 
        name = ""
):
    """ Create logger

    Args: 
        name: name of logger

    returns:
        created logger
    """
    logger = logging.getLogger(name)
    if logger.handlers:  
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # create logs file
    log_dir = ".logs"
    log_file = None
    mode = 'a'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    if name == 'debug':
        mode = 'w'
        log_file = os.path.join(log_dir, "debug.log")
    else:
        log_file = os.path.join(log_dir, "app.log")

    # console logger
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)

    # file logger
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,
        backupCount=10,
        encoding="utf-8",
        mode = mode
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_fmt)

    # add handler
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = get_logger(mode = 'w', name= 'debug')