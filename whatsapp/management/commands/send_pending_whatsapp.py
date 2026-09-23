import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from whatsapp.models import PendingMessage
from whatsapp.services import send_whatsapp_text, send_whatsapp_template, build_template_components, send_generic_template

logger = logging.getLogger('whatsapp_sender')


class Command(BaseCommand):
    help = "Send pending WhatsApp messages via Meta Cloud API using Templates or Text."

    def add_arguments(self, parser):
        default_batch = getattr(settings, 'WHATSAPP_BATCH_SIZE', 50)
        parser.add_argument('--batch-size', type=int, default=default_batch)

    def handle(self, *args, **options):
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  Sri NRI — Meta WhatsApp Cloud API Sender"))
        self.stdout.write(self.style.SUCCESS(f"  Batch size: {batch_size}"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        from django.db import transaction
        with transaction.atomic():
            pending_ids = list(
                PendingMessage.objects.select_for_update(skip_locked=True)
                .filter(status=PendingMessage.STATUS_PENDING)
                .order_by('created_at')
                .values_list('id', flat=True)[:batch_size]
            )
            if not pending_ids:
                self.stdout.write("No pending messages. Exiting.")
                return
            PendingMessage.objects.filter(id__in=pending_ids).update(status=PendingMessage.STATUS_PROCESSING)

        pending = list(PendingMessage.objects.filter(id__in=pending_ids).order_by('created_at'))

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

            # Dispatch via Template or Text based on message_type
            if getattr(msg, 'message_type', 'template') == PendingMessage.TYPE_TEMPLATE:
                template_name = msg.template_name or getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
                params = msg.template_params or [msg.message]
                components = build_template_components(params)
                language = msg.language or getattr(settings, 'WHATSAPP_DEFAULT_LANGUAGE', 'en')
                result = send_whatsapp_template(
                    to_number=phone,
                    template_name=template_name,
                    language=language,
                    components=components
                )
                gen_template = getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
                if not result["success"] and template_name != gen_template:
                    self.stdout.write(self.style.WARNING(f"  RETRYING: {recipient} ({phone}) via fallback template '{gen_template}'..."))
                    gen_components = build_template_components([msg.message])
                    result = send_whatsapp_template(
                        to_number=phone,
                        template_name=gen_template,
                        language=language,
                        components=gen_components
                    )
            else:
                result = send_whatsapp_text(to_number=phone, message=msg.message)

            if result["success"]:
                msg.status = PendingMessage.STATUS_SENT
                msg.wamid = result.get("wamid") or result.get("message_id") or ""
                msg.error_message = ""
                msg.save()
                self.stdout.write(self.style.SUCCESS(f"  SENT: {recipient} ({phone}) via {getattr(msg, 'message_type', 'template')}"))
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
