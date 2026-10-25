"""Local distribution safety checks; no providers, setup downloads or app data."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
from types import SimpleNamespace

import pytest

from scripts import local_preview as preview
from scripts import run_web as web


@pytest.fixture
def short_data():
    # macOS AF_UNIX socket paths are short; use a dedicated synthetic QA root.
    base = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp").resolve()
    path = Path(tempfile.mkdtemp(prefix="lp-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path)


def env(inherited=None, **updates):
    return web.local_environment(inherited or {}, data_dir="/private/preview", api_port=8871,
                                 web_port=3088, node=sys.executable, isolated=True, **updates)


def test_distribution_environment_drops_hosted_and_provider_injection():
    inherited = {key: "must-not-leak" for key in (
        "MVP_HOSTED_INVITE_SHA256", "MVP_PERSISTENT_ROOT", "MVP_PUBLIC_ORIGIN", "RENDER_EXTERNAL_URL",
        "NCBI_EMAIL", "NCBI_API_KEY", "OPENAI_API_KEY", "DEEPINFRA_API_KEY", "HF_TOKEN",
        "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS", "HTTPS_PROXY",
        "MVP_PROPOSALS_ENABLED", "MVP_MAP_ENABLED", "MVP_SEARCH_PLANNER_ENABLED", "MVP_API_ORIGIN")}
    inherited.update(HOME="/private/home", PATH="/usr/bin", MVP_DEPLOYMENT_MODE="hosted")
    actual = env(inherited, browser_host="localhost")
    assert actual["HOME"] == "/private/home"
    assert actual["MVP_DEPLOYMENT_MODE"] == "local"
    assert actual["MVP_WEB_ORIGIN"] == "http://localhost:3088"
    assert actual["MVP_API_ORIGIN"] == "http://127.0.0.1:8871"
    assert all(actual[name] == "0" for name in ("MVP_PROPOSALS_ENABLED", "MVP_MAP_ENABLED", "MVP_SEARCH_PLANNER_ENABLED"))
    assert actual["NODE_ENV"] == "production"
    assert not any(value == "must-not-leak" for value in actual.values())
    assert not set(actual) & {"PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "HTTPS_PROXY", "NCBI_EMAIL", "NCBI_API_KEY"}


def test_live_is_explicit_and_only_validated_ncbi_values_are_forwarded():
    inherited = {"NCBI_EMAIL": "reviewer@example.org", "NCBI_API_KEY": "a" * 36,
                 "OPENAI_API_KEY": "must-not-leak", "MVP_PROPOSALS_ENABLED": "1"}
    assert "NCBI_EMAIL" not in env(inherited)
    actual = env(inherited, allow_live=True)
    assert actual["NCBI_EMAIL"] == inherited["NCBI_EMAIL"]
    assert actual["NCBI_API_KEY"] == inherited["NCBI_API_KEY"]
    assert "OPENAI_API_KEY" not in actual and actual["MVP_PROPOSALS_ENABLED"] == "0"
    for invalid in ({}, {"NCBI_EMAIL": "bad"}, {"NCBI_EMAIL": "a@example.org", "NCBI_API_KEY": "bad key"}):
        with pytest.raises(web.LocalLaunchError):
            env(invalid, allow_live=True)


@pytest.mark.parametrize("api,ui", [(1,3000),(8765,65536),(8765,8765)])
def test_invalid_ports_are_refused(api, ui):
    with pytest.raises(web.LocalLaunchError):
        web.check_ports_available(api, ui)


@pytest.mark.parametrize("reuse", [False, True])
def test_foreign_port_conflict_never_starts_or_kills_processes(monkeypatch,reuse):
    with socket.socket() as foreign:
        if reuse:foreign.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        foreign.bind(("127.0.0.1", 0));foreign.listen()
        port=foreign.getsockname()[1]
        monkeypatch.setattr(web.subprocess, "Popen", lambda *a, **k: pytest.fail("No child may start after a port conflict"))
        servers=web.LocalServers([], {}, port, port+1 if port<65535 else port-1)
        with pytest.raises(web.LocalLaunchError, match="unavailable"):
            servers.start()
        assert foreign.fileno() >= 0


def test_immediate_port_preflight_after_real_tcp_active_close():
    """Real loopback handshake/active close; no sleeps or retry workaround."""
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(("127.0.0.1",0));port=listener.getsockname()[1];listener.listen()
        with socket.create_connection(("127.0.0.1",port)) as client:
            accepted,_=listener.accept()
            with accepted:
                accepted.shutdown(socket.SHUT_WR)
                assert client.recv(1)==b""
                client.close()
    # Establish the prior failure condition, then immediately exercise the
    # corrected preflight. The previous implementation fails this scenario.
    import errno
    with socket.socket() as without_reuse:
        with pytest.raises(OSError) as failure:without_reuse.bind(("127.0.0.1",port))
        assert failure.value.errno==errno.EADDRINUSE
    with socket.socket() as free:
        free.bind(("127.0.0.1",0));other=free.getsockname()[1]
    web.check_ports_available(other,port)


def test_listener_identity_distinguishes_our_socket_from_another_pid():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0));listener.listen()
        port=listener.getsockname()[1]
        assert web.listener_owned(os.getpid(),port)
        assert not web.listener_owned(1,port)


def test_foreign_health_cannot_satisfy_readiness(monkeypatch):
    servers=web.LocalServers([],{},8871,3088)
    servers.children=[SimpleNamespace(pid=1,poll=lambda:None),SimpleNamespace(pid=2,poll=lambda:None)]
    monkeypatch.setattr(web,"listener_owned",lambda *a:False)
    monkeypatch.setattr(web,"health_ready",lambda *a:pytest.fail("Foreign listeners must not be health-probed as ours"))
    with pytest.raises(web.LocalLaunchError,match="did not become ready"):
        servers.wait_ready(Event(),timeout=.01)


def test_both_owned_health_checks_are_required_and_use_browser_host(monkeypatch):
    servers=web.LocalServers([],{},8871,3088,browser_host="localhost")
    servers.children=[SimpleNamespace(pid=1,poll=lambda:None),SimpleNamespace(pid=2,poll=lambda:None)]
    calls=[]
    monkeypatch.setattr(web,"listener_owned",lambda *a:True)
    def health(*args):calls.append(args);return True
    monkeypatch.setattr(web,"health_ready",health)
    assert servers.wait_ready(Event(),timeout=1)
    assert calls==[(8871,"/readyz",{"ready":True}),(3088,"/healthz",{"status":"ok"},"localhost")]


def test_stop_stale_manifest_never_signals_recorded_pid(short_data,monkeypatch):
    state=preview.private_directory(short_data/".preview")
    with preview.owner_lock(state):pass
    preview.atomic_json(state/"owner.json",{"pid":os.getpid(),"token":"a"*64,"instance":"b"*32})
    monkeypatch.setattr(os,"kill",lambda *a:pytest.fail("Stored PIDs must never be signalled"))
    assert preview.control_request(short_data,"stop")["status"]=="stopped"
    assert (state/"owner.json").exists()


def test_authenticated_controller_status_and_stop(short_data):
    state=preview.private_directory(short_data/".preview")
    stop=Event();ready=Event();errors=[]
    identity={"token":"a"*64,"instance":"b"*32,"pid":os.getpid(),"phase":"ready"}
    def serve():
        try:
            with preview.owner_lock(state):
                controller=preview.Controller(state,stop,identity)
                controller.start();preview.atomic_json(state/"owner.json",identity);ready.set()
                try:stop.wait(5)
                finally:controller.close()
        except Exception as error:errors.append(error);ready.set()
    thread=Thread(target=serve);thread.start()
    try:
        assert ready.wait(3) and not errors
        connection=socket.socket(socket.AF_UNIX);connection.settimeout(1);connection.connect(str(state/"control"))
        connection.sendall((json.dumps({"action":"stop","instance":"b"*32,"token":"wrong"})+"\n").encode())
        assert preview.read_message(connection)=={"status":"denied"};connection.close()
        assert not stop.is_set()
        actual=preview.control_request(short_data,"status")
        assert actual["status"]=="ready" and "token" not in actual
        assert preview.control_request(short_data,"stop")["status"]=="stopped"
        thread.join(timeout=2);assert not thread.is_alive() and not errors
    finally:
        stop.set();thread.join(timeout=3)


def test_lock_refuses_second_controller_without_touching_ownership(short_data):
    state=preview.private_directory(short_data/".preview")
    with preview.owner_lock(state):
        with pytest.raises(web.LocalLaunchError,match="already has"):
            with preview.owner_lock(state):pytest.fail("Second owner acquired lock")


def test_containment_dotdot_symlink_and_long_paths_create_no_app_data(tmp_path,monkeypatch):
    root=tmp_path/"app";root.mkdir();monkeypatch.setattr(preview,"ROOT",root)
    for path in (root/"research",tmp_path/"outside/../app/research",tmp_path/("x"*110)):
        with pytest.raises(web.LocalLaunchError):preview.state_paths(path)
    assert not (root/"research").exists()
    link=tmp_path/"linked";link.symlink_to(root,target_is_directory=True)
    with pytest.raises(web.LocalLaunchError):preview.private_directory(link/"research")
    assert not (root/"research").exists()


def test_python_node_pnpm_prerequisites_are_exact_and_actionable(tmp_path,monkeypatch):
    executable=tmp_path/"tool";executable.write_text("public placeholder");executable.chmod(0o700)
    monkeypatch.setattr(preview,"command_version",lambda command,env:"v24.19.0" if command[0]==str(executable) else "10.20.0")
    pnpm=tmp_path/"pnpm";pnpm.write_text("public placeholder");pnpm.chmod(0o700)
    assert preview.prerequisites(str(executable),str(pnpm))["node_version"]=="v24.19.0"
    monkeypatch.setattr(preview,"command_version",lambda command,env:"v24.19.0" if command[0]==str(executable) else "11.0.0")
    with pytest.raises(web.LocalLaunchError,match="10.20.0"):preview.prerequisites(str(executable),str(pnpm))
    monkeypatch.setattr(preview,"command_version",lambda *a:"v22.0.0")
    with pytest.raises(web.LocalLaunchError,match="Node.js24"):preview.prerequisites(str(executable),require_pnpm=False)
    monkeypatch.setattr(preview.sys,"version_info",(3,11))
    with pytest.raises(web.LocalLaunchError,match="Python3.12"):preview.prerequisites()


def test_missing_setup_and_next_env_file_are_honest_errors(tmp_path,monkeypatch):
    monkeypatch.setattr(preview,"ROOT",tmp_path)
    with pytest.raises(web.LocalLaunchError,match="Setup required"):
        preview.launch_configuration(argparse.Namespace())
    webroot=tmp_path/"apps/web";webroot.mkdir(parents=True);(webroot/".env.production.local").write_text("synthetic private canary, never parsed")
    with pytest.raises(web.LocalLaunchError,match="Next.js .env"):
        preview.reject_web_env_files(tmp_path)


def test_installation_cannot_be_replaced_while_launcher_is_running(tmp_path,monkeypatch):
    monkeypatch.setattr(preview,"ROOT",tmp_path)
    with preview.installation_lock(shared=True):
        with pytest.raises(web.LocalLaunchError,match="running or being set up"):
            with preview.installation_lock():pytest.fail("Setup acquired a live install")


def test_bounded_owned_group_cleanup_preserves_unrelated_process(short_data):
    marker=short_data/"descendant.pid"
    # Parent exits after creating a descendant which ignores SIGTERM.
    descendant="import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)"
    parent=f"import subprocess,sys,pathlib,time;p=subprocess.Popen([sys.executable,'-c',{descendant!r}]);pathlib.Path({str(marker)!r}).write_text(str(p.pid));time.sleep(.1)"
    foreign=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],start_new_session=True)
    servers=web.LocalServers([],{},8871,3088,shutdown_seconds=.1)
    child=subprocess.Popen([sys.executable,"-c",parent],start_new_session=True)
    servers.children=[child]
    try:
        deadline=time.monotonic()+3
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert marker.exists();child.wait(timeout=3)
        started=time.monotonic();servers.stop();assert time.monotonic()-started<2
        assert foreign.poll() is None
        descendant_pid=int(marker.read_text())
        # Killed orphan may briefly remain as a zombie until the OS reaps it.
        for _ in range(60):
            result=subprocess.run(["ps","-o","stat=","-p",str(descendant_pid)],capture_output=True,text=True)
            if result.returncode or result.stdout.strip().startswith("Z"):break
            time.sleep(.02)
        else:pytest.fail("Owned descendant survived launcher cleanup")
    finally:
        servers.stop();foreign.terminate();foreign.wait(timeout=3)


def test_sigkill_controller_preserves_both_locks_until_owned_children_exit(short_data,monkeypatch):
    app=short_data/"app";app.mkdir()
    data=preview.private_directory(short_data/"data")
    state=preview.private_directory(data/".preview")
    registry=short_data/"children.json"
    harness=f'''
import json,os,sys,time
from pathlib import Path
from threading import Event
from scripts import local_preview as preview
from scripts.run_web import LocalServers
preview.ROOT=Path({str(app)!r})
state=Path({str(state)!r})
stop=Event()
identity={{"token":"a"*64,"instance":"b"*32,"pid":os.getpid(),"phase":"ready"}}
with preview.installation_lock(shared=True) as install_fd:
 with preview.owner_lock(state) as owner_fd:
  controller=preview.Controller(state,stop,identity);controller.start()
  preview.atomic_json(state/"owner.json",identity)
  commands=[]
  for index in range(2):
   marker=Path({str(short_data)!r})/('child-'+str(index))
   code="from pathlib import Path;import time;Path("+repr(str(marker))+").write_text('ready');time.sleep(60)"
   commands.append(([sys.executable,'-c',code],preview.ROOT))
  servers=LocalServers(commands,{{"PATH":os.defpath}},8886,3098,pass_fds=(owner_fd,install_fd))
  servers.start()
  Path({str(registry)!r}).write_text(json.dumps([child.pid for child in servers.children]))
  time.sleep(60)
'''
    controller=subprocess.Popen([sys.executable,"-c",harness],cwd=Path(__file__).resolve().parents[2],start_new_session=True)
    children=[]
    try:
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if registry.exists() and all((short_data/f"child-{index}").exists() for index in range(2)):
                children=json.loads(registry.read_text());break
            assert controller.poll() is None
            time.sleep(.02)
        assert len(children)==2
        controller.kill();controller.wait(timeout=3)
        assert preview.lock_held(state)
        monkeypatch.setattr(preview,"ROOT",app)
        with pytest.raises(web.LocalLaunchError,match="running or being set up"):
            with preview.installation_lock():pytest.fail("Setup must not replace an orphaned runtime")
        # A different pair of ports must not bypass the durable data lock.
        next_cli=app/"apps/web/node_modules/next/dist/bin/next";next_cli.parent.mkdir(parents=True);next_cli.write_text("public test placeholder")
        (app/"apps/web/.next").mkdir();(app/"apps/web/.next/BUILD_ID").write_text("synthetic")
        monkeypatch.setattr(preview,"launch_configuration",lambda args:(sys.executable,sys.executable))
        args=argparse.Namespace(data_dir=data,api_port=8887,web_port=3099,allow_live=False,browser_host="localhost",no_browser=True)
        with preview.installation_lock(shared=True) as descriptor:
            with pytest.raises(web.LocalLaunchError,match="already has a running preview"):
                preview.launch(args,installation_descriptor=descriptor)
        with monkeypatch.context() as safe:
            safe.setattr(os,"kill",lambda *a:pytest.fail("A lost controller must not cause stale PID signalling"))
            with pytest.raises(web.LocalLaunchError,match="no PID was signalled"):
                preview.control_request(data,"stop")
    finally:
        if controller.poll() is None:controller.kill();controller.wait(timeout=3)
        # Only child groups created by this fresh synthetic harness are ended.
        for pid in children:
            try:os.killpg(pid,signal.SIGTERM)
            except ProcessLookupError:pass
    deadline=time.monotonic()+3
    while preview.lock_held(state) and time.monotonic()<deadline:time.sleep(.02)
    assert not preview.lock_held(state)
    with preview.installation_lock():pass


@pytest.mark.parametrize("case", ["ready", "no-browser", "startup-failure", "port-conflict", "timeout", "cancelled"])
def test_browser_open_is_gated_by_both_owned_servers_ready(short_data,monkeypatch,case):
    """Mocked OS opener and servers: ordering/control-flow, not browser QA."""
    app=short_data/"app";app.mkdir()
    data=short_data/"data"
    monkeypatch.setattr(preview,"ROOT",app)
    monkeypatch.setattr(preview,"launch_configuration",lambda args:(sys.executable,sys.executable))
    monkeypatch.setattr(preview,"server_commands",lambda *args:[])
    observations=[]
    state={}
    class FakeController:
        def __init__(self,path,stop,identity):state["stop"]=stop
        def start(self):observations.append("controller-start")
        def close(self):observations.append("controller-close")
    class FakeServers:
        def __init__(self,*args,**kwargs):pass
        def start(self):
            observations.append("servers-start")
            if case in {"startup-failure","port-conflict"}:
                raise web.LocalLaunchError(case)
        def wait_ready(self,stop):
            observations.append("api-owned-ready")
            if case=="timeout":raise web.LocalLaunchError("readiness timeout")
            if case=="cancelled":stop.set();return False
            observations.append("web-owned-ready")
            state["both_ready"]=True
            if case=="no-browser":stop.set()
            return True
        def check_children(self):pytest.fail("Mocked launch should already be stopping")
        def stop(self):observations.append("owned-servers-stop")
    def open_browser(url):
        assert state.get("both_ready") is True,"Browser opened before both owned health checks"
        assert observations[-1]=="web-owned-ready"
        assert url=="http://localhost:3088"
        observations.append("browser-open")
        state["stop"].set()
        return True
    monkeypatch.setattr(preview,"Controller",FakeController)
    monkeypatch.setattr(preview,"LocalServers",FakeServers)
    monkeypatch.setattr(preview.webbrowser,"open",open_browser)
    args=argparse.Namespace(data_dir=data,api_port=8871,web_port=3088,
                           allow_live=False,browser_host="localhost",no_browser=case=="no-browser")
    if case in {"startup-failure","port-conflict","timeout"}:
        with pytest.raises(web.LocalLaunchError):preview.launch(args)
    else:
        assert preview.launch(args)["status"]=="stopped"
    assert observations.count("browser-open")==int(case=="ready")
    assert "owned-servers-stop" in observations and observations[-1]=="controller-close"
    assert not (data/".preview/owner.json").exists()


def test_distribution_preserves_windows_username_without_pwd_or_credentials():
    # Windows has no Unix pwd module. Torch's eager model-import path also
    # initializes a username-scoped cache through getpass.getuser().
    inherited = {key: value for key, value in os.environ.items() if key in web.SAFE_ENVIRONMENT}
    for key in ("LOGNAME", "USER", "LNAME"):
        inherited.pop(key, None)
    inherited.update(USERNAME="windows-software-qa", OPENAI_API_KEY="PRIVATE_CANARY",
        PYTHONPATH="PRIVATE_CANARY", NODE_OPTIONS="PRIVATE_CANARY")
    actual = env(inherited)
    code = "import sys,getpass;sys.modules['pwd']=None;assert getpass.getuser()=='windows-software-qa';print('USERNAME_PREREQUISITE_PASS')"
    result = subprocess.run([sys.executable, "-c", code], env=actual, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, "An isolated Windows-compatible child must resolve its OS username without Unix pwd."
    assert result.stdout.strip() == "USERNAME_PREREQUISITE_PASS"
    assert "PRIVATE_CANARY" not in actual.values()
    assert not set(actual) & {"OPENAI_API_KEY", "PYTHONPATH", "NODE_OPTIONS"}
