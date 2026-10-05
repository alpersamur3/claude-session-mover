"""Render the application's own demo windows (Windows + Pillow, development only).

No real account roots are scanned. Fixtures are copied to a temporary directory;
only windows created by this process are captured. CLI images render actual output.
"""
import builtins
import contextlib
import ctypes
from ctypes import wintypes as w
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.argv = [str(ROOT / 'csmui.py'), '--demo', '--en']
from PIL import Image, ImageDraw, ImageFont
import csm
import csmui
import csbridge
import cspack
import i18n


def capture_own_window(app, path):
    user, gdi = ctypes.WinDLL('user32'), ctypes.WinDLL('gdi32')
    user.GetAncestor.argtypes, user.GetAncestor.restype = [w.HWND, w.UINT], w.HWND
    user.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user.GetDC.argtypes, user.GetDC.restype = [w.HWND], w.HDC
    user.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [w.HDC], w.HDC
    gdi.CreateCompatibleBitmap.argtypes, gdi.CreateCompatibleBitmap.restype = [w.HDC, ctypes.c_int, ctypes.c_int], w.HBITMAP
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [w.HDC, w.HANDLE], w.HANDLE
    gdi.DeleteObject.argtypes = [w.HANDLE]
    gdi.DeleteDC.argtypes = [w.HDC]
    gdi.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT]
    hwnd = user.GetAncestor(app.winfo_id(), 2)
    rect = w.RECT()
    user.GetClientRect(hwnd, ctypes.byref(rect))
    width, height = rect.right, rect.bottom
    dc = user.GetDC(hwnd)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    old = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(hwnd, memory, 3):
            raise RuntimeError('PrintWindow failed for demo window')
        gdi.SelectObject(memory, old)
        class Header(ctypes.Structure):
            _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG),
                        ('planes', w.WORD), ('bits', w.WORD), ('compression', w.DWORD),
                        ('image_size', w.DWORD), ('x', w.LONG), ('y', w.LONG),
                        ('used', w.DWORD), ('important', w.DWORD)]
        header = Header(40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0) != height:
            raise RuntimeError('Could not read demo bitmap')
        Image.frombytes('RGB', (width, height), buffer.raw, 'raw', 'BGRX').save(path)
    finally:
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd, dc)


def cli_image(lang, demo):
    csm.tr = i18n.Translator(lang)
    output = io.StringIO()
    choices = iter(['1'])
    def answer(prompt):
        print(prompt, end='')
        try:
            value = next(choices)
        except StopIteration:
            raise EOFError
        print(value)
        return value
    with contextlib.redirect_stdout(output):
        old = builtins.input
        builtins.input = answer
        try:
            csm.main()
        except SystemExit as ex:
            if ex.code not in (0, None):
                raise
        finally:
            builtins.input = old
    text = output.getvalue().replace(str(demo / 'sample-data'), 'sample-data')
    lines = []
    for line in text.splitlines():
        lines.extend(textwrap.wrap(line, 108, replace_whitespace=False) or [''])
    font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 18)
    symbols = ImageFont.truetype('C:/Windows/Fonts/seguisym.ttf', 18)
    emoji = ImageFont.truetype('C:/Windows/Fonts/seguiemj.ttf', 18)
    image = Image.new('RGB', (1220, 72 + len(lines) * 25), '#111827')
    draw = ImageDraw.Draw(image)
    draw.text((25, 16), 'Claude Session Mover | CLI demo | ' + lang.upper(), font=font, fill='#93c5fd')
    for n, line in enumerate(lines):
        x = 25
        for char in line:
            chosen = emoji if ord(char) > 0xffff else symbols if ord(char) >= 0x2000 else font
            draw.text((x, 55 + n * 25), char, font=chosen, fill='#e5e7eb')
            x += font.getlength(' ') if chosen is font else max(font.getlength(' '), chosen.getlength(char))
    image.save(ROOT / 'docs' / ('cli-' + lang + '.png'))


def main():
    if sys.platform != 'win32':
        raise SystemExit('Screenshot generation requires Windows')
    ctypes.WinDLL('user32').SetProcessDPIAware()
    import tkinter as tk
    with tempfile.TemporaryDirectory(prefix='csm-docs-') as folder:
        demo = Path(folder)
        shutil.copytree(ROOT / 'sample-data', demo / 'sample-data')
        for path in (demo / 'sample-data').rglob('*'):
            if path.suffix not in ('.json', '.jsonl'):
                continue
            stamp = path.stat()
            data = path.read_text(encoding='utf-8')
            # Replace fixture-specific personal paths with neutral example paths.
            data = data.replace('C:\\\\Users\\\\alper\\\\Desktop', 'C:\\\\Projects')
            path.write_text(data, encoding='utf-8')
            os.utime(path, (stamp.st_atime, stamp.st_mtime))
        csm.SCRIPT_DIR = demo
        csm.IS_DEMO = True
        cspack.claude_temp_root = lambda: demo / 'scratch'
        (ROOT / 'docs').mkdir(exist_ok=True)
        original = tk.Tk.mainloop
        for lang in ('en', 'tr'):
            sys.argv = [str(ROOT / 'csmui.py'), '--demo', '--' + lang]
            csm.tr = i18n.Translator(lang)
            def render(app, _n=0):
                try:
                    app.geometry('1440x960+30+30')
                    app.update()
                    for pane in app.panes.values():
                        pane.stores_var.set('sample-data\\' + csm.STORE_NAMES[pane.kind])
                    app.bridge.paths_var.set(app.tr.t('g_br_paths', c='sample-data/projects', x='sample-data/codex/sessions'))
                    panes = [('gui', app.panes['code']), ('cowork', app.panes['cowork']),
                             ('bridge', app.bridge), ('pack', app.pack_pane)]
                    assert len(app.nb.tabs()) == 4
                    for name, pane in panes:
                        app.nb.select(pane)
                        children = pane.tree.get_children()
                        assert children, name + ' demo list is empty'
                        pane.tree.selection_set(children[0])
                        pane.tree.focus(children[0])
                        pane.on_select()
                        app.update()
                        if hasattr(pane, 'preview_frame'):
                            pane.preview_frame.master.sashpos(0, 800 if name != 'bridge' else 930)
                        if hasattr(pane, 'detail_var'):
                            pane.detail_var.set(pane.detail_var.get().replace(str(demo / 'sample-data'), 'sample-data'))
                            app.update_idletasks()
                        # Give the window's native controls a paint cycle before capture.
                        app.after(150, app.quit)
                        original(app)
                        capture_own_window(app, ROOT / 'docs' / (name + '-' + lang + '.png'))
                        print('Rendered', name, lang)
                finally:
                    app.destroy()
            tk.Tk.mainloop = render
            try:
                csmui.run_gui()
            finally:
                tk.Tk.mainloop = original
            cli_image(lang, demo)


if __name__ == '__main__':
    main()
