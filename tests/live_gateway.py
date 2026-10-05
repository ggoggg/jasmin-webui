"""Opt-in integration test against a running gateway through SSH tunnels.

Requires ROUTER_PASSWORD, SMPP_PASSWORD, ROUTER_PORT, SMPP_PORT and the
forward/reverse tunnels documented in README. Creates only unique test objects.
"""
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
import requests


class SMSC(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SMPP(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.connection = self.request
        def read(n):
            data = b''
            while len(data) < n:
                chunk = self.request.recv(n-len(data))
                if not chunk: raise EOFError
                data += chunk
            return data
        try:
            while True:
                length, command, status, seq = struct.unpack('>IIII', read(16))
                body = read(length-16)
                if command == 9:
                    assert body.split(b'\0')[:2] == [self.server.system_id.encode(), self.server.password.encode()]
                    response = b'test-smsc\0'
                    self.server.bound.set()
                elif command == 4:
                    self.server.submits.append(body)
                    response = b'test-message-001\0'
                    self.server.submitted.set()
                elif command == 0x80000005:
                    self.server.mo_status = status
                    self.server.mo_acked.set()
                    continue
                elif command in (0x15, 6): response = b''
                elif command & 0x80000000: continue
                else: response = b''
                self.request.sendall(struct.pack('>IIII', 16+len(response), command|0x80000000, 0, seq)+response)
                if command == 6: break
        except (EOFError, ConnectionError, OSError):
            pass


class Callback(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.messages.append(parse_qs(raw.decode()))
        self.send_response(200); self.end_headers(); self.wfile.write(b'ACK/Jasmin')
        self.server.received.set()
    def log_message(self, *args): pass


def wait_until(fn, message, timeout=20):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        if fn(): return
        time.sleep(.2)
    raise AssertionError(message)


def remove_test_profile(target, profile):
    """Only remove this run's known files; never load or rewrite deployment profiles."""
    code = """
import re, sys
from pathlib import Path
profile = sys.argv[1]
assert re.fullmatch(r'jm[0-9a-f]{8}', profile)
root = Path('/etc/jasmin/store')
for suffix in ('router-groups','router-users','router-mointerceptors','router-mtinterceptors','router-moroutes','router-mtroutes','smppccs'):
    (root / (profile + '.' + suffix)).unlink(missing_ok=True)
for suffix in ('router-groups','router-users'):
    path = root / ('jcli-prod.' + suffix)
    if path.exists() and profile.encode() in path.read_bytes():
        raise RuntimeError('Jasmin auto-persisted a test object; deployment profile requires cleanup: ' + str(path))
"""
    command = shlex.join(['sudo', '-n', 'python3', '-c', code, profile])
    subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', target, command], check=True, timeout=30)


def main():
    ssh_target = os.environ.get('LIVE_SSH_TARGET')
    uid = 'jm' + secrets.token_hex(4)
    secret = secrets.token_hex(4)
    token = secrets.token_urlsafe(32)
    smsc = SMSC(('127.0.0.1', 27750), SMPP)
    smsc.system_id, smsc.password = uid, secret
    smsc.bound, smsc.submitted, smsc.mo_acked = threading.Event(), threading.Event(), threading.Event()
    smsc.submits = []
    callback = ThreadingHTTPServer(('127.0.0.1', 28081), Callback)
    callback.received, callback.messages = threading.Event(), []
    for service in (smsc, callback): threading.Thread(target=service.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    app = subprocess.Popen([sys.executable,'-m','manager.server','--port',str(port)],env={**os.environ,'MANAGER_TOKEN':token},stdout=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    session = requests.Session()
    session.headers.update({'Authorization':'Bearer '+token,'X-Jasmin-Manager':'1'})
    cleanup, report = [], {'test_id':uid,'checks':[]}
    baseline = None
    def call(path, data=None, method='POST', expected=200):
        response = session.request(method,base+'/api/'+path,json=data,timeout=90)
        assert response.status_code == expected, f'{method} {path}: {response.status_code}: {response.text}'
        return response.json()
    def snapshot(): return call('state',method='GET')
    def checkpoint(message): report['checks'].append(message); print('PASS',message,flush=True)
    def provision(path, data, removal):
        # Record cleanup before requesting: a remote operation may finish even if HTTP fails.
        cleanup.append(removal)
        call(path,data)
    try:
        for _ in range(100):
            try: requests.get(base,timeout=.2); break
            except requests.ConnectionError: time.sleep(.05)
        catalog = call('gateways', method='GET')
        selected = os.getenv('LIVE_GATEWAY_ID')
        if selected is None and len(catalog['gateways']) == 1:
            selected = catalog['default']
        assert selected in [g['id'] for g in catalog['gateways']], 'Set LIVE_GATEWAY_ID to the intended test gateway profile.'
        session.headers['X-Jasmin-Gateway'] = selected
        report['gateway_id'] = selected
        baseline = snapshot()
        orders = {r['order'] for routes in baseline['routes'].values() for r in routes}
        order = max(orders|{10000})+1
        report['baseline'] = {k:len(baseline[k]) for k in ('users','groups','connectors')}
        checkpoint('Read existing gateway configuration through the live web API')
        provision('groups',{'gid':uid},'groups/'+uid)
        provision('users',dict(uid=uid,gid=uid,username=uid,password=secret,balance=10,submit_sm_count=20),'users/'+uid)
        for kind in ('groups','users'):
            call(f'{kind}/{uid}/disable')
            items = snapshot()[kind]; key = 'gid' if kind=='groups' else 'uid'
            assert next(x for x in items if x[key]==uid)['enabled'] is False
            call(f'{kind}/{uid}/enable')
        call(f'users/{uid}/quotas',{'balance':20,'submit_sm_count':25,'http_throughput':5,'smpps_throughput':5})
        assert next(u for u in snapshot()['users'] if u['uid']==uid)['balance']==20
        checkpoint('Create groups/users, enable/disable both, update messaging quotas')
        provision('connectors',dict(id=uid,host='127.0.0.1',port=27750,username=uid,password=secret,throughput=10),'connectors/'+uid)
        provision('routes/mt',dict(order=order,type='Static',rate=.01,connectors=[{'id':uid}],filters=[{'type':'User','value':uid}]),f'routes/mt/{order}')
        provision('routes/mo',dict(order=order,type='Static',connectors=[{'id':uid,'type':'http','url':'http://127.0.0.1:28081/inbound','method':'POST'}],filters=[{'type':'Connector','value':uid}]),f'routes/mo/{order}')
        call(f'connectors/{uid}',method='DELETE',expected=400)
        call(f'users/{uid}',method='DELETE',expected=400)
        checkpoint('Create isolated MT/MO routes and reject deletion of referenced objects')
        current=snapshot()
        user=next(u for u in current['users'] if u['uid']==uid)
        call(f'users/{uid}/edit',dict(username=uid+'_u',gid=uid,password='',revision=user['revision']))
        connection=next(c for c in current['connectors'] if c['id']==uid)
        call(f'connectors/{uid}/edit',dict(host='127.0.0.1',port=27750,username=uid,password='',throughput=17,bindOperation='transceiver',revision=connection['revision']))
        current=snapshot()
        assert next(c for c in current['connectors'] if c['id']==uid)['throughput']==17
        assert next(u for u in current['users'] if u['uid']==uid)['username']==uid+'_u'
        checkpoint('Edit user identity and stopped connector while retaining credentials and route references')
        call(f'connectors/{uid}/start')
        wait_until(lambda: smsc.bound.is_set(),'SMPP bind was not received')
        wait_until(lambda: next(c for c in snapshot()['connectors'] if c['id']==uid)['session_state']=='BOUND_TRX','Connector did not become BOUND_TRX')
        checkpoint('Start real Jasmin SMPP connector and establish transceiver bind')
        # Only this test user matches the high-priority MT route to the simulator.
        sent = requests.post('http://127.0.0.1:11401/send',data={'username':uid+'_u','password':secret,'to':'995555000001','from':'JasminTest','content':'manager-live-mt'},timeout=20)
        assert sent.status_code == 200 and sent.text.startswith('Success'), sent.text
        assert smsc.submitted.wait(15), 'No submit_sm received by test SMSC'
        assert b'manager-live-mt' in smsc.submits[-1]
        checkpoint('HTTP send → live MT route → SMPP submit_sm → successful response')
        message = b'manager-live-mo'
        body = b'\0'+bytes([1,1])+b'995555000001\0'+bytes([1,1])+b'995555000002\0'+bytes([0,0,0])+b'\0\0'+bytes([0,0,0,0,len(message)])+message
        smsc.connection.sendall(struct.pack('>IIII',16+len(body),5,0,9001)+body)
        assert smsc.mo_acked.wait(15) and smsc.mo_status==0, 'MO deliver_sm was not acknowledged'
        assert callback.received.wait(20), 'MO HTTP callback not received'
        assert any('manager-live-mo' in str(item) for item in callback.messages), callback.messages
        checkpoint('SMPP deliver_sm → live MO route → HTTP callback with expected message')
        # Persist under a unique profile; never overwrite the deployment profile.
        if ssh_target:
            report['temporary_profile'] = uid
            call('persist',{'profile':uid})
            checkpoint('Persist both PB services to a unique test profile')
        else:
            print('SKIP persistence: set LIVE_SSH_TARGET to allow automatic profile cleanup.', flush=True)
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.add_init_script('sessionStorage.setItem("jasmin-gateway", '+json.dumps(selected)+');')
            page.goto(base);page.locator('#logout').click();page.locator('#token').fill(token);page.locator('#login-form [type="submit"]').click()
            expect(page.locator('#mode')).to_have_text('Live gateway',timeout=30000)
            page.locator('nav [data-page="connectors"]').click()
            page.locator('#search').fill(uid)
            expect(page.locator('tbody tr:visible')).to_contain_text('BOUND_TRX')
            for section in ('users','groups','mt','mo','overview'):
                page.locator(f'nav [data-page="{section}"]').click()
            assert not errors, errors
            browser.close()
        checkpoint('Authenticated browser dashboard renders live accounts, connectors and routes')
        call(f'connectors/{uid}/stop')
        assert next(c for c in snapshot()['connectors'] if c['id']==uid)['service_status']==0
        checkpoint('Stop connector and confirm service state')
    finally:
        cleanup_errors=[]
        for path in reversed(cleanup):
            try: call(path,method='DELETE')
            except Exception as error: cleanup_errors.append(f'{path}: {error}')
        if baseline is not None:
            try:
                final=snapshot()
                def configuration(state):
                    return {'users':sorted((u['uid'],u['gid'],u['username'],u['enabled']) for u in state['users']),
                            'groups':sorted((g['gid'],g['enabled']) for g in state['groups']),
                            'connectors':sorted(state['connectors'],key=lambda c:c['id']),
                            'routes':state['routes']}
                assert configuration(final)==configuration(baseline), 'Gateway inventory differs from baseline after cleanup'
                checkpoint('Remove all temporary objects; existing accounts, connectors and routes match baseline')
            except Exception as error: cleanup_errors.append(str(error))
        if ssh_target:
            try:
                remove_test_profile(ssh_target, uid)
                report['temporary_profile_removed'] = True
                checkpoint('Remove temporary profile files and check deployment profile for test objects')
            except Exception as error: cleanup_errors.append(str(error))
        app.terminate();app.wait(timeout=5)
        for service in (smsc,callback): service.shutdown();service.server_close()
        report['cleanup_errors']=cleanup_errors
        Path('artifacts').mkdir(exist_ok=True)
        Path('artifacts/live-test.json').write_text(json.dumps(report,indent=2)+'\n')
        if cleanup_errors: raise RuntimeError('Cleanup failed: '+'; '.join(cleanup_errors))


if __name__=='__main__':main()
