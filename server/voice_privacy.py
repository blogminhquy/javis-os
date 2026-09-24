"""Keep spoken TTS text out of the application's default HTTP access log."""
import logging


class VoiceAccessFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn access records: client, method, path with query, HTTP version, status.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, target, version, status = record.args
            if isinstance(target, str) and target.partition('?')[0] == '/tts':
                record.args = (client, method, '/tts', version, status)
        return True


def install():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, VoiceAccessFilter) for f in logger.filters):
        logger.addFilter(VoiceAccessFilter())
