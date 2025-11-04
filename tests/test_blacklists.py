from src import blacklists
from pathlib import Path

import sys
sys.path.insert(0, str(Path.cwd()))


def write_feed(file_path, lines):
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def test_exact_ip_match(tmp_path, monkeypatch):
    feed = tmp_path / 'feed1.txt'
    write_feed(feed, ['203.0.113.10'])

    monkeypatch.setattr(blacklists, 'BLACKLIST_FEEDS', {'testfeed': str(feed)})
    # Ensure cache cleared
    blacklists._NETWORK_CACHE.clear()

    hits = blacklists.ip_in_any_blacklist('203.0.113.10')
    assert 'testfeed' in hits


def test_ip_within_cidr(tmp_path, monkeypatch):
    feed = tmp_path / 'feed2.txt'
    write_feed(feed, ['198.51.100.0/24'])

    monkeypatch.setattr(blacklists, 'BLACKLIST_FEEDS', {'testfeed2': str(feed)})
    blacklists._NETWORK_CACHE.clear()

    # IP inside /24
    hits = blacklists.ip_in_any_blacklist('198.51.100.42')
    assert 'testfeed2' in hits


def test_ip_not_in_list(tmp_path, monkeypatch):
    feed = tmp_path / 'feed3.txt'
    write_feed(feed, ['192.0.2.0/28'])

    monkeypatch.setattr(blacklists, 'BLACKLIST_FEEDS', {'testfeed3': str(feed)})
    blacklists._NETWORK_CACHE.clear()

    hits = blacklists.ip_in_any_blacklist('192.0.2.100')
    assert hits == []


def test_ipv6_cidr_match(tmp_path, monkeypatch):
    feed = tmp_path / 'feed_ipv6.txt'
    # example IPv6 /64 network
    with open(feed, 'w', encoding='utf-8') as f:
        f.write('2001:db8:abcd:0012::/64\n')

    monkeypatch.setattr(blacklists, 'BLACKLIST_FEEDS', {'ipv6feed': str(feed)})
    blacklists._NETWORK_CACHE.clear()

    hits = blacklists.ip_in_any_blacklist('2001:db8:abcd:12::1')
    assert 'ipv6feed' in hits


def test_set_data_dir(tmp_path):
    # create a custom feeds dir
    custom_dir = tmp_path / 'feedsdir'
    custom_dir.mkdir()
    # write a feed file matching an IP
    fpath = custom_dir / 'customfeed.txt'
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('203.0.113.99\n')

    # point blacklist module to this dir
    blacklists.set_data_dir(str(custom_dir))
    blacklists.BLACKLIST_FEEDS = {'customfeed': 'customfeed.txt'}
    blacklists._NETWORK_CACHE.clear()

    hits = blacklists.ip_in_any_blacklist('203.0.113.99')
    assert 'customfeed' in hits
