"""Utility to force-update all blacklist feeds (run manually or via cron).

Supports optional cache rebuild (--rebuild-cache) which will rebuild the
local SQLite cache from the downloaded feed files.
"""
import argparse
import os
from src.blacklists import ensure_feeds, rebuild_cache
from src.blacklists import set_blacklist_feeds_from_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rebuild-cache', action='store_true', help='Rebuild the local cache after updating feeds')
    parser.add_argument('--no-download', action='store_true',
                        help='Skip downloading feeds; rebuild uses existing local files')
    parser.add_argument('--feeds-file', help='Path to feeds mapping file (JSON or simple lines)', default=None)
    parser.add_argument('--stats', action='store_true', help='Print stats (count of CIDRs) per feed from the cache DB')
    parser.add_argument(
        '--feed', help='Name of a single feed to update (only this feed will be downloaded/updated)', default=None)
    parser.add_argument('--list-feeds', action='store_true', help='List feed names and resolved local paths/URLs')
    args = parser.parse_args()

    # Optionally load feeds mapping from file
    if args.feeds_file:
        ok = set_blacklist_feeds_from_file(args.feeds_file)
        if not ok:
            print(f'Failed to load feeds from {args.feeds_file}; continuing with defaults')

    # list feeds mapping and resolved paths
    if args.list_feeds:
        from src.blacklists import BLACKLIST_FEEDS
        print('\nFeed\tPath/URL')
        print('-------------------------')
        for name, val in BLACKLIST_FEEDS.items():
            # resolve to absolute local path if exists
            path = val
            if isinstance(val, str) and os.path.exists(val):
                path = os.path.abspath(val)
            else:
                # check data dir fallback path
                fallback = os.path.join('data', f"{name}.txt")
                if os.path.exists(fallback):
                    path = os.path.abspath(fallback)
            print(f"{name}\t{path}")
        return

    # Stats mode: print counts per feed from DB and exit
    if args.stats:
        from src.blacklists import _cache_file_path
        import sqlite3
        db = _cache_file_path()
        if not os.path.exists(db):
            print('No cache DB found at', db)
            return
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute('SELECT feed, COUNT(*) FROM networks GROUP BY feed')
        rows = cur.fetchall()
        print('\nFeed\tCIDRs')
        print('-------------------')
        for feed, cnt in rows:
            print(f"{feed}\t{cnt}")
        conn.close()
        return

    if not args.no_download:
        if args.feed:
            # Update only the named feed
            feed_name = args.feed
            url = None
            try:
                url = __import__('src.blacklists', fromlist=['BLACKLIST_FEEDS']).BLACKLIST_FEEDS.get(feed_name)
            except Exception:
                url = None
            if not url:
                print(f'Feed {feed_name} not found in BLACKLIST_FEEDS mapping')
            else:
                from src.blacklists import update_feed
                print(f'Updating single feed: {feed_name}')
                ok = update_feed(feed_name, url)
                print(f'Updated {feed_name}:', ok)
        else:
            # Force refresh regardless of threshold by passing 0
            ensure_feeds(refresh_threshold_minutes=0)
            print('Blacklist feeds updated.')

    if args.rebuild_cache:
        print('Rebuilding blacklist cache...')
        rebuild_cache()
        print('Cache rebuild complete.')


if __name__ == '__main__':
    main()
