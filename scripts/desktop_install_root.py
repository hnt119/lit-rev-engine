"""Stdlib-only Windows installer preflight, run from bundled temporary Python.

This verifies the fixed per-user application root before NSIS extracts executable
code there. It never accepts the research data root or repairs a foreign ACL.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as w
import os
import re
from pathlib import Path
import sys

WRITE_MASK=0x500D0156  # generic write/all, delete, DAC/owner and file write bits
TRUSTED_SYSTEM={'S-1-5-18','S-1-5-32-544'}


def validate_acl(owner, current, entries):
    if owner!=current:raise ValueError('The application directory must be owned by the current user.')
    for principal,mask,inherit_only in entries:
        if not inherit_only and mask&WRITE_MASK and principal not in {current,*TRUSTED_SYSTEM}:
            raise ValueError('An application ancestor permits another principal to write.')


def canonical_root(argument,local):
    expected=Path(local)/'Programs'/'Literature Review Engine'
    if not Path(local).is_absolute() or str(local).startswith('\\\\') or os.path.normcase(os.path.abspath(argument))!=os.path.normcase(os.path.abspath(expected)):
        raise ValueError('Only the fixed per-user Programs application directory is accepted.')
    return expected


class Native:
    def __init__(self):
        self.a=ctypes.WinDLL('advapi32',use_last_error=True);self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.a.GetNamedSecurityInfoW.argtypes=[w.LPWSTR,w.DWORD,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p)];self.a.GetNamedSecurityInfoW.restype=w.DWORD
        self.a.ConvertSidToStringSidW.argtypes=[ctypes.c_void_p,ctypes.POINTER(w.LPWSTR)];self.a.ConvertSidToStringSidW.restype=w.BOOL
        self.a.GetAce.argtypes=[ctypes.c_void_p,w.DWORD,ctypes.POINTER(ctypes.c_void_p)];self.a.GetAce.restype=w.BOOL
        self.a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)];self.a.OpenProcessToken.restype=w.BOOL
        self.k.GetCurrentProcess.restype=w.HANDLE;self.k.LocalFree.argtypes=[ctypes.c_void_p];self.k.LocalFree.restype=ctypes.c_void_p
        self.a.GetTokenInformation.argtypes=[w.HANDLE,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)];self.a.GetTokenInformation.restype=w.BOOL
        self.k.CloseHandle.argtypes=[w.HANDLE];self.k.CloseHandle.restype=w.BOOL
        self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(w.DWORD)];self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype=w.BOOL
        self.k.CreateDirectoryW.argtypes=[w.LPCWSTR,ctypes.c_void_p];self.k.CreateDirectoryW.restype=w.BOOL
        self.a.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.c_void_p];self.a.SetFileSecurityW.restype=w.BOOL
    def sid(self,pointer):
        text=w.LPWSTR()
        if not self.a.ConvertSidToStringSidW(pointer,ctypes.byref(text)):raise ctypes.WinError(ctypes.get_last_error())
        try:return text.value
        finally:self.k.LocalFree(text)
    def current(self):
        token=w.HANDLE()
        if not self.a.OpenProcessToken(self.k.GetCurrentProcess(),8,ctypes.byref(token)):raise ctypes.WinError(ctypes.get_last_error())
        try:
            size=w.DWORD();self.a.GetTokenInformation(token,1,None,0,ctypes.byref(size));buffer=ctypes.create_string_buffer(size.value)
            if not self.a.GetTokenInformation(token,1,buffer,size,ctypes.byref(size)):raise ctypes.WinError(ctypes.get_last_error())
            return self.sid(ctypes.c_void_p.from_buffer(buffer).value)
        finally:self.k.CloseHandle(token)
    def inspect(self,path):
        info=path.lstat()
        if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400 or not path.is_dir():raise ValueError('Application ancestors must be ordinary local directories.')
        owner=ctypes.c_void_p();dacl=ctypes.c_void_p();descriptor=ctypes.c_void_p()
        code=self.a.GetNamedSecurityInfoW(str(path),1,5,ctypes.byref(owner),None,ctypes.byref(dacl),None,ctypes.byref(descriptor))
        if code:raise ctypes.WinError(code)
        try:
            if not dacl.value:raise ValueError('A null application ACL is not accepted.')
            # ACL header: revision, sbz1, size, AceCount, sbz2.
            count=ctypes.c_ushort.from_address(dacl.value+4).value;entries=[]
            if count>4096:raise ValueError('Application ACL exceeds its bound.')
            for index in range(count):
                ace=ctypes.c_void_p()
                if not self.a.GetAce(dacl,index,ctypes.byref(ace)):raise ctypes.WinError(ctypes.get_last_error())
                kind=ctypes.c_ubyte.from_address(ace.value).value;flags=ctypes.c_ubyte.from_address(ace.value+1).value
                if kind==0:
                    mask=ctypes.c_uint32.from_address(ace.value+4).value;entries.append((self.sid(ace.value+8),mask,bool(flags&8)))
                elif kind not in {1,2,3,17,18,19,20}:
                    raise ValueError('An unreviewed application ACL entry type is not accepted.')
            return self.sid(owner),entries
        finally:self.k.LocalFree(descriptor)
    def protect(self,path,current,create=False):
        descriptor=ctypes.c_void_p();sddl=f'D:P(A;OICI;FA;;;{current})(A;OICI;FA;;;SY)'
        if not self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,ctypes.byref(descriptor),None):raise ctypes.WinError(ctypes.get_last_error())
        try:
            if create:
                class SA(ctypes.Structure):_fields_=[('length',w.DWORD),('descriptor',ctypes.c_void_p),('inherit',w.BOOL)]
                attributes=SA(ctypes.sizeof(SA),descriptor,False)
                if not self.k.CreateDirectoryW(str(path),ctypes.byref(attributes)):raise ctypes.WinError(ctypes.get_last_error())
            elif not self.a.SetFileSecurityW(str(path),0x80000004,descriptor):raise ctypes.WinError(ctypes.get_last_error())
        finally:self.k.LocalFree(descriptor)


def main():
    if os.name!='nt':raise RuntimeError('The installer preflight is Windows-only.')
    local=Path(os.environ['LOCALAPPDATA']);root=canonical_root(sys.argv[1],local);native=Native();current=native.current()
    # LOCALAPPDATA and the two descendants must be owned and not foreign-writable.
    # Higher OS-managed ancestors are outside the writable per-user install root.
    for directory in [local,local/'Programs',root]:
        if directory.exists():
            owner,entries=native.inspect(directory);validate_acl(owner,current,entries)
        else:native.protect(directory,current,create=True)
        owner,entries=native.inspect(directory);validate_acl(owner,current,entries)
    version=sys.argv[2]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,119}',version):raise ValueError('Invalid installed version.')
    # Never follow or overwrite an existing version directory. A successor uses
    # a new immutable version; reinstalling this exact version needs uninstall.
    candidate=root/('app-'+version)
    if candidate.exists() or candidate.is_symlink():raise ValueError('This application version already exists; preserve it and uninstall before reinstalling.')
    native.protect(root,current)
    owner,entries=native.inspect(root);validate_acl(owner,current,entries)
    print('Verified private per-user application directory.')


if __name__=='__main__':
    try:main()
    except Exception:
        print('Application directory ownership/ACL validation failed; nothing was unpacked there.',file=sys.stderr)
        raise SystemExit(1)
