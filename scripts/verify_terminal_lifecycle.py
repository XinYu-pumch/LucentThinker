"""Verify real PTY hangup stops the detached server, including attached launch windows."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import store
import httpx

ROOT=Path(__file__).resolve().parent.parent

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
    except OSError:return False

def wait_until(predicate, seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Lifecycle wait timed out')

def main():
    assert not any(r['status']=='running' for c in store.conversations() for r in store.get_conversation(c['id'])['runs']), 'Do not interrupt active research'
    reports=[]
    for mode in ('terminal_hangup','attached_window_hangup'):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        state=ROOT/'.cache'/('lifecycle-'+mode);state.mkdir(parents=True,exist_ok=True)
        pid,master=os.forkpty()
        if pid==0:
            os.execv(str(ROOT/'start.sh'),[str(ROOT/'start.sh'),'--port',str(port),'--state-dir',str(state)])
        attached=None
        try:
            wait_until(lambda:listening(port))
            with httpx.Client(trust_env=False) as client:
                assert client.get(f'http://127.0.0.1:{port}/api/config').status_code==200
            server_pid=int((state/'server.pid').read_text())
            if mode=='attached_window_hangup':
                with (state/'attached.log').open('w') as log:
                    attached=subprocess.Popen([str(ROOT/'start.sh'),'--port',str(port),'--state-dir',str(state)],stdout=log,stderr=log)
                wait_until(lambda:'已连接' in (state/'attached.log').read_text())
                assert int((state/'server.pid').read_text())==server_pid
                attached.send_signal(signal.SIGHUP)
                assert attached.wait(timeout=15)==0
            else:
                os.close(master);master=None
            wait_until(lambda:not listening(port))
            wait_until(lambda:not (state/'server.pid').exists())
            _,status=os.waitpid(pid,0);pid=None
            assert os.waitstatus_to_exitcode(status)==0
            reports.append({'mode':mode,'server_started':True,'port_released':True,'pid_files_removed':True,'supervisor_exit_code':0})
        finally:
            if master is not None:os.close(master)
            if attached and attached.poll() is None:attached.terminate();attached.wait(timeout=15)
            if pid:
                try:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0)
                except ProcessLookupError:pass
    (ROOT/'data/terminal-lifecycle-verification.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
