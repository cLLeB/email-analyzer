import argparse
from rich import print
from src.parser import parse_email_header
from src.blacklists import ensure_feeds
from src.blacklists import set_data_dir, set_use_cache
from src.blacklists import set_blacklist_feeds_from_file
from src.analyzer import analyze_header
import os


def pretty_print_result(parsed, analysis):
    print('\n[bold underline]Header Summary[/bold underline]')
    print(f"From: {parsed.get('From')}")
    print(f"Subject: {parsed.get('Subject')}")
    print(f"Date: {parsed.get('Date')}")

    print('\n[bold underline]Analysis[/bold underline]')
    print(f"Risk: [bold]{analysis['risk']}[/bold]")
    print(f"Score: {analysis['score']} / 100")
    if analysis['notes']:
        print('\nNotes:')
        for n in analysis['notes']:
            print(f" - {n}")

    if analysis['blacklist_hits']:
        print('\n[red]Blacklist Hits:[/red]')
        for ip, feeds in analysis['blacklist_hits'].items():
            print(f" - {ip} -> {', '.join(feeds)}")
    else:
        print('\n[green]No blacklist hits found.[/green]')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Email header analyzer')
    parser.add_argument('header_file', help='Path to raw header text file')
    parser.add_argument('--geoip-db', help='Path to GeoIP mmdb file (optional)', default=None)
    parser.add_argument('--no-update', help='Skip updating blacklist feeds at startup', action='store_true')
    parser.add_argument('--feeds-dir', help='Path to feeds directory to override data/', default=None)
    parser.add_argument('--no-cache', help='Disable on-disk parsed-network cache', action='store_true')
    parser.add_argument(
        '--feeds-file', help='Path to JSON or simple feeds file to override built-in feeds', default=None)
    args = parser.parse_args()

    header_file = args.header_file

    # Optionally override feeds dir
    if args.feeds_dir:
        set_data_dir(args.feeds_dir)

    if args.feeds_file:
        ok = set_blacklist_feeds_from_file(args.feeds_file)
        if not ok:
            print(f"[yellow]Warning:[/yellow] failed to load feeds from {args.feeds_file}; using defaults.")

    # cache control
    if args.no_cache:
        set_use_cache(False)

    # Optionally update feeds
    if not args.no_update:
        ensure_feeds()

    with open(header_file, 'r', encoding='utf-8') as f:
        header_text = f.read()

    # Warn if geoip db path provided but missing
    geoip_db = args.geoip_db
    if geoip_db and not os.path.exists(geoip_db):
        print(f"[yellow]Warning:[/yellow] GeoIP DB not found at {geoip_db}; GeoIP lookup will be skipped.")
        geoip_db = None

    parsed = parse_email_header(header_text)
    analysis = analyze_header(parsed, geoip_db_path=geoip_db)

    pretty_print_result(parsed, analysis)
