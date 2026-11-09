"""Per-user Windows installer for the bundled Mini Cursor executable."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from shell_runner import HIDDEN


def install_files(destination):
    destination.mkdir(parents=True, exist_ok=True)
    payload = Path(sys._MEIPASS) / "MiniCursor.exe"
    application = destination / "MiniCursor.exe"
    staged = destination / "MiniCursor.installing"
    try:
        shutil.copyfile(payload, staged)
        staged.replace(application)
    finally:
        staged.unlink(missing_ok=True)
    return application


def shortcut(application, label):
    env = dict(os.environ, MINI_CURSOR_EXE=str(application), MINI_CURSOR_LABEL=label)
    script = (
        "$dir = [Environment]::GetFolderPath('Programs'); "
        "$shell = New-Object -ComObject WScript.Shell; "
        "$item = $shell.CreateShortcut((Join-Path $dir ($env:MINI_CURSOR_LABEL + '.lnk'))); "
        "$item.TargetPath = $env:MINI_CURSOR_EXE; "
        "$item.WorkingDirectory = Split-Path -Parent $env:MINI_CURSOR_EXE; "
        "$item.Save()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, creationflags=HIDDEN, check=True, timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.verify:
        install_files(args.verify)
        return
    version = Path(sys.executable).stem.removeprefix("MiniCursor-Setup-").removesuffix("-x64")
    destination = Path(os.environ["LOCALAPPDATA"]) / "Programs" / f"MiniCursor-{version}"
    root = tk.Tk()
    root.title(f"Mini Cursor {version} 安装")
    root.geometry("525x245")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="安装 Mini Cursor", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
    ttk.Label(frame, text="应用会安装到当前用户目录，并出现在开始菜单中。",
              font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(12, 4))
    ttk.Label(frame, text=str(destination), wraplength=465).pack(anchor="w")
    status = tk.StringVar(value="准备安装")
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=12)

    def install():
        button.configure(state="disabled")
        status.set("正在复制应用…")
        root.update_idletasks()
        try:
            application = install_files(destination)
            shortcut(application, f"Mini Cursor {version}")
        except (OSError, subprocess.SubprocessError) as error:
            status.set("安装失败")
            messagebox.showerror("安装失败", str(error), parent=root)
            button.configure(state="normal")
            return
        status.set("已安装，可从开始菜单打开")
        def launch():
            subprocess.Popen([str(application)], cwd=destination)
            root.destroy()
        button.configure(text="打开 Mini Cursor", command=launch, state="normal")

    button = ttk.Button(frame, text="安装", command=install)
    button.pack(anchor="e")
    root.mainloop()


if __name__ == "__main__":
    main()
