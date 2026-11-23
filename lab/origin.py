import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

NAME = os.environ['ORIGIN_NAME']
KIND = os.environ['ORIGIN_TYPE']
PORT = int(os.environ['PORT'])
COUNTS = {}
FAIL = False

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        global FAIL
        path = urlsplit(self.path).path
        if path == '/__control/fail':
            FAIL = True
            return self.reply(200, b'failure enabled', 'no-store')
        if path == '/__control/recover':
            FAIL = False
            return self.reply(200, b'failure disabled', 'no-store')
        if path == '/__control/count':
            return self.reply(200, json.dumps(COUNTS).encode(), 'no-store')
        COUNTS[self.path] = COUNTS.get(self.path, 0) + 1
        if FAIL:
            return self.reply(503, b'origin unavailable', 'no-store')
        if path == '/error':
            return self.reply(500, b'origin error', 'no-store')
        if path == '/private':
            return self.reply(200, ('private:' + self.headers.get('Cookie', '')).encode(), 'private, no-store')
        if path == '/authenticated':
            return self.reply(200, ('auth:' + self.headers.get('Authorization', '')).encode(), 'private, no-store')
        if path == '/cookie':
            return self.reply(200, b'cookie response', 'public, max-age=60', {'Set-Cookie': 'session=example; HttpOnly'})
        if path == '/esi':
            return self.reply(200, b'<html>before <esi:include src="/fragment"/> after</html>', 'public, max-age=60', {'Surrogate-Control': 'content="ESI/1.0"'})
        if path == '/esi-off':
            return self.reply(200, b'<html>before <esi:include src="/fragment"/> after</html>', 'public, max-age=60')
        if path == '/fragment':
            return self.reply(200, b'fragment', 'public, max-age=60')
        if path == '/vary':
            return self.reply(200, self.headers.get('Accept-Language', 'none').encode(), 'public, max-age=60', {'Vary': 'Accept-Language'})
        if path == '/short':
            return self.reply(200, ('short:' + str(COUNTS[self.path])).encode(), 'public, max-age=2')
        payload = json.dumps({'origin': NAME, 'type': KIND, 'path': self.path}).encode()
        return self.reply(200, payload, 'public, max-age=60')

    def reply(self, status, data, cache, extra=None):
        self.send_response(status)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Content-Type', 'text/html' if urlsplit(self.path).path in ('/esi', '/esi-off', '/fragment') else 'text/plain')
        self.send_header('Cache-Control', cache)
        self.send_header('X-Origin-Server', NAME)
        self.send_header('X-Origin-Type', KIND)
        for header in ('X-Powered-By', 'X-Drupal-Cache', 'X-Generator', 'X-AspNet-Version'):
            self.send_header(header, 'remove-me')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
