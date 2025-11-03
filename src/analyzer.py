"""Core analysis and scoring logic for parsed headers.

Enhancements:
- Reverse DNS (RDNS) lookup for each extracted IP (best-effort).
- Optional GeoIP lookup if `geoip2` and a local database are available. GeoIP is optional
  and will be skipped silently if not configured.
"""
from .parser import extract_ips_from_received
from .blacklists import ip_in_any_blacklist

import socket
import os
from typing import Optional

# geoip2 import is optional; used only if available in the environment and a DB path is set
try:
    import geoip2.database
    _HAS_GEOIP2 = True
except Exception:
    _HAS_GEOIP2 = False


def _reverse_dns(ip: str) -> Optional[str]:
    """Best-effort reverse DNS lookup. Returns hostname or None."""
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return host
    except Exception:
        return None


def _geoip_lookup(ip: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Return GeoIP info if geoip2 is available and db_path exists.

    db_path: path to a local GeoLite2-City.mmdb or similar. If not provided or missing,
    this returns None.
    """
    if not _HAS_GEOIP2:
        return None
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        with geoip2.database.Reader(db_path) as reader:
            resp = reader.city(ip)
            return {
                'country': getattr(resp.country, 'iso_code', None),
                'country_name': getattr(resp.country, 'name', None),
                'city': getattr(resp.city, 'name', None),
                'latitude': getattr(resp.location, 'latitude', None),
                'longitude': getattr(resp.location, 'longitude', None),
            }
    except Exception:
        return None


def analyze_header(parsed_header: dict, geoip_db_path: Optional[str] = None) -> dict:
    """Return an analysis summary including IP hits, auth results, RDNS, GeoIP and score."""
    result = {}
    received = parsed_header.get('Received', [])
    ips = extract_ips_from_received(received)
    result['extracted_ips'] = ips

    # For each IP, check local blacklists
    ip_hits = {}
    rdns_map = {}
    geo_map = {}
    for ip in ips:
        hits = ip_in_any_blacklist(ip)
        if hits:
            ip_hits[ip] = hits

        # RDNS (best-effort)
        rdns = _reverse_dns(ip)
        if rdns:
            rdns_map[ip] = rdns

        # GeoIP (optional)
        geo = _geoip_lookup(ip, geoip_db_path)
        if geo:
            geo_map[ip] = geo

    result['blacklist_hits'] = ip_hits
    result['rdns'] = rdns_map
    result['geoip'] = geo_map

    # Simple authentication checks (from Authentication-Results lines)
    auth_lines = parsed_header.get('Authentication-Results', [])
    auth_summary = {'SPF': 'Not found', 'DKIM': 'Not found', 'DMARC': 'Not found'}
    for line in auth_lines:
        low = line.lower()
        if 'spf=' in low:
            auth_summary['SPF'] = line
        if 'dkim=' in low:
            auth_summary['DKIM'] = line
        if 'dmarc=' in low:
            auth_summary['DMARC'] = line
    result['auth'] = auth_summary

    # Scoring (simple rule-based)
    score = 0
    notes = []

    if any('fail' in str(v).lower() for v in auth_summary.values()):
        score += 40
        notes.append('Authentication failure present (SPF/DKIM/DMARC).')

    if len(ip_hits) > 0:
        score += 40
        notes.append('Sender IP(s) present on one or more blocklists.')

    # Domain mismatch heuristic: simple check comparing From domain to last Received domain
    from_header = parsed_header.get('From') or ''
    from_domain = None
    if '@' in from_header:
        from_domain = from_header.split('@')[-1].strip('>" ')

    last_received = received[-1] if received else ''
    if from_domain and from_domain not in last_received:
        score += 10
        notes.append('Possible domain mismatch between From and Received headers.')

    result['score'] = score
    result['risk'] = 'SAFE' if score < 30 else ('SUSPICIOUS' if score < 70 else 'PHISHING')
    result['notes'] = notes

    return result
