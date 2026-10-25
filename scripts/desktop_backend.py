"""Packaged backend entry point. Never consult a developer Python or migrate data."""
import fcntl
import os
from pathlib import Path
import signal
import stat
import sys
from threading import Thread
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import uvicorn
    parent=int(sys.argv[1])
    directory=Path(os.environ['MVP_WEB_DATA_DIR'])
    if not directory.is_absolute() or any(p.is_symlink() for p in (directory,*directory.parents)):
        raise RuntimeError('Unsafe desktop data path')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.stat().st_uid!=os.getuid():
        raise RuntimeError('Desktop data must be owned by the current user')
    directory.chmod(0o700)
    lock=os.open(directory/'.desktop-backend.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    metadata=os.fstat(lock)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=os.getuid():
        raise RuntimeError('Unsafe desktop lock')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    server=uvicorn.Server(uvicorn.Config('src.web_api.app:app_factory',factory=True,
        host='127.0.0.1',port=int(os.environ['MVP_API_HOST'].rsplit(':',1)[1]),
        workers=1,access_log=False,proxy_headers=False,timeout_graceful_shutdown=10,log_level='critical'))
    def watch_parent():
        while not server.should_exit:
            if os.getppid()!=parent:
                server.should_exit=True
                return
            time.sleep(.5)
    Thread(target=watch_parent,daemon=True).start()
    try:server.run()
    finally:os.close(lock)


if __name__=='__main__':main()
