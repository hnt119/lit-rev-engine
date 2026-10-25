#!/usr/bin/env python3
"""Local-only TLS ingress for deployment tests, never a production proxy.

Use a generated test certificate; no trust-store/browser settings are changed.
Only loopback bind/upstream are supported. Incoming forwarding headers are
removed, and Host/proto are set to the one configured application origin.
This simulates the intended managed ingress boundary without claiming Render
execution or real hosted-domain verification.
"""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
from urllib.parse import urlsplit

HOP = {'connection', 'transfer-encoding', 'keep-alive', 'te', 'trailer', 'upgrade', 'proxy-authenticate', 'proxy-authorization'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--upstream-port', required=True, type=int)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    args = parser.parse_args(); origin = urlsplit(args.origin)
    if origin.scheme != 'https' or not origin.hostname.endswith('.test') or origin.port != args.port:
        parser.error('Use the exact HTTPS .test origin and TLS port.')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *values):
            pass
        def forward(self):
            # Preserve the actual Host so the application can reject an invalid
            # request; a managed ingress must not convert a foreign host to valid.
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in HOP and not name.lower().startswith('x-forwarded-')}
            headers['X-Forwarded-Proto'] = 'https'
            headers['X-Forwarded-Host'] = self.headers.get('Host', '')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > 6 * 1024 * 1024:
                    raise ValueError
            except ValueError:
                self.send_error(413); return
            def incoming():
                remaining = length
                first = True
                while remaining:
                    chunk = self.rfile.read(1 if first else min(65536, remaining))
                    first = False
                    if not chunk:
                        raise OSError('Truncated test request body')
                    remaining -= len(chunk)
                    yield chunk
            body = incoming() if length else None
            upstream = http.client.HTTPConnection('127.0.0.1', args.upstream_port, timeout=180)
            try:
                upstream.request(self.command, self.path, body=body, headers=headers)
                response = upstream.getresponse(); data = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in HOP | {'content-length', 'server', 'date'}:
                        self.send_header(name, value)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if self.command != 'HEAD': self.wfile.write(data)
            except (OSError, http.client.HTTPException):
                data = b'{"status":"unavailable"}'
                self.send_response(503); self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(data)
            finally:
                upstream.close()
        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = forward

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(json.dumps({'local_https_test_ingress': args.port, 'upstream_loopback_port': args.upstream_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
