"""Parse raw email headers into a structured dict.
This intentionally keeps things simple (line-based parsing) but handles common multi-line headers.
"""
import re
from email import policy
from email.parser import Parser


def parse_email_header(header_text: str) -> dict:
    """Return a dict of important header fields and full Received headers list."""
    # Use Python's email parser for robustness
    msg = Parser(policy=policy.default).parsestr(header_text)

    parsed = {
        'From': msg.get('From'),
        'To': msg.get('To'),
        'Subject': msg.get('Subject'),
        'Date': msg.get('Date'),
        'Message-ID': msg.get('Message-ID'),
        'Return-Path': msg.get('Return-Path'),
        'Authentication-Results': msg.get_all('Authentication-Results', []) or [],
        'Received': msg.get_all('Received', []) or []
    }

    return parsed


def extract_ips_from_received(received_headers):
    """Extract IPv4 addresses from Received headers (returns unique list)."""
    ips = []
    pattern = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
    for header in received_headers:
        found = pattern.findall(header)
        for ip in found:
            if ip not in ips:
                ips.append(ip)
    return ips
