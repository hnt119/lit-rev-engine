"""Windows per-user uninstall helper, executed from NSIS's temporary runtime.

Only registered, hash-bound application payload files are eligible. Unexpected
or modified files survive. Research/model/profile roots are never cleanup roots.
"""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

PRODUCT='org.hnt119.litrev.desktop'
KEY=r'Software\hnt119\LiteratureReviewEngineDesktop'
MAX_MANIFEST=16*1024*1024


def no_links(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        try:info=item.lstat()
        except FileNotFoundError:continue
        if item.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('Application paths must not use symlinks or reparse points.')
    return path


def validate_root(root, expected):
    root=no_links(root);expected=no_links(expected)
    if os.path.normcase(os.path.abspath(root))!=os.path.normcase(os.path.abspath(expected)):
        raise ValueError('The uninstaller is not in its registered per-user application directory.')
    return Path(os.path.abspath(root))


def plan_version(root,version,expected_manifest):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,119}',version) or not re.fullmatch('[a-f0-9]{64}',expected_manifest):
        raise ValueError('Invalid installed-version registry binding.')
    directory=no_links(root/('app-'+version));manifest_path=no_links(directory/'INSTALLATION.json')
    if manifest_path.stat().st_size>MAX_MANIFEST:raise ValueError('Installed manifest exceeds its bound.')
    raw=manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_manifest:raise ValueError('Installed application manifest changed; nothing was removed.')
    value=json.loads(raw)
    if value.get('schema')!='litrev.desktop.installed-files.v1' or value.get('app_id')!=PRODUCT or value.get('version')!=version:
        raise ValueError('The installed payload is not this product/version.')
    if not re.fullmatch('[a-f0-9]{40}',value.get('source_commit','')) or not isinstance(value.get('files'),dict):
        raise ValueError('The installed source/file binding is invalid.')
    eligible=[];preserved=[]
    for relative,record in value['files'].items():
        parsed=PurePosixPath(relative)
        if parsed.is_absolute() or '..' in parsed.parts or parsed.as_posix()!=relative or '\\' in relative or ':' in relative or not parsed.parts or any(part.endswith(('.', ' ')) for part in parsed.parts) or any(ch in relative for ch in '\x00\r\n'):
            raise ValueError('Unsafe installed manifest member.')
        if set(record)!={'bytes','sha256'} or type(record['bytes']) is not int or record['bytes']<0 or not re.fullmatch('[a-f0-9]{64}',record['sha256']):raise ValueError('Invalid installed file digest.')
        file=no_links(directory/relative)
        if not file.exists():continue
        if not file.is_file():raise ValueError('Installed member changed file type.')
        if file.stat().st_size==record['bytes'] and hashlib.sha256(file.read_bytes()).hexdigest()==record['sha256']:
            eligible.append((file,record))
        else:preserved.append(file)
    return directory,manifest_path,eligible,preserved


def windows_closed(directory):
    """A process image or active backend lock must not be in use; never kill."""
    if os.name!='nt':raise RuntimeError('Native Windows check is unavailable.')
    api=ctypes.windll.kernel32
    api.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    api.CreateFileW.restype=ctypes.c_void_p
    targets=[directory/'LiteratureReviewEngine.exe',directory/'resources/python/python.exe']
    data=Path(os.environ['LOCALAPPDATA'])/'LiteratureReviewEngineDesktop/engine/.desktop-backend.lock'
    targets.append(data)
    for path in targets:
        no_links(path)
        if not path.exists():continue
        handle=api.CreateFileW(str(path),0x80000000|0x40000000,0,None,3,0x00200000,None)
        if handle in (None,ctypes.c_void_p(-1).value):raise RuntimeError('Quit the installed application before removal; no process was stopped.')
        api.CloseHandle(ctypes.c_void_p(handle))


def remove_plans(plans):
    removed=0;preserved=0
    for directory,manifest,eligible,changed in plans:
        owned_dirs={directory}
        for file in [*(entry[0] for entry in eligible),*changed]:
            parent=file.parent
            while parent!=directory:
                owned_dirs.add(parent);parent=parent.parent
        for file,record in eligible:
            try:
                no_links(file)
                if not file.is_file() or file.stat().st_size!=record['bytes'] or hashlib.sha256(file.read_bytes()).hexdigest()!=record['sha256']:continue
                file.unlink();removed+=1
            except (FileNotFoundError,ValueError):pass
            except OSError:pass
        # Remove only empty directories named by the original manifest.
        for d in sorted(owned_dirs-{directory},key=lambda p:len(p.parts),reverse=True):
            try:d.rmdir()
            except OSError:pass
        remaining=[p for p in directory.rglob('*') if p!=manifest]
        preserved+=len(remaining)
        if not remaining:manifest.unlink(missing_ok=True)
        try:directory.rmdir()
        except OSError:pass
    return {'removed_files':removed,'preserved_modified_or_unexpected_entries':preserved}


def main():
    if os.name!='nt':raise RuntimeError('This helper is only for installed Windows applications.')
    import winreg
    expected=Path(os.environ['LOCALAPPDATA'])/'Programs/Literature Review Engine'
    root=validate_root(sys.argv[1],expected)
    access=winreg.KEY_READ|winreg.KEY_WOW64_64KEY
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY,0,access) as key:
        registered=winreg.QueryValueEx(key,'InstallRoot')[0]
    validate_root(root,registered)
    entries=[]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY+r'\Versions',0,access) as versions:
        index=0
        while True:
            try:version,checksum,_=winreg.EnumValue(versions,index)
            except OSError as error:
                if getattr(error,'winerror',None)==259:break
                raise
            entries.append((version,checksum));index+=1
    if not entries or len(entries)>50:raise ValueError('Installed version inventory is missing or exceeds its bound.')
    plans=[plan_version(root,version,checksum) for version,checksum in entries]
    for directory,*_ in plans:windows_closed(directory)
    print(json.dumps(remove_plans(plans)))

if __name__=='__main__':
    try:main()
    except Exception:
        print('Uninstall validation failed; existing data was preserved.',file=sys.stderr)
        raise SystemExit(1)
