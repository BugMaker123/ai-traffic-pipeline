import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """统一应用日志格式，避免各模块自行输出不可检索的堆栈。"""
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
