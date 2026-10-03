import argparse
import hmac
import json
import os
from pathlib import Path
from twisted.internet import reactor
from twisted.web import resource, server, static
from manager.gateway import Gateway
from manager.config import load_profiles


class API(resource.Resource):
    isLeaf = True

    def __init__(self, gateway, token, profiles=None, default="default"):
        super().__init__()
        self.gateways = gateway if isinstance(gateway, dict) else {'default': gateway}
        self.token = token
        self.default = default
        self.profiles = profiles or {'default': {'id': 'default', 'name': 'Default gateway', 'host': '127.0.0.1'}}

    def render(self, request):
        request.setHeader(b'content-type', b'application/json; charset=utf-8')
        request.setHeader(b'cache-control', b'no-store')
        request.setHeader(b'x-content-type-options', b'nosniff')
        auth = request.getHeader('authorization') or ''
        if self.token and not hmac.compare_digest(auth.encode(), ('Bearer ' + self.token).encode()):
            request.setResponseCode(401)
            return b'{"error":"Enter the manager admin token to connect."}'
        if request.method not in (b'GET', b'POST', b'DELETE'):
            request.setResponseCode(405)
            return b'{"error":"Method not allowed."}'
        if request.method != b'GET' and request.getHeader('x-jasmin-manager') != '1':
            request.setResponseCode(403)
            return b'{"error":"Missing management request header."}'
        try:
            raw = request.content.read(65537)
            if len(raw) > 65536:
                raise ValueError('Request is too large.')
            data = json.loads(raw) if raw else {}
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            path = [part.decode() for part in request.postpath if part]
        except (ValueError, UnicodeError):
            request.setResponseCode(400)
            return b'{"error":"Invalid JSON request (maximum 64 KiB)."}'
        if request.method == b'GET' and path == ['gateways']:
            return json.dumps({'default': self.default, 'gateways': [
                {key: profile[key] for key in ('id', 'name', 'host')} for profile in self.profiles.values()
            ]}).encode()
        gateway_id = request.getHeader('x-jasmin-gateway')
        if gateway_id is None and len(self.gateways) == 1:
            gateway_id = self.default
        if gateway_id not in self.gateways:
            request.setResponseCode(400)
            return b'{"error":"Select a configured Jasmin gateway before continuing."}'
        gateway = self.gateways[gateway_id]
        def success(result):
            if path == ['state']:
                result['gateway_id'] = gateway_id
            if not request._disconnected:
                request.write(json.dumps(result).encode())
                request.finish()
        def failure(err):
            if not request._disconnected:
                validation = isinstance(err.value, (ValueError, KeyError, TypeError)) or err.value.__class__.__module__.startswith('jasmin.routing') or err.value.__class__.__module__ == 'jasmin.protocols.smpp.configs'
                request.setResponseCode(400 if validation else 502)
                message = str(err.value) if validation else 'Gateway operation failed or timed out. Check PB connectivity and credentials; refresh to verify the outcome before retrying.'
                if isinstance(err.value, RuntimeError): message = str(err.value)
                request.write(json.dumps({'error': message}).encode())
                request.finish()
        gateway.execute(request.method.decode(), path, data).addCallbacks(success, failure)
        return server.NOT_DONE_YET


class SecureSite(server.Site):
    def getResourceFor(self, request):
        request.setHeader(b'content-security-policy', b"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        request.setHeader(b'x-content-type-options', b'nosniff')
        request.setHeader(b'referrer-policy', b'no-referrer')
        return super().getResourceFor(request)


def main():
    parser = argparse.ArgumentParser(description='Jasmin gateway web manager')
    parser.add_argument('--demo', action='store_true', help='In-memory demonstration; never connects to Jasmin')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    token = os.getenv('MANAGER_TOKEN', '')
    try:
        profiles, default = load_profiles(args.demo)
    except (ValueError, TypeError) as error:
        parser.error(str(error))
    if not args.demo and len(token) < 24:
        parser.error('Live mode requires MANAGER_TOKEN (24+ characters).')
    if args.demo and args.host not in ('127.0.0.1', '::1') and len(token) < 24:
        parser.error('A non-local demo requires MANAGER_TOKEN (24+ characters).')
    root = static.File(str(Path(__file__).parent / 'static'))
    gateways = {gid: Gateway(args.demo, profile['settings']) for gid, profile in profiles.items()}
    root.putChild(b'api', API(gateways, token, profiles, default))
    reactor.listenTCP(args.port, SecureSite(root), interface=args.host)
    print(f'Jasmin Manager: http://{args.host}:{args.port} ({"DEMO — ephemeral data" if args.demo else "LIVE"})', flush=True)
    reactor.run()


if __name__ == '__main__':
    main()
