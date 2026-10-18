"""Verified HTTP transport with credential-safe redirects."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.error import HTTPError


def _origin(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), (parsed.hostname or '').lower(),
            parsed.port or (443 if parsed.scheme.lower() == 'https' else 80))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        old_origin, new_origin = _origin(request.full_url), _origin(new_url)
        if new_origin[0] not in ('http', 'https') or (old_origin[0] == 'https' and new_origin[0] != 'https'):
            raise HTTPError(request.full_url, code, 'Unsafe redirect refused', headers, response)
        redirected = super(SafeRedirect, self).redirect_request(request, response, code, message, headers, new_url)
        if redirected is not None and old_origin != new_origin:
            # Preserve only explicitly public playback headers across origins.
            # This also removes custom token headers and headers placed in
            # unredirected_hdrs by authentication handlers.
            allowed = {'accept', 'accept-encoding', 'user-agent', 'range'}
            for collection in (redirected.headers, redirected.unredirected_hdrs):
                for name in list(collection):
                    if name.lower() not in allowed:
                        del collection[name]
        return redirected


def urlopen(request, timeout=30):
    return build_opener(SafeRedirect()).open(request, timeout=timeout)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def private_urlopen(request, timeout=30):
    return build_opener(NoRedirect()).open(request, timeout=timeout)
