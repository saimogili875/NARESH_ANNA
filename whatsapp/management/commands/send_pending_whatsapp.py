import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from whatsapp.models import PendingMessage
from whatsapp.services import send_whatsapp_text

logger = logging.getLogger('whatsapp_sender')


class Command(BaseCommand):
    help = "Send pending WhatsApp messages via Meta Cloud API."

    def add_arguments(self, parser):
        default_batch = getattr(settings, 'WHATSAPP_BATCH_SIZE', 50)
        parser.add_argument('--batch-size', type=int, default=default_batch)

    def handle(self, *args, **options):
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  Sri NRI — Meta WhatsApp Cloud API Sender"))
        self.stdout.write(self.style.SUCCESS(f"  Batch size: {batch_size}"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        pending = list(
            PendingMessage.objects.filter(
                status=PendingMessage.STATUS_PENDING
            ).order_by('created_at')[:batch_size]
        )

        if not pending:
            self.stdout.write("No pending messages. Exiting.")
            return

        self.stdout.write(f"\nProcessing {len(pending)} message(s)...")

        sent = 0
        failed = 0

        for msg in pending:
            recipient = (
                msg.faculty.name if msg.faculty
                else (msg.student.name if msg.student else "Unknown")
            )
            phone = (msg.phone or "").strip()

            if not phone:
                msg.status = PendingMessage.STATUS_FAILED
                msg.error_message = "No phone number"
                msg.save()
                self.stdout.write(self.style.ERROR(f"  FAIL: {recipient} — no phone"))
                failed += 1
                continue

            result = send_whatsapp_text(to_number=phone, message=msg.message)

            if result["success"]:
                msg.status = PendingMessage.STATUS_SENT
                msg.error_message = ""
                msg.save()
                self.stdout.write(self.style.SUCCESS(f"  SENT: {recipient} ({phone})"))
                sent += 1
            else:
                msg.status = PendingMessage.STATUS_FAILED
                msg.error_message = result.get("error", "Unknown error")
                msg.save()
                self.stdout.write(self.style.ERROR(f"  FAIL: {recipient} — {result.get('error', '')}"))
                failed += 1

        summary = f"Done: {sent} sent, {failed} failed out of {len(pending)}."
        self.stdout.write(self.style.SUCCESS(f"\n{summary}"))
        logger.info(summary)
