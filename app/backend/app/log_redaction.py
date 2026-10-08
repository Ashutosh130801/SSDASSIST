"""Redact callback credentials and WebSocket JWTs from Uvicorn request logging."""
import logging
import re


class CredentialQueryFilter(logging.Filter):
    def filter(self, record):
        def clean(value):
            if isinstance(value, str):
                return re.sub(r'([?&](?:key|token|pass)=)[^&\s\"\']+', r'\1[REDACTED]', value, flags=re.I)
            return value
        record.msg = clean(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(clean(v) for v in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: clean(v) for k, v in record.args.items()}
        return True


def install():
    for name in ('uvicorn.access', 'uvicorn.error'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, CredentialQueryFilter) for f in logger.filters):
            logger.addFilter(CredentialQueryFilter())
