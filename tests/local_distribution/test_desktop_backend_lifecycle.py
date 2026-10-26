"""Owned backend owner-loss deadline, without killing unrelated processes."""
from scripts.desktop_backend import watch_owner


def test_owner_loss_requests_stop_then_exits_only_this_backend():
    calls=[]
    watch_owner(lambda:False,lambda:calls.append('stop'),lambda code:calls.append(('exit',code)),grace=.001)
    assert calls==['stop',('exit',70)]


def test_server_completion_cannot_cancel_owner_loss_deadline():
    calls=[]
    def stop():calls.append('server loop finished but model thread remains')
    watch_owner(lambda:False,stop,lambda code:calls.append(('exit',code)),grace=.001)
    assert calls[-1]==('exit',70)


def test_watch_remains_alive_until_owner_loss(monkeypatch):
    states=iter([True,False]);calls=[]
    monkeypatch.setattr('scripts.desktop_backend.time.sleep',lambda duration:calls.append(('wait',duration)))
    watch_owner(lambda:next(states),lambda:calls.append('stop'),lambda code:calls.append(('exit',code)),grace=12)
    assert calls==[('wait',.5),'stop',('wait',12),('exit',70)]
