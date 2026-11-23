#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose config -q
docker compose up -d --build varnish
# Static VCL backends resolve DNS at load time; refresh after origin recreation.
docker compose up -d --force-recreate --no-deps varnish
docker compose exec -T varnish varnishd -C -f /etc/varnish/default.vcl 2>/tmp/varnish-vcl-compile.log || { cat /tmp/varnish-vcl-compile.log; exit 1; }
docker compose run --rm test-runner
