"""Windows-only owned launch entry point for the existing Uvicorn app."""
import argparse
import os
import signal


def main():
    if os.name != 'nt': raise RuntimeError('This entry point is Windows-only.')
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('Use an unprivileged local port.')
    server = uvicorn.Server(uvicorn.Config('src.web_api.app:app_factory', factory=True,
        host='127.0.0.1', port=args.port, workers=1, access_log=False,
        proxy_headers=False, timeout_graceful_shutdown=10))
    previous = signal.signal(signal.SIGBREAK, lambda *_: setattr(server, 'should_exit', True))
    try: server.run()
    finally: signal.signal(signal.SIGBREAK, previous)


if __name__ == '__main__': main()
