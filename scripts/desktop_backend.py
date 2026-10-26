"""Packaged backend and narrow native helpers. No system runtime or migration."""
import json
import os
from pathlib import Path
import sys
from threading import Thread
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def listener_owned(pid, port):
    if os.name!='nt': raise RuntimeError('Windows listener helper is Windows-only.')
    from src.platform_support.windows import require_runtime
    from src.platform_support.processes import OwnedWindowsProcess, windows_listener_owned
    from types import SimpleNamespace
    _,api,con,*_=require_runtime()
    handle=api.OpenProcess(con.SYNCHRONIZE|0x1000,False,pid)
    child=OwnedWindowsProcess(handle,pid,[],SimpleNamespace(handle=None))
    try:return windows_listener_owned(child,port)
    finally:child.close()


def watch_owner(parent_alive,request_stop,forced_exit,grace=12):
    # This daemon stays until process termination, including Python's wait for
    # non-daemon model threads after server.run returns. Only this backend exits.
    while True:
        if not parent_alive():
            request_stop()
            time.sleep(grace)
            forced_exit(70)
            return
        time.sleep(.5)


def main():
    from src.platform_support.files import private_directory,open_private,owned_fd
    from src.platform_support.locks import flock,LOCK_EX,LOCK_NB
    if len(sys.argv)==3 and sys.argv[1]=='--private-directory':
        private_directory(Path(sys.argv[2]));return
    if len(sys.argv)==4 and sys.argv[1]=='--listener-owned':
        if not listener_owned(int(sys.argv[2]),int(sys.argv[3])):raise RuntimeError('Listener is not owned.')
        return
    import uvicorn
    parent=int(sys.argv[1])
    directory=private_directory(Path(os.environ['MVP_WEB_DATA_DIR']))
    lock=open_private(directory/'.desktop-backend.lock',os.O_CREAT|os.O_RDWR)
    if not owned_fd(lock,private=True):raise RuntimeError('Unsafe desktop lock')
    flock(lock,LOCK_EX|LOCK_NB)
    parent_handle=job=None
    if os.name=='nt':
        from src.platform_support.windows import require_runtime,security_attributes
        _,api,con,_,_,event,_,jobs,_=require_runtime()
        parent_handle=api.OpenProcess(con.SYNCHRONIZE,False,parent)
        job=jobs.CreateJobObject(security_attributes(),'Local\\litrev-desktop-'+str(os.getpid()))
        limits=jobs.QueryInformationJobObject(job,jobs.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags']|=jobs.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        jobs.SetInformationJobObject(job,jobs.JobObjectExtendedLimitInformation,limits)
        jobs.AssignProcessToJobObject(job,api.GetCurrentProcess())
    server=uvicorn.Server(uvicorn.Config('src.web_api.app:app_factory',factory=True,
        host='127.0.0.1',port=int(os.environ['MVP_API_HOST'].rsplit(':',1)[1]),
        workers=1,access_log=False,proxy_headers=False,timeout_graceful_shutdown=10,log_level='critical'))
    def parent_alive():
        return (event.WaitForSingleObject(parent_handle,0)==con.WAIT_TIMEOUT) if os.name=='nt' else os.getppid()==parent
    def request_stop():server.should_exit=True
    def control():
        # Anonymous stdin is inherited only from our live owning Node process.
        # EOF on owner loss and the bounded private stop command are graceful;
        # no HTTP control endpoint, renderer IPC, stored PID or global signal.
        command=sys.stdin.buffer.readline(16)
        if command in {b'stop\n',b''}:server.should_exit=True
    Thread(target=watch_owner,args=(parent_alive,request_stop,os._exit),daemon=True).start()
    Thread(target=control,daemon=True).start()
    try:server.run()
    finally:
        os.close(lock)
        if parent_handle is not None:parent_handle.Close()
        if job is not None:job.Close()


if __name__=='__main__':main()
