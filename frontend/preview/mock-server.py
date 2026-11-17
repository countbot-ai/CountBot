#!/usr/bin/env python3
"""预览沙盒的本地 mock：/api/* 一律返回空集合，让面板能渲染真实的空态。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if '/api/cron' in self.path:
            self._send({'jobs': []})
        elif '/api/wiki' in self.path:
            self._send({'entries': [], 'stats': None})
        elif '/api/sessions' in self.path:
            self._send([])
        else:
            self._send({})

    do_POST = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
