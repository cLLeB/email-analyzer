"""Download and cache public blocklist feeds (no API required).
Stores files under `data/` and maintains a small metadata JSON with timestamps.
"""
import os
import json
from datetime import datetime, timedelta
import requests
import ipaddress
from typing import List
import pickle
import sqlite3
import time
import json
from urllib.parse import urlparse, unquote
from urllib.request import url2pathname

# Toggle to control whether cache is used
_USE_CACHE = True

# DATA_DIR is relative to repo root: move up from this file's directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

METADATA_FILE = os.path.join(DATA_DIR, '.cache_metadata.json')


def set_data_dir(path: str):
    """Override the directory where feeds and metadata are stored.

    Use this to point the blacklist system at a custom directory (useful for tests
    or enterprise setups). This updates DATA_DIR and METADATA_FILE module globals
    and creates the directory if needed.
    """
    global DATA_DIR, METADATA_FILE
    DATA_DIR = path
    os.makedirs(DATA_DIR, exist_ok=True)
    METADATA_FILE = os.path.join(DATA_DIR, '.cache_metadata.json')


def set_use_cache(val: bool):
    """Enable or disable using the on-disk cache."""
    global _USE_CACHE
    _USE_CACHE = bool(val)


def _cache_file_path():
    return os.path.join(DATA_DIR, 'networks.db')


def _db_connect():
    path = _cache_file_path()
    conn = sqlite3.connect(path)
    return conn


def _init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS networks (
        feed TEXT,
        cidr TEXT,
        start BLOB,
        end BLOB,
        version INTEGER,
        last_updated REAL
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_networks_ver_start ON networks (version, start)')
    conn.commit()


def _ip_to_bytes(ip_obj: ipaddress._BaseAddress) -> bytes:
    # ipaddress objects have .packed which is big-endian bytes (4 or 16 bytes)
    return ip_obj.packed


def _network_bounds_bytes(net: ipaddress._BaseNetwork):
    return net.network_address.packed, net.broadcast_address.packed


def _read_meta_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute('SELECT key, value FROM meta')
    rows = cur.fetchall()
    return {k: v for k, v in rows}


def _write_meta_db(conn: sqlite3.Connection, meta: dict):
    cur = conn.cursor()
    for k, v in meta.items():
        cur.execute('REPLACE INTO meta (key, value) VALUES (?, ?)', (k, v))
    conn.commit()


def set_blacklist_feeds_from_file(path: str):
    """Load a feeds mapping from a JSON file or simple whitespace-separated lines.

    JSON format: {"name": "url_or_path", ...}
    Plain text format: each line `name url_or_path`
    """
    global BLACKLIST_FEEDS
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read().strip()
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    BLACKLIST_FEEDS = data
                    return True
            except Exception:
                # parse simple lines
                mapping = {}
                for line in raw.splitlines():
                    s = line.strip()
                    if not s or s.startswith('#'):
                        continue
                    parts = s.split()
                    if len(parts) >= 2:
                        mapping[parts[0]] = parts[1]
                if mapping:
                    BLACKLIST_FEEDS = mapping
                    return True
    except Exception:
        return False
    return False


def _rebuild_cache(feed_files: dict, feed_mtimes: dict):
    """Rebuild the SQLite networks DB from given feed_files mapping (name->path).

    feed_files: mapping of feed name to local file path.
    feed_mtimes: mapping of feed name to mtime used to store in meta.
    """
    db_path = _cache_file_path()
    # remove old DB if exists
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass

    conn = _db_connect()
    _init_db(conn)
    cur = conn.cursor()

    # Insert networks
    for name, file_path in feed_files.items():
        nets = _load_networks_from_file(file_path)
        for net in nets:
            start_b, end_b = _network_bounds_bytes(net)
            version = 6 if net.version == 6 else 4
            cur.execute('INSERT INTO networks (feed, cidr, start, end, version, last_updated) VALUES (?, ?, ?, ?, ?, ?)',
                        (name, str(net), start_b, end_b, version, time.time()))

    # write meta data (store feed_mtimes as JSON string)
    meta = {'feed_mtimes': json.dumps(feed_mtimes), 'cache_version': '1'}
    _write_meta_db(conn, meta)
    conn.commit()
    conn.close()


def rebuild_cache():
    """Public: rebuild cache using current BLACKLIST_FEEDS mapping and data dir.

    This will download nothing — it rebuilds based on whatever local feed files exist
    (typically those under DATA_DIR or local paths in BLACKLIST_FEEDS).
    """
    # build feed_files and feed_mtimes
    feed_mtimes = {}
    feed_files = {}
    for name, feed_val in BLACKLIST_FEEDS.items():
        if isinstance(feed_val, str) and os.path.exists(feed_val):
            file_path = feed_val
        else:
            file_path = os.path.join(DATA_DIR, f"{name}.txt")
        feed_files[name] = file_path
        try:
            feed_mtimes[name] = os.path.getmtime(file_path)
        except Exception:
            feed_mtimes[name] = 0

    _rebuild_cache(feed_files, feed_mtimes)

# Public, no-auth feeds (text files)
BLACKLIST_FEEDS = {
    'spamhaus_drop': 'https://www.spamhaus.org/drop/drop.txt',
    'spamhaus_edrop': 'https://www.spamhaus.org/drop/edrop.txt',
    'firehol_level1': 'https://iplists.firehol.org/files/firehol_level1.netset',
    'blocklist_de_all': 'https://lists.blocklist.de/lists/all.txt',
    # Local test feed (contains 203.0.113.5 for verification)
    'local_test': os.path.join(DATA_DIR, 'mytest.txt')
}

DEFAULT_REFRESH_MINUTES = 60  # feeds older than this will be refreshed by updater

# In-memory cache of parsed networks to avoid reparsing files repeatedly
_NETWORK_CACHE = {}


def _read_meta():
    try:
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _write_meta(meta):
    with open(METADATA_FILE, 'w') as f:
        json.dump(meta, f, indent=2)


def needs_refresh(feed_name: str, threshold_minutes: int = DEFAULT_REFRESH_MINUTES) -> bool:
    meta = _read_meta()
    ts = meta.get(feed_name)
    if not ts:
        return True
    then = datetime.fromisoformat(ts)
    return (datetime.utcnow() - then) > timedelta(minutes=threshold_minutes)


def update_feed(feed_name: str, url: str) -> bool:
    """Download feed and save it locally. Returns True on success."""
    file_path = os.path.join(DATA_DIR, f"{feed_name}.txt")
    try:
        # Support local file paths and file:// URIs in addition to HTTP(S) URLs
        data_text = None
        # Handle file:// URIs robustly (including Windows paths) and direct local paths
        if isinstance(url, str):
            parsed = urlparse(url)
            scheme = (parsed.scheme or '').lower()
            if scheme == 'file':
                # turn file URI into local path, handling percent-encoding and Windows drive letters
                local_path = url2pathname(unquote(parsed.path))
                # On Windows, urlparse for file://C:/... may place drive in path or netloc
                if parsed.netloc and not local_path:
                    # netloc may contain drive letter
                    local_path = url2pathname(unquote(parsed.netloc + parsed.path))
                local_path = os.path.expanduser(local_path)
                local_path = os.path.abspath(local_path)
                if os.path.exists(local_path):
                    with open(local_path, 'r', encoding='utf-8') as lf:
                        data_text = lf.read()
                else:
                    raise FileNotFoundError(local_path)
            elif scheme in ('http', 'https'):
                # HTTP(S) URL
                r = requests.get(url, timeout=20)
                r.raise_for_status()
                data_text = r.text
            else:
                # No scheme or other scheme: treat as local path if exists, otherwise try HTTP fetch
                local_candidate = os.path.abspath(os.path.expanduser(url))
                if os.path.exists(local_candidate):
                    with open(local_candidate, 'r', encoding='utf-8') as lf:
                        data_text = lf.read()
                else:
                    # Fallback: try HTTP(S) fetch
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()
                    data_text = r.text
        else:
            # Non-string URL (unlikely) — try requests
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            data_text = r.text

        # Save raw text to local cache file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data_text)
        meta = _read_meta()
        meta[feed_name] = datetime.utcnow().isoformat()
        _write_meta(meta)
        # If cache is enabled, incrementally update DB for this feed
        try:
            if _USE_CACHE:
                # compute mtime
                try:
                    mtime = os.path.getmtime(file_path)
                except Exception:
                    mtime = 0
                _update_db_for_feed(feed_name, file_path, mtime)
        except Exception:
            # don't fail update if DB update fails
            pass
        return True
    except Exception as e:
        print(f"Failed to update {feed_name}: {e}")
        return False


def _update_db_for_feed(feed_name: str, file_path: str, mtime: float):
    """Incrementally update the networks DB for a single feed.

    Deletes existing rows for the feed and inserts parsed networks.
    Also updates the meta feed_mtimes entry.
    """
    conn = _db_connect()
    _init_db(conn)
    cur = conn.cursor()
    # delete existing rows for this feed
    cur.execute('DELETE FROM networks WHERE feed=?', (feed_name,))

    nets = _load_networks_from_file(file_path)
    for net in nets:
        start_b, end_b = _network_bounds_bytes(net)
        version = 6 if net.version == 6 else 4
        cur.execute('INSERT INTO networks (feed, cidr, start, end, version, last_updated) VALUES (?, ?, ?, ?, ?, ?)',
                    (feed_name, str(net), start_b, end_b, version, time.time()))

    # update meta feed_mtimes
    meta = _read_meta_db(conn)
    stored = meta.get('feed_mtimes')
    try:
        stored_mtimes = json.loads(stored) if stored else {}
    except Exception:
        stored_mtimes = {}
    stored_mtimes[feed_name] = mtime
    _write_meta_db(conn, {'feed_mtimes': json.dumps(stored_mtimes)})
    conn.commit()
    conn.close()


def ensure_feeds(refresh_threshold_minutes: int = DEFAULT_REFRESH_MINUTES):
    """Ensure all feeds exist and are refreshed if older than threshold."""
    for name, url in BLACKLIST_FEEDS.items():
        if needs_refresh(name, refresh_threshold_minutes):
            print(f"Updating feed: {name}")
            update_feed(name, url)
    # Invalidate network cache after potential updates
    _NETWORK_CACHE.clear()


def _load_networks_from_file(file_path: str) -> List[ipaddress._BaseNetwork]:
    nets = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Strip whitespace and common inline comment markers
                raw = line.strip()
                if not raw:
                    continue
                # Remove comments after #, ; or // if present
                for marker in ('#', ';', '//'):
                    if marker in raw:
                        raw = raw.split(marker, 1)[0].strip()
                if not raw:
                    continue

                # Some feeds include extra tokens; take the first token that looks like an IP/CIDR
                parts = raw.split()
                token = None
                for p in parts:
                    p = p.strip().strip('"\'')
                    if p:
                        token = p
                        break
                if not token:
                    continue

                # Normalize token and try parsing as a network. ipaddress handles IPv4/IPv6
                try:
                    if '/' in token:
                        net = ipaddress.ip_network(token, strict=False)
                    else:
                        # single IP -> /32 or /128
                        # ip_network will infer correct version
                        net = ipaddress.ip_network(token + '/32') if ':' not in token else ipaddress.ip_network(token + '/128')
                    nets.append(net)
                except Exception:
                    # ignore unparseable lines
                    continue
    except FileNotFoundError:
        pass
    return nets


def ip_in_any_blacklist(ip: str) -> list:
    """Check if IP appears in any cached blacklist files (CIDR-aware).

    Returns list of feed names where the IP was found.
    """
    hits = []
    try:
        ip_obj = ipaddress.ip_address(ip)
    except Exception:
        return hits

    # Determine feed file paths and mtimes
    feed_mtimes = {}
    feed_files = {}
    for name, feed_val in BLACKLIST_FEEDS.items():
        if isinstance(feed_val, str) and os.path.exists(feed_val):
            file_path = feed_val
        else:
            file_path = os.path.join(DATA_DIR, f"{name}.txt")
        feed_files[name] = file_path
        try:
            feed_mtimes[name] = os.path.getmtime(file_path)
        except Exception:
            feed_mtimes[name] = 0

    # If cache is enabled, prefer SQLite DB for fast lookups
    if _USE_CACHE:
        db_path = _cache_file_path()
        # If DB doesn't exist or feed mtimes changed, rebuild cache (best-effort)
        rebuild_needed = False
        if not os.path.exists(db_path):
            rebuild_needed = True
        else:
            try:
                conn = _db_connect()
                meta = _read_meta_db(conn)
                stored = meta.get('feed_mtimes')
                if stored:
                    try:
                        stored_mtimes = json.loads(stored)
                    except Exception:
                        stored_mtimes = {}
                else:
                    stored_mtimes = {}
                if stored_mtimes != feed_mtimes:
                    rebuild_needed = True
                conn.close()
            except Exception:
                rebuild_needed = True

        if rebuild_needed:
            try:
                _rebuild_cache(feed_files, feed_mtimes)
            except Exception:
                # fallback to parsing if rebuild fails
                pass

        # Query DB for the IP
        try:
            conn = _db_connect()
            cur = conn.cursor()
            version = 6 if ip_obj.version == 6 else 4
            ip_packed = ip_obj.packed
            # SQLite supports blob comparisons
            cur.execute('SELECT DISTINCT feed FROM networks WHERE version=? AND start<=? AND end>=?', (version, ip_packed, ip_packed))
            rows = cur.fetchall()
            conn.close()
            for r in rows:
                hits.append(r[0])
            # return early when using DB
            return hits
        except Exception:
            # fallback to in-memory parsing if DB query fails
            pass

    # Fallback: parse files into in-memory networks (no on-disk cache)
    for name, file_path in feed_files.items():
        nets = _load_networks_from_file(file_path)
        for net in nets:
            if ip_obj in net:
                hits.append(name)
                break

    return hits
