import logging

from django.conf import settings
from django.core.mail import send_mail
from django.dispatch import receiver
from django.utils import timezone

from axes.signals import user_locked_out

logger = logging.getLogger("lockout")


@receiver(user_locked_out)
def send_lockout_notification(sender, request, username, ip_address, **kwargs):
    """Email alert when a user gets locked out by django-axes."""
    now = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z")
    recipient = getattr(settings, "LOCKOUT_NOTIFY_EMAIL", None)
    if not recipient:
        return

    subject = f"[Sri NRI Junior College] Login Lockout — {username} from {ip_address}"
    body = (
        f"A login lockout was triggered.\n\n"
        f"Username : {username}\n"
        f"IP       : {ip_address}\n"
        f"Time     : {now}\n"
        f"Failures : {settings.AXES_FAILURE_LIMIT} attempts exceeded\n"
        f"Cooloff  : {settings.AXES_COOLOFF_TIME} hours\n"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=True)
        logger.info("Lockout email sent for %s from %s", username, ip_address)
    except Exception as exc:
        logger.error("Failed to send lockout email: %s", exc)
