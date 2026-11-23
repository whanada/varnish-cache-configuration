import http.client
import json
import os
import time
import unittest
import uuid

VARNISH = os.getenv('VARNISH_HOST', 'localhost')
TOKEN = uuid.uuid4().hex


def request(path, host='site.example.invalid', headers=None, method='GET', address=None, port=80):
    connection = http.client.HTTPConnection(address or VARNISH, port, timeout=5)
    connection.request(method, path, headers={'Host': host, **(headers or {})})
    response = connection.getresponse()
    body = response.read().decode()
    result = response.status, dict(response.getheaders()), body
    connection.close()
    return result


def header(headers, name):
    return next((v for k, v in headers.items() if k.lower() == name.lower()), None)


def origin(name, port, path):
    return request(path, address=name, port=port)


class Lab(unittest.TestCase):
    def path(self, base):
        return base + '?test=' + TOKEN + '-' + self._testMethodName

    def test_readiness(self):
        for name, port in [('site-01', 8080), ('site-02', 8081), ('api-01', 8082), ('images-01', 8083)]:
            self.assertEqual(origin(name, port, '/health')[0], 200, name)

    def test_routing_and_distribution(self):
        for host, path, expected in [('api.example.invalid', '/api/example', 'api'), ('site.example.invalid', '/api/example', 'api'), ('images.example.invalid', '/public/test.json', 'images'), ('site.example.invalid', '/health', 'site')]:
            status, h, _ = request(self.path(path), host)
            self.assertEqual((status, header(h, 'X-Origin-Type')), (200, expected), (host, h))
        seen = set()
        for i in range(8):
            _, h, _ = request(self.path('/health') + '&n=' + str(i))
            seen.add(header(h, 'X-Origin-Server'))
        self.assertEqual(seen, {'site-01', 'site-02'})

    def test_cache_keys_and_origin_counts(self):
        path = self.path('/public/test.css')
        before = json.loads(origin('api-01', 8082, '/__control/count')[2]).get(path, 0)
        first = request(path, 'api.example.invalid')
        second = request(path, 'api.example.invalid')
        self.assertEqual(header(first[1], 'X-Cache'), 'MISS')
        self.assertEqual(header(second[1], 'X-Cache'), 'HIT')
        self.assertEqual(json.loads(origin('api-01', 8082, '/__control/count')[2]).get(path, 0) - before, 1)
        self.assertEqual(header(request(path + '&different=1', 'api.example.invalid')[1], 'X-Cache'), 'MISS')
        other = request(path, 'images.example.invalid')
        self.assertEqual((header(other[1], 'X-Cache'), header(other[1], 'X-Origin-Type')), ('MISS', 'images'))
        self.assertEqual(header(first[1], 'Cache-Control'), 'public, max-age=60')
        self.assertIsNotNone(header(second[1], 'Age'))
        for name in ('X-Powered-By', 'X-Drupal-Cache', 'X-Generator', 'X-AspNet-Version'):
            self.assertIsNone(header(second[1], name), name)
        print('Observed cache response headers:', second[1], flush=True)

    def test_private_cookie_and_authorization(self):
        path = self.path('/private')
        for user in ('alice', 'bob'):
            status, _, body = request(path, headers={'Cookie': 'user=' + user})
            self.assertEqual((status, body), (200, 'private:user=' + user))
        public_request_path = self.path('/private') + '&no-cookie=1'
        for _ in range(2):
            self.assertNotEqual(header(request(public_request_path)[1], 'X-Cache'), 'HIT')
        path = self.path('/authenticated')
        for user in ('alice', 'bob'):
            self.assertEqual(request(path, headers={'Authorization': 'Bearer ' + user})[2], 'auth:Bearer ' + user)
        path = self.path('/cookie')
        for _ in range(2):
            _, h, _ = request(path, 'api.example.invalid')
            self.assertIsNotNone(header(h, 'Set-Cookie'))
            self.assertNotEqual(header(h, 'X-Cache'), 'HIT')

    def test_vary_and_esi(self):
        path = self.path('/vary')
        for language in ('en', 'fr'):
            _, h, body = request(path, headers={'Accept-Language': language})
            self.assertEqual(body, language)
            self.assertEqual(header(h, 'Vary'), 'Accept-Language')
        _, h, body = request(self.path('/esi'))
        self.assertIn('before fragment after', body)
        self.assertIsNone(header(h, 'Surrogate-Control'))
        self.assertIn('<esi:include', request(self.path('/esi-off'))[2])

    def test_invalidation(self):
        path = self.path('/public/test.json')
        request(path)
        for method in ('PURGE', 'BAN'):
            self.assertEqual(request(path, method=method)[0], 405)
        self.assertEqual(header(request(path)[1], 'X-Cache'), 'HIT')

    def test_ttl_and_grace(self):
        path = self.path('/short')
        first = request(path, 'api.example.invalid')
        self.assertEqual(header(request(path, 'api.example.invalid')[1], 'X-Cache'), 'HIT')
        time.sleep(3)
        # Grace may serve stale immediately while a background refresh runs.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = request(path, 'api.example.invalid')
            if current[2] != first[2]:
                break
            time.sleep(0.3)
        self.assertNotEqual(current[2], first[2], 'expired object was not refreshed')
        private_path = self.path('/private')
        self.assertEqual(request(private_path, 'api.example.invalid', headers={'Cookie': 'user=alice'})[0], 200)
        origin('api-01', 8082, '/__control/fail')
        try:
            time.sleep(3)
            stale = request(path, 'api.example.invalid')
            self.assertEqual((stale[0], stale[2]), (200, current[2]), 'expected stale response during backend failure')
            private = request(private_path, 'api.example.invalid', headers={'Cookie': 'user=alice'})
            self.assertEqual(private[0], 503)
        finally:
            origin('api-01', 8082, '/__control/recover')

    def test_error(self):
        self.assertEqual(request(self.path('/error'), 'api.example.invalid')[0], 500)


if __name__ == '__main__':
    deadline = time.monotonic() + 60
    while True:
        try:
            if request('/health')[0] == 200:
                break
        except (OSError, http.client.HTTPException):
            pass
        if time.monotonic() >= deadline:
            raise SystemExit('Varnish did not become ready within 60 seconds')
        time.sleep(1)
    unittest.main(verbosity=2)
