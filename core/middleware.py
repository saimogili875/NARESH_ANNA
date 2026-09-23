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

        if self.networks and not getattr(settings, "TRUSTED_PROXY_IPS", []) and not getattr(settings, "DEBUG", False):
            logger.warning(
                "CRITICAL SECURITY WARNING: ALLOWED_CLIENT_IPS is non-empty, but TRUSTED_PROXY_IPS is empty when DEBUG=False. "
                "IP Whitelisting will fail behind reverse proxies like Render because REMOTE_ADDR is proxy IP."
            )

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
        remote_addr = request.META.get("REMOTE_ADDR", "").strip()
        trusted_proxies = getattr(settings, "TRUSTED_PROXY_IPS", [])

        # TODO: Needs infra-level confirmation for Render/Cloudflare trusted proxy IP ranges.
        # Only trust HTTP_TRUE_CLIENT_IP / X-Forwarded-For if REMOTE_ADDR is a confirmed trusted proxy.
        if trusted_proxies:
            is_trusted = False
            try:
                remote_ip = ipaddress.ip_address(remote_addr)
                is_trusted = any(remote_ip in ipaddress.ip_network(p, strict=False) for p in trusted_proxies)
            except ValueError:
                is_trusted = False

            if is_trusted:
                ip = request.META.get("HTTP_TRUE_CLIENT_IP", "").strip()
                if ip:
                    return ip
                xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
                if xff:
                    return xff.split(",")[0].strip()

        # Fallback to REMOTE_ADDR when immediate connecting peer cannot be confirmed as a trusted proxy
        return remote_addr


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
