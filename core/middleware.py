import ipaddress
import logging

from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger("ip_whitelist")


class IPWhitelistMiddleware:
    """Block requests from IPs not in ALLOWED_CLIENT_IPS."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = self._parse_networks(getattr(settings, "ALLOWED_CLIENT_IPS", []))
        self.exempt_paths = set(getattr(settings, "IP_WHITELIST_EXEMPT_PATHS", []))

    @staticmethod
    def _parse_networks(raw_list):
        networks = []
        for entry in raw_list:
            entry = entry.strip()
            if not entry:
                continue
            try:
                networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                logger.warning("Invalid IP/CIDR in ALLOWED_CLIENT_IPS: %s", entry)
        return networks

    def _get_client_ip(self, request):
        # Render sets HTTP_TRUE_CLIENT_IP via Cloudflare
        ip = request.META.get("HTTP_TRUE_CLIENT_IP", "").strip()
        if ip:
            return ip
        # Fall back to first entry in X-Forwarded-For
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            return xff.split(",")[0].strip()
        # Local / dev fallback
        return request.META.get("REMOTE_ADDR", "")

    def __call__(self, request):
        # Skip if no whitelist configured (open access, e.g. local dev)
        if not self.networks:
            return self.get_response(request)

        # Skip exempt paths (health checks, etc.)
        if request.path in self.exempt_paths:
            return self.get_response(request)

        client_ip_str = self._get_client_ip(request)
        try:
            client_ip = ipaddress.ip_address(client_ip_str)
        except ValueError:
            logger.warning("Unparseable client IP '%s' for %s — blocked", client_ip_str, request.path)
            return HttpResponseForbidden("Forbidden")

        for network in self.networks:
            if client_ip in network:
                return self.get_response(request)

        logger.warning("Blocked %s from %s", request.path, client_ip_str)
        return HttpResponseForbidden("Forbidden")
