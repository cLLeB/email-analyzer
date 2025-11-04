# Email Header Analyzer — quickstart

This repository is a CLI-first starter for email-header forensics. It parses headers, extracts IPs, checks local blacklist feeds (CIDR-aware), and produces a simple risk score. Everything runs locally — no external API keys are required.

What's new in this repo
- `tool.py` is the single entrypoint for common tasks (setup, run, update, admin commands).
- `tool.py setup` can now perform an all-in-one bootstrap: create a virtualenv, install deps, download blacklist feeds, and optionally download & extract a GeoIP database.

Requirements
- Python 3.11+ (CI runs on 3.12)
- Internet access if you want the updater to download public blacklist feeds

Optional
- GeoIP enrichment (GeoLite2-City): MaxMind requires a (free) account and a license key to download the official GeoLite2 files. You can also provide a direct download URL.


Quick start for new users (what to expect)

A new user who clones this repository will be able to run the CLI and GUI locally, but there are a few important notes so the first run is smooth:

- The repository HEAD intentionally does NOT include the GeoIP database file (`data/GeoLite2-City.mmdb`) in the working tree. This file is large and is meant to be downloaded by each user (or CI) when needed.
- Historically the GeoIP DB was present in earlier commits. That means a full Git clone (which fetches history) may still transfer the large blob unless you either shallow-clone or we rewrite history to remove the blob.

If you want to avoid downloading any historical large blobs when cloning, use a shallow clone (recommended for quick starts):

```bash
git clone --depth 1 https://github.com/cLLeB/email-analyzer.git
cd email-analyzer
```

After cloning, follow these steps to set up and run the project locally.

Create a virtual environment and bootstrap the project

```bash
# create venv (Windows example in bash)
python -m venv .venv
source .venv/Scripts/activate

# install requirements and perform the project's bootstrap actions
python bootstrap.py
```

One-command setup (optional)
Run a full setup that bootstraps the environment, downloads blacklist feeds, and fetches a GeoIP DB from MaxMind using your license key (or use a direct GeoIP URL):

```bash
# using a MaxMind license key (recommended via env var instead of passing on the CLI):
export MAXMIND_LICENSE_KEY='YOUR_MAXMIND_LICENSE_KEY'
python tool.py setup --download-feeds

# or pass a direct geoip URL (mmdb or tar.gz containing an .mmdb):
python tool.py setup --download-feeds --geoip-url 'https://example.com/GeoLite2-City.mmdb.tar.gz'

# if you only want to create the venv + install deps without downloads:
python tool.py setup
```

Common workflows
- Update all blacklist feeds and rebuild the SQLite cache:

```bash
python tool.py update
```


To enable GeoIP in CI or locally, ensure `geoip2` is installed (it's included in `requirements.txt`). The code will silently skip GeoIP if the library or DB is not present.

Local caching

By default parsed networks are cached to `data/networks.db` (SQLite). The updater validates the cache against feed file mtimes and performs incremental updates where possible. To force re-parse and avoid the on-disk cache, pass `--no-cache` to the analyzer or use `src.blacklists.set_use_cache(False)` programmatically.

Run analysis

```bash
python tool.py run sample_headers/phishing_sample.txt
```

Files of interest

- `src/parser.py` — parse raw headers
- `src/blacklists.py` — feed parsing, CIDR handling, SQLite cache management
- `src/analyzer.py` — scoring, RDNS, optional GeoIP enrichment

Use `tool.py` as the single entrypoint for common tasks. The older scripts still exist but are wrapped by `tool.py` (for debugging or direct invocation): `update_blacklists.py`, `main.py`.

License

MIT — add `LICENSE` if you want to publish.

## MaxMind GeoLite2 — account & license key

This project can optionally enrich IP addresses with GeoIP information using MaxMind's GeoLite2-City database. MaxMind requires a (free) account and a license key to download the official GeoLite2 archives. Follow these steps to obtain a license key and make the project download the DB automatically.

1. Create a MaxMind account
	 - Visit https://www.maxmind.com and sign up for a free account (GeoLite2 is free but requires an account).
	 - Verify your email and log in.

2. Create a license key
	 - In the MaxMind user portal, go to "Account settings" → "License keys" (or similar).
	 - Create a new license key. Copy the key value.

3. Provide the key to this project
	 - Recommended (environment variable): set `MAXMIND_LICENSE_KEY` before running `tool.py setup`.

		 Bash / WSL / Git Bash:
		 ```bash
		 export MAXMIND_LICENSE_KEY='YOUR_LICENSE_KEY'
		 python tool.py setup --download-feeds
		 ```

		 PowerShell (Windows):
		 ```powershell
		 $env:MAXMIND_LICENSE_KEY = 'YOUR_LICENSE_KEY'
		 python tool.py setup --download-feeds
		 ```

	 - Alternative (less secure): pass on the CLI:
		 ```bash
		 python tool.py setup --download-feeds --maxmind-license YOUR_LICENSE_KEY
		 ```

4. What `tool.py setup` does with the key
	 - If `data/GeoLite2-City.mmdb` is missing, the setup will automatically download the GeoLite2 tar.gz from MaxMind using your license key, extract the `.mmdb` file, and save it to the default `data/GeoLite2-City.mmdb` (or the path provided with `--geoip-dest`).
	 - The setup step prints progress and will show a confirmation like `Saved GeoIP DB to data/GeoLite2-City.mmdb` on success.

5. CI usage
	 - Store the key as a secret (e.g., `MAXMIND_LICENSE_KEY`) in GitHub Actions or your CI system.
	 - Expose it to the step that runs setup:

		 ```yaml
		 - name: Setup and download GeoIP
			 env:
				 MAXMIND_LICENSE_KEY: ${{ secrets.MAXMIND_LICENSE_KEY }}
			 run: |
				 python tool.py setup --download-feeds
		 ```

Security notes
 - Never commit the license key to source control. Use environment variables or CI secrets.
 - Command-line flags are visible to other users on the same host (process list); prefer env vars.

Post-setup confirmation
 - After `tool.py setup` finishes with `--download-feeds` and a valid key, verify the file exists:
	 ```bash
	 ls -l data/GeoLite2-City.mmdb
	 ```
 - The setup output will also include an explicit saved message and the bootstrap step prints the analyzer sample run summary.

GUI (minimal)

If you prefer a minimal graphical interface, there's a tiny Tkinter GUI bundled as `gui.py` and accessible via the CLI:

	- Launch from the command line:

```bash
python tool.py gui
```

	- The GUI provides buttons for: Setup (optionally download feeds), Update feeds, Rebuild cache, Run analysis on a selected header file, and display key data paths. Output and progress are shown in a text area.

Notes:
 - The GUI uses your system Python and does not add any heavy UI dependencies (Tkinter is part of the Python standard library on most installations).
 - The GUI is intentionally minimal — it shells out to the same scripts used by the CLI so behavior is consistent.

