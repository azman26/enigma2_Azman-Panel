"""Bounds for data entering bouquet files and Enigma2's native EPG cache."""
import json
import re

MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def read_json(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError('EPG response too large')
    result = json.loads(raw.decode('utf-8'))
    if not isinstance(result, dict):
        raise ValueError('Invalid EPG response')
    return result


def valid_reference(reference):
    return isinstance(reference, str) and re.fullmatch(r'[0-9A-Fa-f]{1,8}(?::[0-9A-Fa-f]{1,8}){8}', reference) is not None
