import logging
from logging.handlers import RotatingFileHandler
import os

def get_logger(name="voltron"):
    """获取配置好的日志器（单例模式，避免重复配置）"""
    logger = logging.getLogger(name)
    if logger.handlers:  
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 确保日志目录存在
    log_dir = ".logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, "app.log")

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)

    # 文件处理器（按大小轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_fmt)

    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

# 全局日志实例（其他模块直接导入）
logger = get_logger()