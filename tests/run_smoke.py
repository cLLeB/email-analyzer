import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from src.parser import parse_email_header
from src.analyzer import analyze_header


def main():
    text = Path('sample_headers/phishing_sample.txt').read_text(encoding='utf-8')
    parsed = parse_email_header(text)

    # Monkeypatch analyzer's RDNS to keep this offline
    import src.analyzer as analyzer_module
    analyzer_module._reverse_dns = lambda ip: 'mail.paypa1.com'

    analysis = analyze_header(parsed, geoip_db_path=None)

    ok = True
    if '185.45.12.34' not in analysis['extracted_ips']:
        print('ERROR: expected IP not found')
        ok = False

    if not ('SPF' in analysis['auth'] and 'fail' in analysis['auth']['SPF'].lower()):
        print('ERROR: expected SPF fail in auth summary')
        ok = False

    if analysis['rdns'].get('185.45.12.34') != 'mail.paypa1.com':
        print('ERROR: RDNS mock failed')
        ok = False

    if analysis['geoip'] != {}:
        print('ERROR: expected empty geoip map when db not provided')
        ok = False

    if ok:
        print('Smoke test passed')
        return 0
    else:
        print('Smoke test FAILED')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
