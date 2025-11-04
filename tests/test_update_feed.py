import subprocess
import sys
import json


def test_update_feed_local(tmp_path):
    p = tmp_path / 'localfeed.txt'
    p.write_text('198.51.100.0/24\n')

    # point feeds mapping to this file
    mapping = {'tmpfeed': str(p)}
    feeds_file = tmp_path / 'feeds.json'
    feeds_file.write_text(json.dumps(mapping))

    # call update_blacklists.py --feeds-file feeds.json --feed tmpfeed
    res = subprocess.run([sys.executable, 'update_blacklists.py', '--feeds-file',
                         str(feeds_file), '--feed', 'tmpfeed'], capture_output=True)
    assert res.returncode == 0
    out = res.stdout.decode('utf-8')
    assert 'Updated tmpfeed' in out


def test_list_feeds(tmp_path):
    p = tmp_path / 'localfeed2.txt'
    p.write_text('203.0.113.0/24\n')
    mapping = {'feed2': str(p)}
    feeds_file = tmp_path / 'feeds2.json'
    feeds_file.write_text(json.dumps(mapping))

    res = subprocess.run([sys.executable, 'update_blacklists.py', '--feeds-file',
                         str(feeds_file), '--list-feeds'], capture_output=True)
    assert res.returncode == 0
    out = res.stdout.decode('utf-8')
    assert 'feed2' in out
