import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from src.parser import parse_email_header
from src.analyzer import analyze_header


def test_analyze_phishing_sample(monkeypatch):
    text = Path('sample_headers/phishing_sample.txt').read_text(encoding='utf-8')
    parsed = parse_email_header(text)

    # Mock reverse DNS to avoid network calls
    monkeypatch.setattr('src.analyzer._reverse_dns', lambda ip: 'mail.paypa1.com')

    # Run analysis without a geoip db path (should skip GeoIP)
    analysis = analyze_header(parsed, geoip_db_path=None)

    assert '185.45.12.34' in analysis['extracted_ips']
    # auth lines should show SPF fail
    assert 'SPF' in analysis['auth'] and 'fail' in analysis['auth']['SPF'].lower()
    # RDNS mapping should contain our mocked value
    assert analysis['rdns'].get('185.45.12.34') == 'mail.paypa1.com'
    # GeoIP is optional and should be empty when db not provided
    assert analysis['geoip'] == {}
