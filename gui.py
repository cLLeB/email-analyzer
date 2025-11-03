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

        # Output box
        self.out = tk.Text(self, wrap='none')
        self.out.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

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

    def update_feeds(self):
        cmd = [sys.executable, str(ROOT / 'tool.py'), 'update']
        self._run_in_thread(cmd)

    def rebuild_cache(self):
        # call update_blacklists.py with --rebuild-cache
        cmd = [sys.executable, str(ROOT / 'update_blacklists.py'), '--rebuild-cache']
        self._run_in_thread(cmd)

    def run_on_file(self):
        path = filedialog.askopenfilename(title='Select email header file', filetypes=[('Text files', '*.txt'), ('All files', '*.*')])
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


def main():
    root = EmailAnalyzerGUI()
    root.mainloop()


if __name__ == '__main__':
    main()
