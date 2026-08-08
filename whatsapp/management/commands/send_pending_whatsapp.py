import time
import os
import json
import urllib.parse
import logging

# Allow Django ORM operations inside Playwright's sync event loop
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from django.core.management.base import BaseCommand
from django.conf import settings
from whatsapp.models import PendingMessage, WhatsAppSession

logger = logging.getLogger('whatsapp_sender')


def _normalize_phone_number(phone: str) -> str:
    """Format phone number for WhatsApp Web URL (e.g. 919876543210)."""
    if not phone:
        return ""
    phone = phone.strip()
    if phone.startswith("whatsapp:"):
        phone = phone[len("whatsapp:"):]
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    return digits


class Command(BaseCommand):
    help = "Batch WhatsApp message sender via Playwright with low-memory optimizations and DB session persistence."

    def add_arguments(self, parser):
        default_batch_size = getattr(settings, 'WHATSAPP_BATCH_SIZE', 50)
        parser.add_argument(
            '--batch-size',
            type=int,
            default=default_batch_size,
            help=f'Maximum number of pending messages to send per batch (default: {default_batch_size}).',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Backwards compatibility flag (batch mode always closes and exits after one pass).',
        )

        parser.add_argument(
            '--headless',
            type=str,
            default=None,
            help='Override HEADLESS_MODE setting (true/false).',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        headless_arg = options['headless']

        if headless_arg is not None:
            if isinstance(headless_arg, bool):
                headless = headless_arg
            else:
                headless = str(headless_arg).lower() in ['true', '1', 'yes']
        else:
            headless = getattr(settings, 'WHATSAPP_PLAYWRIGHT_HEADLESS', getattr(settings, 'HEADLESS_MODE', True))


        session_dir = getattr(settings, 'WHATSAPP_SESSION_DIR', settings.BASE_DIR / 'whatsapp_session')
        os.makedirs(session_dir, exist_ok=True)
        storage_state_file = session_dir / 'storage_state.json'

        # 1. Restore storage state from DB if local file is missing/wiped
        db_session = WhatsAppSession.objects.first()
        if db_session and db_session.session_data:
            try:
                with open(storage_state_file, 'w', encoding='utf-8') as f:
                    f.write(db_session.session_data)
                self.stdout.write(self.style.SUCCESS("✔ Restored WhatsApp Web storage state from Database."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not restore DB storage state: {e}"))

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("  Sri NRI Junior College — WhatsApp Playwright Low-Memory Sender"))
        self.stdout.write(self.style.SUCCESS(f"  Headless Mode: {headless}"))
        self.stdout.write(self.style.SUCCESS(f"  Batch Size: {batch_size}"))
        self.stdout.write(self.style.SUCCESS(f"  Session Directory: {session_dir}"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        # Query batch of pending messages
        pending_messages = list(
            PendingMessage.objects.filter(status=PendingMessage.STATUS_PENDING).order_by('created_at')[:batch_size]
        )

        if not pending_messages:
            self.stdout.write("No pending messages found. Exiting.")
            return

        self.stdout.write(f"\nProcessing batch of {len(pending_messages)} pending WhatsApp message(s)...")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.stderr.write(self.style.ERROR(
                "\nPlaywright package is not installed in Python environment!\n"
                "Please run: pip install playwright && playwright install chromium"
            ))
            return

        # Low-RAM Chromium launch arguments suited for 512MB hosts
        chromium_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--no-first-run",
            "--no-zygote",
        ]

        with sync_playwright() as p:
            self.stdout.write("Launching low-memory browser context...")
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(session_dir),
                    headless=headless,
                    args=chromium_args
                )
                if storage_state_file.exists():
                    try:
                        state_data = json.loads(storage_state_file.read_text(encoding='utf-8'))
                        cookies = state_data.get('cookies', [])
                        if cookies:
                            context.add_cookies(cookies)
                    except Exception:
                        pass
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"\nBrowser launch failed: {e}\n"
                    "If browser is missing, run: playwright install chromium"
                ))
                return


            page = context.new_page()

            # Request Interception: Block image and media resource types to save RAM & CPU
            def block_heavy_resources(route):
                if route.request.resource_type in ["image", "media"]:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", block_heavy_resources)

            # Open WhatsApp Web to verify login
            self.stdout.write("Opening WhatsApp Web...")
            page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
            time.sleep(3)

            qr_code = page.locator("canvas[aria-label='Scan this QR code with WhatsApp to log in'], canvas")
            if qr_code.count() > 0 and ("Scan" in page.content() or "QR" in page.content()):
                if headless:
                    self.stderr.write(self.style.WARNING(
                        "\n[ATTENTION] WhatsApp Web is not logged in yet!\n"
                        "Run command with --headless=false to scan QR code once:\n"
                        "    python manage.py send_pending_whatsapp --headless=false\n"
                    ))
                else:
                    self.stdout.write(self.style.NOTICE(
                        "\n[ACTION REQUIRED] Please scan the QR code using WhatsApp on your phone."
                    ))

            sent_count = 0
            failed_count = 0

            for msg in pending_messages:
                success = self.process_message(page, msg)
                if success:
                    sent_count += 1
                else:
                    failed_count += 1

            # Save session state into Database (WhatsAppSession model)
            try:
                state_dict = context.storage_state()
                session_json = json.dumps(state_dict)
                session_obj = WhatsAppSession.objects.first()
                if not session_obj:
                    session_obj = WhatsAppSession()
                session_obj.session_data = session_json
                session_obj.save()

                # Also write to local storage_state.json
                with open(storage_state_file, 'w', encoding='utf-8') as f:
                    f.write(session_json)

                self.stdout.write(self.style.SUCCESS("\n✔ Exported & saved WhatsApp Web session state into Database."))
            except Exception as e_save:
                self.stdout.write(self.style.WARNING(f"\nCould not export session state: {e_save}"))

            summary_msg = f"Batch complete: {sent_count} sent, {failed_count} failed out of {len(pending_messages)} processed."
            self.stdout.write(self.style.SUCCESS(f"\n{summary_msg} Closing browser context."))
            if failed_count > 0:
                logger.warning(summary_msg)
            else:
                logger.info(summary_msg)
            context.close()

    def process_message(self, page, msg_obj: PendingMessage) -> bool:
        recipient_name = msg_obj.faculty.name if msg_obj.faculty else (msg_obj.student.name if msg_obj.student else "Unknown")
        phone_digits = _normalize_phone_number(msg_obj.phone)
        if not phone_digits:
            msg_obj.status = PendingMessage.STATUS_FAILED
            msg_obj.error_message = "Invalid or empty phone number."
            msg_obj.save()
            logger.error(f"Failed to send WhatsApp message to {recipient_name} (ID: {msg_obj.id}): Invalid or empty phone number.")
            self.stdout.write(self.style.ERROR(f"✖ Failed: {recipient_name} — Missing phone number"))
            return False

        encoded_text = urllib.parse.quote(msg_obj.message)
        send_url = f"https://web.whatsapp.com/send?phone={phone_digits}&text={encoded_text}"

        self.stdout.write(f"Sending message to {recipient_name} ({phone_digits})...")

        try:
            page.goto(send_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # 1. Check if QR code scanner is visible (User hasn't completed QR login)
            qr_code = page.locator("canvas[aria-label='Scan this QR code with WhatsApp to log in'], canvas")
            if qr_code.count() > 0 and ("Scan" in page.content() or "QR" in page.content()):
                self.stdout.write(self.style.NOTICE(">>> Waiting for QR Code scan on your phone... (Scan now in Chrome)"))
                try:
                    page.wait_for_selector("div[contenteditable='true'], span[data-icon='send'], #pane-side", timeout=60000)
                    time.sleep(3)
                except Exception:
                    logger.error(f"Failed to send WhatsApp message to {recipient_name} ({phone_digits}, ID: {msg_obj.id}): QR scan timeout / WhatsApp Web session expired.")
                    self.stdout.write(self.style.WARNING("QR scan timeout. Skipping message."))
                    return False

            # 2. Check for invalid number dialog
            invalid_dialog = page.locator("text='Phone number shared via url is invalid', text='is invalid'")
            if invalid_dialog.count() > 0:
                msg_obj.status = PendingMessage.STATUS_FAILED
                msg_obj.error_message = "Phone number is not on WhatsApp or invalid."
                msg_obj.save()
                logger.error(f"Failed to send WhatsApp message to {recipient_name} ({phone_digits}, ID: {msg_obj.id}): Phone number is not on WhatsApp or invalid.")
                self.stdout.write(self.style.ERROR(f"✖ Failed: {recipient_name} — Number not on WhatsApp"))
                return False

            # 3. Wait for chat box / footer container to load
            self.stdout.write("Waiting for WhatsApp chat box to load...")
            try:
                page.wait_for_selector("footer, div[contenteditable='true'], button[aria-label='Send'], span[data-icon='send']", timeout=25000)
            except Exception:
                pass

            # 4. Locate Chat Box Input and Send Arrow Button
            chat_box = page.locator("footer div[contenteditable='true'], div[contenteditable='true'][data-tab='10'], div[contenteditable='true']")
            send_btn = page.locator("button[aria-label='Send'], span[data-icon='send'], button:has(span[data-icon='send']), footer button:has(span)")

            if chat_box.count() > 0:
                chat_box.first.focus()
                time.sleep(0.5)
                page.keyboard.press("Enter")
                time.sleep(2)

            if send_btn.count() > 0 and send_btn.first.is_visible():
                try:
                    send_btn.first.click()
                    time.sleep(2)
                except Exception:
                    pass

            msg_obj.status = PendingMessage.STATUS_SENT
            msg_obj.error_message = ""
            msg_obj.save()
            self.stdout.write(self.style.SUCCESS(f"✔ Sent: {recipient_name} ({phone_digits})"))
            return True

        except Exception as e:
            msg_obj.status = PendingMessage.STATUS_FAILED
            msg_obj.error_message = str(e)
            msg_obj.save()
            logger.error(f"Failed to send WhatsApp message to {recipient_name} ({phone_digits}, ID: {msg_obj.id}): {e}")
            self.stdout.write(self.style.ERROR(f"✖ Failed: {recipient_name} — Error: {e}"))
            return False


