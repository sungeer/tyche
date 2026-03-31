import logging.config
from datetime import date

from src.core import settings

log_dir = settings.base_dir / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)


def setup_logger():
    today = date.today().isoformat()  # '2026-02-03'

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,

        'formatters': {
            'standard': {
                'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s'
            },
        },

        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'standard',
            },
            'red_area': {
                'class': 'logging.FileHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'filename': str(log_dir / f'red_area.{today}.log'),
                'encoding': 'utf-8',
            },
            'to_pdf': {
                'class': 'logging.FileHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'filename': str(log_dir / f'to_pdf.{today}.log'),
                'encoding': 'utf-8',
            },
        },

        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },

        'loggers': {
            'red_area': {
                'handlers': ['console', 'red_area'],
                'level': 'INFO',
                'propagate': False,
            },
            'to_pdf': {
                'handlers': ['console', 'to_pdf'],
                'level': 'INFO',
                'propagate': False,
            },
        },
    }

    logging.config.dictConfig(logging_config)
