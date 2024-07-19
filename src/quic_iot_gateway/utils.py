import logging
import colorlog


def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Create a handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)

    # Define the log colors
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'white',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }

    # Define secondary log colors
    secondary_log_colors = {
        'message': {
            'DEBUG': 'cyan',
            'INFO': 'white',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    }

    # Create a formatter
    formatter = colorlog.ColoredFormatter(
        "%(green)s%(asctime)s.%(msecs)03d%(white)s | "
        "%(log_color)s%(levelname)-8s%(white)s | "
        "%(cyan)s%(module)s:%(funcName)s:%(lineno)d%(white)s - "
        "%(log_color)s%(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors=log_colors,
        secondary_log_colors=secondary_log_colors,
        style='%'
    )

    # Add the formatter to the handler
    handler.setFormatter(formatter)

    # Add the handler to the logger
    if not logger.handlers:  # Avoid adding multiple handlers to the same logger
        logger.addHandler(handler)

    return logger
