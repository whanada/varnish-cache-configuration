vcl 4.1;

import directors;

# TEMPLATE: replace all example addresses, ports, domains, and paths.
# These values do not describe your infrastructure and are not production-ready.
# Naming convention: backend_<role>_<number> and pool_<role>.

# 1. BACKENDS: define one block for each server or instance.
# The application must accept the probe Host and return 200 for its path.
# The probe is disabled until the health endpoint is configured.
# probe probe_padrao {
#     .url = "/health";
#     .interval = 5s;
#     .timeout = 1s;
#     .window = 5;
#     .threshold = 3;
# }

backend backend_site_01 {
    .host = "127.0.0.1";       # Replace with the origin IP or DNS name.
    .port = "8080";            # Origin port; must differ from the Varnish listener.
    .max_connections = 300;     # Adjust to the origin capacity.
    .connect_timeout = 5s;
    .first_byte_timeout = 300s;
    .between_bytes_timeout = 2s;
    # .probe = probe_padrao;     # Enable after configuring /health.
}
backend backend_site_02 {
    .host = "127.0.0.1";
    .port = "8081";
    .max_connections = 300;
    .connect_timeout = 5s;
    .first_byte_timeout = 300s;
    .between_bytes_timeout = 2s;
    # .probe = probe_padrao;
}
backend backend_api_01 {
    .host = "127.0.0.1";
    .port = "8082";
    .max_connections = 300;
    .connect_timeout = 5s;
    .first_byte_timeout = 300s;
    .between_bytes_timeout = 2s;
    # .probe = probe_padrao;
}
backend backend_imagens_01 {
    .host = "127.0.0.1";
    .port = "8083";
    .max_connections = 300;
    .connect_timeout = 5s;
    .first_byte_timeout = 300s;
    .between_bytes_timeout = 2s;
    # .probe = probe_padrao;
}

# 2. DIRECTORS: group only equivalent servers that serve the same content.
sub vcl_init {
    new pool_site = directors.round_robin();
    pool_site.add_backend(backend_site_01);
    pool_site.add_backend(backend_site_02);
    new pool_api = directors.round_robin();
    pool_api.add_backend(backend_api_01);
    new pool_imagens = directors.round_robin();
    pool_imagens.add_backend(backend_imagens_01);
}

# 3. INVALIDATION: configure trusted networks before enabling PURGE.
# The ACL and PURGE block are commented out; BAN remains disabled.
# acl acl_invalida {
#     "127.0.0.1";
#     "::1";
#     # "192.0.2.0"/24; # Example: replace with your network.
# }

# Remove the Proxy header before forwarding requests to an origin.
sub request_sanitize {
    unset req.http.proxy;
}

# Select an origin pool based on the request host and URL.
sub request_route {
    # 4. ROUTING: replace the fictional reserved .invalid domains.
    # Order matters: API and images are evaluated before the default.
    set req.backend_hint = pool_site.backend();
    if (req.http.host ~ "(?i)^api[.]exemplo[.]invalid(:[0-9]+)?$" ||
        (req.http.host ~ "(?i)^site[.]exemplo[.]invalid(:[0-9]+)?$" &&
         req.url ~ "^/api/")) {
        set req.backend_hint = pool_api.backend();
    } elseif (req.http.host ~ "(?i)^imagens[.]exemplo[.]invalid(:[0-9]+)?$") {
        set req.backend_hint = pool_imagens.backend();
    }
    # Example of routing by domain and path, as in the original CDN:
    # elseif (req.http.host ~ "(?i)^cdn[.]exemplo[.]invalid(:[0-9]+)?$" &&
    #         req.url ~ "^/cliente-ficticio/imagens/") {
    #     set req.backend_hint = pool_imagens.backend();
    # }

}

# Reject cache invalidation until a trusted-client policy is configured.
sub request_invalidation {
    # To enable PURGE, configure acl_invalida, uncomment this block, and change
    # the block below to reject only BAN. Check client.ip when using proxies.
    # if (req.method == "PURGE") {
    #     if (client.ip !~ acl_invalida) {
    #         return (synth(403, "Forbidden"));
    #     }
    #     return (purge);
    # }
    if (req.method == "PURGE" || req.method == "BAN") {
        return (synth(405, "Invalidation not configured"));
    }

}

# Advertise ESI and document optional public-asset cookie handling.
sub request_cache_policy {
    # 5. ESI AND CACHE: built-in VCL handles methods, Authorization, and Cookie.
    # Do not remove cookies or force hash without verifying the content is public.
    set req.http.Surrogate-Capability = "key=ESI/1.0";
    # OPTIONAL example: only for public files verified to be identical
    # for every user, including when a cookie is present:
    # if (req.method == "GET" && !req.http.Authorization &&
    #     req.url ~ "(?i)^/publico/.*[.](css|js|jpg|jpeg|png|gif|svg|ico|woff2?)([?].*)?$") {
    #     unset req.http.Cookie;
    # }
}

# Process each request in order; built-in VCL handles remaining decisions.
sub vcl_recv {
    call request_sanitize;
    call request_route;
    call request_invalidation;
    call request_cache_policy;
}

# 6. HASH: built-in VCL already includes the URL and Host. Add only
# necessary dimensions here; do not repeat the built-in fields.
sub vcl_hash {
    # Example: hash_data(req.http.X-Trusted-Variant);
}

sub vcl_hit {
    # Built-in VCL handles fresh objects, grace, and background refresh.
}
sub vcl_miss {
    # Built-in VCL fetches the object from the origin.
}

# Enable ESI processing only when the origin explicitly requests it.
sub response_enable_esi {
    if (beresp.http.Surrogate-Control ~ "ESI/1.0") {
        unset beresp.http.Surrogate-Control;
        set beresp.do_esi = true;
    }
}

# Set grace and provide optional TTL examples for verified public content.
sub response_cache_policy {
    set beresp.grace = 6h;
    # OPTIONAL TTL examples from the original file. Enable only for verified
    # public routes; built-in VCL still checks Set-Cookie and Cache-Control.
    # if (beresp.status == 200 && beresp.ttl > 0s) {
    #     if (bereq.url ~ "^/publico/.*[.](jpg|jpeg|png|gif|svg|ico)([?].*)?$") {
    #         set beresp.ttl = 1w;
    #     } elseif (bereq.url ~ "^/publico/.*[.](css|js|woff2?)([?].*)?$") {
    #         set beresp.ttl = 10d;
    #     } elseif (bereq.url ~ "^/publico/.*[.]xml([?].*)?$") {
    #         set beresp.ttl = 1d;
    #     } elseif (bereq.url ~ "^/api/publica/") {
    #         set beresp.ttl = 2h;
    #         set beresp.grace = 2h;
    #     }
    # }
    # Built-in VCL handles origin errors and headers.
}

# Apply backend response policies before built-in cacheability checks.
sub vcl_backend_response {
    call response_enable_esi;
    call response_cache_policy;
}

# Add a cache diagnostic and remove selected origin technology headers.
sub response_delivery_headers {
    if (obj.hits > 0) {
        set resp.http.X-Cache = "HIT";
    } else {
        set resp.http.X-Cache = "MISS";
    }
    unset resp.http.X-Powered-By;
    unset resp.http.X-Drupal-Cache;
    unset resp.http.X-Generator;
    unset resp.http.X-AspNet-Version;
}

# Prepare response headers before delivering the response to the client.
# Configure CORS at the origin with real origins, preflight, and Vary: Origin.
sub vcl_deliver {
    call response_delivery_headers;
}

sub vcl_purge {
    # Built-in VCL responds to PURGE; do not restart by default.
}
sub vcl_synth {
    # Customize synthetic messages or redirects here if needed.
}
sub vcl_fini {
    # Varnish releases the directors.
}
