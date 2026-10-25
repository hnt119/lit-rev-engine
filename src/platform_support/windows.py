"""Pinned pywin32 native file/ACL/lock primitives, loaded only on Windows.

The bootstrap must install the explicit Windows prerequisite before touching
private state. No chmod-as-ACL, permissive named-pipe default or PID signal is
used. Same-account malware and privileged administrators are outside this
per-user boundary, as on POSIX.
"""
from functools import lru_cache
from functools import wraps
import errno
import ntpath
import os
from pathlib import Path
import stat


@lru_cache(maxsize=1)
def require_runtime():
    if os.name != 'nt':
        raise RuntimeError('Windows native security is available only on Windows.')
    try:
        import pywintypes, win32api, win32con, win32file, win32security, win32event, win32process, win32job, win32pipe, ntsecuritycon
        from types import SimpleNamespace
        from importlib.metadata import version
        if version('pywin32') != '312':
            raise ImportError('unreviewed security runtime')
    except ImportError:
        raise RuntimeError('Windows setup requires the pinned security prerequisite before private state is opened. Create .venv-bootstrap with py -3.12 -m venv .venv-bootstrap, then run its Scripts\\python.exe -m pip install -r requirements-windows-bootstrap.txt. Use that interpreter for setup/launch; do not run the global pywin32 post-install script.') from None
    # File access rights live in ntsecuritycon; some file/event constants are
    # exported only by their API modules in pinned pywin32 312.
    constants = SimpleNamespace(**vars(win32con))
    constants.FILE_READ_ATTRIBUTES = ntsecuritycon.FILE_READ_ATTRIBUTES
    constants.FILE_ALL_ACCESS = ntsecuritycon.FILE_ALL_ACCESS
    constants.FILE_FLAG_OPEN_REPARSE_POINT = win32file.FILE_FLAG_OPEN_REPARSE_POINT
    constants.INFINITE = win32event.INFINITE
    constants.MOVEFILE_WRITE_THROUGH = 0x8  # documented Win32 MOVEFILE_WRITE_THROUGH
    return pywintypes, win32api, constants, win32file, win32security, win32event, win32process, win32job, win32pipe


def _os_error(error):
    code = getattr(error, 'winerror', error.args[0] if error.args else 0)
    kind, number = ({2: (FileNotFoundError, errno.ENOENT), 3: (FileNotFoundError, errno.ENOENT),
        5: (PermissionError, errno.EACCES), 32: (PermissionError, errno.EACCES),
        80: (FileExistsError, errno.EEXIST), 183: (FileExistsError, errno.EEXIST),
        33: (BlockingIOError, errno.EAGAIN)}).get(code, (OSError, errno.EIO))
    result = kind(number, 'The private Windows operation failed; no unsafe fallback was used.')
    result.winerror = code
    return result


def native_errors(function):
    """Expose ordinary OSError categories at the existing platform boundary."""
    @wraps(function)
    def call(*args, **kwargs):
        types = require_runtime()[0]
        try: return function(*args, **kwargs)
        except types.error as error: raise _os_error(error) from None
    return call


@lru_cache(maxsize=1)
def current_sid():
    _, api, con, _, security, *_ = require_runtime()
    token = security.OpenProcessToken(api.GetCurrentProcess(), con.TOKEN_QUERY)
    try:return security.GetTokenInformation(token, security.TokenUser)[0]
    finally:token.Close()


def current_sid_text():
    return require_runtime()[4].ConvertSidToStringSid(current_sid())


def security_attributes(directory=False):
    types, _, con, _, security, *_ = require_runtime()
    acl=security.ACL()
    flags=con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE if directory else 0
    acl.AddAccessAllowedAceEx(security.ACL_REVISION_DS, flags, con.FILE_ALL_ACCESS, current_sid())
    system=security.CreateWellKnownSid(security.WinLocalSystemSid,None)
    acl.AddAccessAllowedAceEx(security.ACL_REVISION_DS, flags, con.FILE_ALL_ACCESS, system)
    descriptor=security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(current_sid(),False)
    descriptor.SetSecurityDescriptorDacl(True,acl,False)
    descriptor.SetSecurityDescriptorControl(security.SE_DACL_PROTECTED,security.SE_DACL_PROTECTED)
    attributes=types.SECURITY_ATTRIBUTES()
    attributes.SECURITY_DESCRIPTOR=descriptor
    attributes.bInheritHandle=False
    return attributes


def _full(path):
    raw=os.fspath(path)
    drive,tail=ntpath.splitdrive(raw)
    if not drive or drive.startswith('\\') or ':' in tail or '\x00' in raw:
        raise ValueError('Use a local drive path, without network paths, device names or alternate streams.')
    for part in Path(raw).parts[1:]:
        name=part.split('.',1)[0].upper()
        if part in {'.','..'} or part.endswith(('.', ' ')) or name in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise ValueError('Use an ordinary local Windows path without ambiguous or reserved components.')
    _require_ntfs(drive + '\\')
    return Path(ntpath.abspath(raw))


def _require_ntfs(drive):
    _, api, con, file, *_ = require_runtime()
    # A mapped SMB drive can report an NTFS label. Drive type is checked on
    # every operation, before querying volume metadata or touching private data.
    if file.GetDriveType(drive) != con.DRIVE_FIXED:
        raise ValueError('Windows private data requires a fixed local drive; mapped/network, removable and unknown drives are unsupported.')
    if api.GetVolumeInformation(drive)[-1].upper() != 'NTFS':
        raise ValueError('Windows private data requires a local NTFS volume; network, FAT and exFAT storage are unsupported.')


@native_errors
def assert_no_reparse(path):
    path=_full(path)
    types,api,con,file,*_=require_runtime()
    for item in (path,*path.parents):
        try:
            # win32file's raw DWORD wrapper returns INVALID_FILE_ATTRIBUTES on
            # failure. win32api checks that sentinel and raises the error.
            flags=api.GetFileAttributes(_native(item))
        except types.error as error:
            if getattr(error,'winerror',None) in {2,3}:continue
            raise _os_error(error) from None
        if flags & con.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Private Windows paths cannot contain reparse points or junctions.')
    return path


def _native(path):
    # User-supplied device/extended paths are rejected by _full first. Only our
    # canonical, validated drive path receives the long-path API prefix.
    return '\\\\?\\' + str(path)


@native_errors
def _handle(path, *, directory=False, access=None):
    _,_,con,file,*_=require_runtime()
    path=assert_no_reparse(path)
    return file.CreateFile(_native(path),(access or con.READ_CONTROL) | con.FILE_READ_ATTRIBUTES,
        con.FILE_SHARE_READ|con.FILE_SHARE_WRITE,None,con.OPEN_EXISTING,
        con.FILE_FLAG_OPEN_REPARSE_POINT | (con.FILE_FLAG_BACKUP_SEMANTICS if directory else 0),None)


def _security(handle):
    security=require_runtime()[4]
    return security.GetSecurityInfo(handle,security.SE_FILE_OBJECT,security.OWNER_SECURITY_INFORMATION|security.DACL_SECURITY_INFORMATION)


def _owned(handle,private=False):
    _,_,con,file,security,*_=require_runtime()
    info=file.GetFileInformationByHandle(handle)
    if info[0] & con.FILE_ATTRIBUTE_REPARSE_POINT:return False
    descriptor=_security(handle)
    if descriptor.GetSecurityDescriptorOwner()!=current_sid():return False
    if not private:return True
    control,_=descriptor.GetSecurityDescriptorControl()
    acl=descriptor.GetSecurityDescriptorDacl()
    if not control & security.SE_DACL_PROTECTED or acl is None:return False
    allowed={current_sid_text(),security.ConvertSidToStringSid(security.CreateWellKnownSid(security.WinLocalSystemSid,None))}
    saw_owner=False
    for index in range(acl.GetAceCount()):
        header,mask,sid=acl.GetAce(index)
        if header[0]!=con.ACCESS_ALLOWED_ACE_TYPE or security.ConvertSidToStringSid(sid) not in allowed:return False
        if sid==current_sid() and mask & con.FILE_ALL_ACCESS == con.FILE_ALL_ACCESS:saw_owner=True
    return saw_owner


def _protect(handle,directory=False):
    _,_,_,_,security,*_=require_runtime()
    descriptor=security_attributes(directory).SECURITY_DESCRIPTOR
    security.SetSecurityInfo(handle,security.SE_FILE_OBJECT,
        security.DACL_SECURITY_INFORMATION|security.PROTECTED_DACL_SECURITY_INFORMATION,
        None,None,descriptor.GetSecurityDescriptorDacl(),None)


@native_errors
def private_directory(path):
    _,_,con,file,*_=require_runtime()
    path=assert_no_reparse(path)
    missing=[];current=path
    while not current.exists():missing.append(current);current=current.parent
    for current in reversed(missing):
        file.CreateDirectory(_native(current),security_attributes(True))
    handle=_handle(path,directory=True,access=con.READ_CONTROL|con.WRITE_DAC)
    try:
        if not file.GetFileInformationByHandle(handle)[0] & con.FILE_ATTRIBUTE_DIRECTORY or not _owned(handle):
            raise ValueError('Private directory must be an ordinary directory owned by the current Windows SID.')
        _protect(handle,True)
        if not _owned(handle,True):raise ValueError('Private directory ACL verification failed.')
    finally:handle.Close()
    return path


@native_errors
def exclusive_private_directory(path):
    path = assert_no_reparse(path)
    require_runtime()[3].CreateDirectory(_native(path), security_attributes(True))
    return private_directory(path)


@native_errors
def open_private(path,flags,*,strict=False):
    import msvcrt
    _,_,con,file,*_=require_runtime()
    access=con.READ_CONTROL|con.WRITE_DAC
    access|=con.GENERIC_WRITE if flags & (os.O_WRONLY|os.O_RDWR) else 0
    access|=con.GENERIC_READ if not flags & os.O_WRONLY or flags & os.O_RDWR else 0
    disposition=con.CREATE_NEW if flags & os.O_CREAT and flags & os.O_EXCL else con.OPEN_ALWAYS if flags & os.O_CREAT else con.OPEN_EXISTING
    path=assert_no_reparse(path)
    handle=file.CreateFile(_native(path),access,con.FILE_SHARE_READ|con.FILE_SHARE_WRITE,
        security_attributes(),disposition,con.FILE_FLAG_OPEN_REPARSE_POINT,None)
    try:
        info=file.GetFileInformationByHandle(handle)
        if info[0] & (con.FILE_ATTRIBUTE_REPARSE_POINT|con.FILE_ATTRIBUTE_DIRECTORY) or info[7]!=1 or not _owned(handle,private=strict):
            raise ValueError('Private Windows file must be ordinary, singly linked and owned by the current SID, with the expected ACL.')
        if not strict:_protect(handle)
        if not _owned(handle,True):raise ValueError('Private file ACL verification failed.')
        if flags & os.O_TRUNC:file.SetFilePointer(handle,0,con.FILE_BEGIN);file.SetEndOfFile(handle)
        native=handle.Detach()
        handle=None
        try:return msvcrt.open_osfhandle(native,flags & (os.O_RDONLY|os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_BINARY))
        except BaseException:
            require_runtime()[1].CloseHandle(native)
            raise
    finally:
        if handle is not None:handle.Close()


@native_errors
def owned_fd(descriptor,*,private=False):
    import msvcrt
    return _owned(msvcrt.get_osfhandle(descriptor),private)


@native_errors
def owned_path(path,*,private=False):
    handle=_handle(path,directory=Path(path).is_dir())
    try:return _owned(handle,private)
    finally:handle.Close()


@native_errors
def restrict_fd(descriptor):
    import msvcrt
    handle=msvcrt.get_osfhandle(descriptor)
    if not _owned(handle):raise ValueError('File owner differs from the current Windows SID.')
    _protect(handle)


@native_errors
def restrict_path(path):
    con=require_runtime()[2]
    handle=_handle(path,directory=Path(path).is_dir(),access=con.READ_CONTROL|con.WRITE_DAC)
    try:
        if not _owned(handle):raise ValueError('Path owner differs from the current Windows SID.')
        _protect(handle,Path(path).is_dir())
    finally:handle.Close()


@native_errors
def flock(descriptor,operation):
    import msvcrt
    types,_,con,file,*_=require_runtime()
    handle=msvcrt.get_osfhandle(descriptor)
    overlapped=types.OVERLAPPED()
    if operation==8:
        file.UnlockFileEx(handle,1,0,overlapped)
        return
    if operation & ~(1|2|4) or bool(operation & 1)==bool(operation & 2):
        raise ValueError('Choose a shared or exclusive OS file lock.')
    flags=(con.LOCKFILE_EXCLUSIVE_LOCK if operation&2 else 0)|(con.LOCKFILE_FAIL_IMMEDIATELY if operation&4 else 0)
    try:file.LockFileEx(handle,flags,1,0,overlapped)
    except types.error as error:
        if getattr(error,'winerror',None)==33:raise BlockingIOError('Another process owns this OS file lock.') from None
        raise


def is_process_alive(pid):
    types,api,con,_,_,event,process,*_=require_runtime()
    try:handle=api.OpenProcess(con.SYNCHRONIZE|0x1000,False,pid)
    except types.error:return False
    try:return event.WaitForSingleObject(handle,0)==con.WAIT_TIMEOUT
    finally:handle.Close()


@native_errors
def move(source, destination, *, replace=False):
    _, api, con, *_ = require_runtime()
    api.MoveFileEx(_native(assert_no_reparse(source)), _native(assert_no_reparse(destination)),
        con.MOVEFILE_WRITE_THROUGH | (con.MOVEFILE_REPLACE_EXISTING if replace else 0))
