#!/usr/bin/env python3
"""Minimal Tkinter GUI for common project actions.

Provides buttons for: Setup (bootstrap + optional feed download), Update feeds, Rebuild cache,
Run analysis on a header file, and show data paths. Keeps dependencies minimal (Tkinter only).
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import subprocess
import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent


def _config_path():
    """Return a path to store the config (platform aware)."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        cfgdir = os.path.join(base, 'email-analyzer')
    else:
        base = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
        cfgdir = os.path.join(base, 'email-analyzer')
    os.makedirs(cfgdir, exist_ok=True)
    return os.path.join(cfgdir, 'config.json')


def _save_key_to_file(key: str):
    path = _config_path()
    data = {'maxmind_license': key}
    # write file with restrictive mode where possible
    with open(path, 'w', encoding='utf-8') as f:
        import json
        json.dump(data, f)
    try:
        # try to set restrictive permissions on POSIX
        if hasattr(os, 'chmod') and os.name != 'nt':
            os.chmod(path, 0o600)
    except Exception:
        pass


def _load_key_from_file():
    path = _config_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
            return data.get('maxmind_license')
    except Exception:
        return None


def _run_cmd(cmd, out_widget=None):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            if out_widget:
                out_widget.insert(tk.END, line)
                out_widget.see(tk.END)
        proc.wait()
        return proc.returncode
    except Exception as e:
        if out_widget:
            out_widget.insert(tk.END, f'Error running command: {e}\n')
        return 1


def _run_cmd_and_cleanup(cmd, out_widget=None, cleanup_path=None):
    rc = _run_cmd(cmd, out_widget)
    if cleanup_path:
        try:
            os.remove(cleanup_path)
            if out_widget:
                out_widget.insert(tk.END, f'Removed temporary file: {cleanup_path}\n')
        except Exception:
            pass
    return rc


def _download_and_extract_mmdb(url: str, dest_path: str, out_widget=None):
    """Download tar.gz from url and extract the first .mmdb member to dest_path."""
    import urllib.request
    import tarfile
    import tempfile
    import shutil
    tmpfd, tmpname = tempfile.mkstemp()
    os.close(tmpfd)
    try:
        if out_widget:
            out_widget.insert(tk.END, f'Fetching {url}\n')
            out_widget.see(tk.END)
        urllib.request.urlretrieve(url, tmpname)
        # If tarball, extract mmdb
        if tarfile.is_tarfile(tmpname):
            with tarfile.open(tmpname, 'r:gz') as tf:
                mmdb_members = [m for m in tf.getmembers() if m.name.endswith('.mmdb')]
                if not mmdb_members:
                    raise RuntimeError('No .mmdb file found in archive')
                with tf.extractfile(mmdb_members[0]) as mmdb_file:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with open(dest_path, 'wb') as out_f:
                        shutil.copyfileobj(mmdb_file, out_f)
        else:
            # Not a tarball; move directly
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(tmpname, dest_path)
            tmpname = None
        if out_widget:
            out_widget.insert(tk.END, f'Saved GeoIP DB to {dest_path}\n')
    finally:
        if tmpname and os.path.exists(tmpname):
            try:
                os.remove(tmpname)
            except Exception:
                pass


class EmailAnalyzerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Email Header Analyzer')
        self.geometry('800x600')

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=8)

        btn_setup = tk.Button(top, text='Setup (bootstrap)', command=self.setup)
        btn_setup.pack(side=tk.LEFT, padx=4)

        btn_update = tk.Button(top, text='Update feeds', command=self.update_feeds)
        btn_update.pack(side=tk.LEFT, padx=4)

        btn_rebuild = tk.Button(top, text='Rebuild cache', command=self.rebuild_cache)
        btn_rebuild.pack(side=tk.LEFT, padx=4)

        btn_run = tk.Button(top, text='Run on header...', command=self.run_on_file)
        btn_run.pack(side=tk.LEFT, padx=4)

        btn_paths = tk.Button(top, text='Show data paths', command=self.show_paths)
        btn_paths.pack(side=tk.LEFT, padx=4)
        # MaxMind license input and button
        lbl_key = tk.Label(top, text='MaxMind key:')
        lbl_key.pack(side=tk.LEFT, padx=(12, 2))
        self.key_var = tk.StringVar()
        ent_key = tk.Entry(top, textvariable=self.key_var, width=36)
        ent_key.pack(side=tk.LEFT, padx=(0, 4))
        btn_setup_key = tk.Button(top, text='Setup + GeoIP', command=self.setup_with_key)
        btn_setup_key.pack(side=tk.LEFT, padx=4)

        # Key storage options (radiobuttons)
        self.store_var = tk.StringVar(value='none')
        rb_none = tk.Radiobutton(top, text="Don't save", variable=self.store_var, value='none')
        rb_none.pack(side=tk.LEFT, padx=(8, 2))
        rb_keyring = tk.Radiobutton(top, text='Save to OS keyring', variable=self.store_var, value='keyring')
        rb_keyring.pack(side=tk.LEFT, padx=2)
        rb_file = tk.Radiobutton(top, text='Save to config file', variable=self.store_var, value='file')
        rb_file.pack(side=tk.LEFT, padx=(2, 4))

        btn_load = tk.Button(top, text='Load saved key', command=self.load_saved_key)
        btn_load.pack(side=tk.LEFT, padx=4)

        # Output box
        self.out = tk.Text(self, wrap='none')
        self.out.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        # Paste area for headers (below output area)
        paste_frame = tk.Frame(self)
        paste_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        lbl_paste = tk.Label(paste_frame, text='Paste headers here:')
        lbl_paste.pack(anchor='w')
        self.paste_text = tk.Text(paste_frame, height=8, wrap='none')
        self.paste_text.pack(fill=tk.BOTH, expand=True)
        paste_btn_frame = tk.Frame(paste_frame)
        paste_btn_frame.pack(fill=tk.X)
        btn_paste_run = tk.Button(paste_btn_frame, text='Paste & Run', command=self.paste_and_run)
        btn_paste_run.pack(side=tk.LEFT, padx=4, pady=4)
        btn_clear_paste = tk.Button(paste_btn_frame, text='Clear Paste',
                                    command=lambda: self.paste_text.delete('1.0', tk.END))
        btn_clear_paste.pack(side=tk.LEFT, padx=4, pady=4)

    def _run_in_thread(self, cmd):
        self.out.insert(tk.END, f'> {" ".join(cmd)}\n')
        self.out.see(tk.END)
        t = threading.Thread(target=_run_cmd, args=(cmd, self.out), daemon=True)
        t.start()

    def setup(self):
        # Ask whether to download feeds and/or GeoIP
        if messagebox.askyesno('Download feeds?', 'Download blacklist feeds and rebuild cache as part of setup?'):
            cmd = [sys.executable, str(ROOT / 'tool.py'), 'setup', '--download-feeds']
        else:
            cmd = [sys.executable, str(ROOT / 'tool.py'), 'setup']
        self._run_in_thread(cmd)

    def setup_with_key(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning(
                'Missing key', 'Please paste your MaxMind license key in the field before clicking "Setup + GeoIP".')
            return
        # In-process GeoIP download to avoid putting the key on the command line
        try:
            dest = str(ROOT / 'data' / 'GeoLite2-City.mmdb')
            url = f'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz'
            self.out.insert(tk.END, 'Downloading GeoIP DB in-process (key kept in memory)...\n')
            self.out.see(tk.END)
            # download and extract in background so UI doesn't block
            t = threading.Thread(target=lambda: (_download_and_extract_mmdb(url, dest, self.out)), daemon=True)
            t.start()
        except Exception as e:
            messagebox.showerror('Download error', f'Failed to download GeoIP DB: {e}')
            return
        # After starting download, update feeds and rebuild cache (no key passed on CLI)
        self._run_in_thread([sys.executable, str(ROOT / 'update_blacklists.py'), '--rebuild-cache'])
        # Save key according to user preference
        store = self.store_var.get()
        try:
            if store == 'keyring':
                try:
                    import keyring
                    # service and username are arbitrary but consistent
                    keyring.set_password('email-analyzer', 'maxmind-license', key)
                    self.out.insert(tk.END, 'Saved license key to OS keyring.\n')
                except Exception as e:
                    messagebox.showwarning('Keyring error', f'Failed to save to keyring: {e}. Falling back to file.')
                    _save_key_to_file(key)
                    self.out.insert(tk.END, 'Saved license key to config file as fallback.\n')
            elif store == 'file':
                _save_key_to_file(key)
                self.out.insert(tk.END, 'Saved license key to config file.\n')
        except Exception as e:
            self.out.insert(tk.END, f'Error saving key: {e}\n')

    def update_feeds(self):
        cmd = [sys.executable, str(ROOT / 'tool.py'), 'update']
        self._run_in_thread(cmd)

    def rebuild_cache(self):
        # call update_blacklists.py with --rebuild-cache
        cmd = [sys.executable, str(ROOT / 'update_blacklists.py'), '--rebuild-cache']
        self._run_in_thread(cmd)

    def run_on_file(self):
        path = filedialog.askopenfilename(title='Select email header file', filetypes=[
                                          ('Text files', '*.txt'), ('All files', '*.*')])
        if not path:
            return
        cmd = [sys.executable, str(ROOT / 'tool.py'), 'run', path]
        self._run_in_thread(cmd)

    def show_paths(self):
        data_dir = ROOT / 'data'
        db = data_dir / 'networks.db'
        geo = data_dir / 'GeoLite2-City.mmdb'
        msg = f'Data directory: {data_dir}\nNetworks DB: {db}\nGeoIP DB: {geo}\n'
        self.out.insert(tk.END, msg)
        self.out.see(tk.END)

    def paste_and_run(self):
        text = self.paste_text.get('1.0', tk.END).strip()
        if not text:
            messagebox.showwarning('No headers', 'Paste some headers into the box before clicking Paste & Run.')
            return
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            messagebox.showerror('Write error', f'Failed to write temp file: {e}')
            return
        cmd = [sys.executable, str(ROOT / 'tool.py'), 'run', path]
        # Run and remove temp file afterwards
        t = threading.Thread(target=_run_cmd_and_cleanup, args=(cmd, self.out, path), daemon=True)
        t.start()

    def load_saved_key(self):
        # Try keyring first, then file
        try:
            try:
                import keyring
                k = keyring.get_password('email-analyzer', 'maxmind-license')
                if k:
                    self.key_var.set(k)
                    self.out.insert(tk.END, 'Loaded license key from OS keyring.\n')
                    return
            except Exception:
                pass
            # Fallback to file
            k = _load_key_from_file()
            if k:
                self.key_var.set(k)
                self.out.insert(tk.END, 'Loaded license key from config file.\n')
                return
            messagebox.showinfo('No saved key', 'No saved key found in OS keyring or config file.')
        except Exception as e:
            messagebox.showwarning('Load error', f'Error loading saved key: {e}')


def main():
    root = EmailAnalyzerGUI()
    root.mainloop()


if __name__ == '__main__':
    main()
