#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tek dosyalık .exe üretir (build.py)  /  Builds the standalone .exe files
=======================================================================
Python kurulu olmayan bir Windows bilgisayarda çalışan iki dosya üretir:

    dist/ClaudeSessionMover.exe   grafik arayüz  / GUI   (csmui.py)
    dist/csm.exe                  terminal       / CLI   (csm.py)

Kullanım / Usage:
    py -m pip install -U pyinstaller
    py build.py                  (ikisini de derler / builds both)
    py build.py gui              (yalnızca arayüz / GUI only)
    py build.py cli              (yalnızca terminal / CLI only)

NOT: PyInstaller 6.16 ve öncesi bu projede BOZUK exe üretiyor (üretilen dosyada
SizeOfImage alanı eksik kalıyor, Windows "geçerli bir uygulama değil" diyor).
Bu yüzden en az 6.22 gerekir; betik sürümü kontrol eder ve ürettiği dosyayı
GetBinaryType ile doğrular.
"""

import os
import subprocess
import sys
from pathlib import Path

MIN_PYINSTALLER = (6, 22)
HERE = Path(__file__).resolve().parent
TARGETS = {
    "gui": {"name": "ClaudeSessionMover", "script": "csmui.py", "windowed": True,
            "hidden": ("csm", "csbridge", "cspack", "i18n"), "exclude": ()},
    # Terminal sürümü arayüzü kullanmaz; tkinter'ı dışarıda bırakıp küçültüyoruz.
    "cli": {"name": "csm", "script": "csm.py", "windowed": False,
            "hidden": ("csbridge", "cspack", "i18n"), "exclude": ("tkinter", "csmui")},
}


def check_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller kurulu değil / not installed:  py -m pip install -U pyinstaller")
    ver = tuple(int(x) for x in PyInstaller.__version__.split(".")[:2])
    if ver < MIN_PYINSTALLER:
        sys.exit(f"PyInstaller {PyInstaller.__version__} bozuk exe üretiyor / produces broken exes; "
                 f"en az {'.'.join(map(str, MIN_PYINSTALLER))} gerekli:  py -m pip install -U pyinstaller")
    return PyInstaller.__version__


def verify(exe: Path) -> str:
    """Windows'ta dosyanın gerçekten çalıştırılabilir olduğunu doğrular."""
    if not exe.is_file():
        return "üretilemedi / missing"
    if sys.platform != "win32":
        return "ok"
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetBinaryTypeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.GetBinaryTypeW.restype = wintypes.BOOL
    kind = wintypes.DWORD()
    if not k.GetBinaryTypeW(str(exe), ctypes.byref(kind)):
        return "GEÇERSİZ / INVALID (GetBinaryType)"
    return "ok"


def build(key: str) -> Path:
    t = TARGETS[key]
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
           "--windowed" if t["windowed"] else "--console",
           "--name", t["name"],
           "--add-data", f"sample-data{sep}sample-data"]
    for mod in t["hidden"]:
        cmd += ["--hidden-import", mod]
    for mod in t["exclude"]:
        cmd += ["--exclude-module", mod]
    cmd.append(t["script"])
    print(f"\n=== {t['name']} ({t['script']}) ===")
    subprocess.run(cmd, cwd=HERE, check=True)
    return HERE / "dist" / (t["name"] + (".exe" if os.name == "nt" else ""))


def main():
    print("PyInstaller", check_pyinstaller())
    keys = [a for a in sys.argv[1:] if a in TARGETS] or list(TARGETS)
    built = [(build(k), TARGETS[k]["name"]) for k in keys]
    print("\n--- sonuç / result ---")
    bad = False
    for exe, name in built:
        state = verify(exe)
        size = f"{exe.stat().st_size / 1048576:.1f} MB" if exe.is_file() else "-"
        print(f"  {name:22} {size:>9}   {state}   {exe}")
        bad |= state != "ok"
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
