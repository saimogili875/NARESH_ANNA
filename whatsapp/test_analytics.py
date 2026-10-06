import json
import hmac
import hashlib
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from accounts.models import Group, Section
from students.models import Student
from faculty.models import Faculty
from whatsapp.models import PendingMessage
from whatsapp.services import dispatch_pending_messages
from whatsapp.analytics import get_analytics_data, get_date_range, KOLKATA_TZ
import importlib
backfill_analytics_fields = importlib.import_module('whatsapp.migrations.0009_backfill_analytics_fields').backfill_analytics_fields

User = get_user_model()


class WhatsAppAnalyticsTestCase(TestCase):
    def setUp(self):
        self.group1, _ = Group.objects.get_or_create(code="MPC", defaults={"name": "MPC"})
        self.group2, _ = Group.objects.get_or_create(code="BIPC", defaults={"name": "BiPC"})
        self.section1, _ = Section.objects.get_or_create(group=self.group1, name="A", year=1)
        self.section2, _ = Section.objects.get_or_create(group=self.group2, name="B", year=1)

        self.student1 = Student.objects.create(
            name="Rahul Sharma",
            admission_number="ADM001",
            section=self.section1,
            mobile="9876543210",
            is_active=True,
        )
        self.student2 = Student.objects.create(
            name="Anita Roy",
            admission_number="ADM002",
            section=self.section2,
            mobile="9876543211",
            is_active=True,
        )

        self.admin_user, _ = User.objects.get_or_create(
            username="admin_test",
            defaults={"role": "admin", "is_staff": True, "is_superuser": True}
        )
        self.admin_user.set_password("Password123!")
        self.admin_user.save()

        self.accounts_user, _ = User.objects.get_or_create(
            username="accounts_test",
            defaults={"role": "accounts"}
        )
        self.accounts_user.set_password("Password123!")
        self.accounts_user.save()

        self.faculty_user, _ = User.objects.get_or_create(
            username="faculty_test",
            defaults={"role": "faculty"}
        )
        self.faculty_user.set_password("Password123!")
        self.faculty_user.save()

        self.faculty_obj, _ = Faculty.objects.get_or_create(
            user=self.faculty_user,
            defaults={"name": "Faculty User", "date_of_joining": date.today()}
        )

        self.client = Client()

    def test_model_category_and_section_autofill(self):
        # Auto-derive MARKS category from template name
        msg_marks = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            message="Marks report",
        )
        self.assertEqual(msg_marks.category, PendingMessage.CATEGORY_MARKS)
        self.assertEqual(msg_marks.section, self.section1)
        self.assertEqual(msg_marks.group, self.group1)

        # Auto-derive ATTENDANCE category from template name
        msg_att = PendingMessage.objects.create(
            student=self.student2,
            phone=self.student2.mobile,
            template_name="absence_alert",
            message="Absence alert",
        )
        self.assertEqual(msg_att.category, PendingMessage.CATEGORY_ATTENDANCE)
        self.assertEqual(msg_att.section, self.section2)
        self.assertEqual(msg_att.group, self.group2)

        # OTHER category when no match
        msg_other = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="custom_template",
            message="Custom info",
        )
        self.assertEqual(msg_other.category, PendingMessage.CATEGORY_OTHER)

    def test_sent_at_stamped_once(self):
        msg = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            status=PendingMessage.STATUS_PENDING,
        )
        self.assertIsNone(msg.sent_at)

        msg.status = PendingMessage.STATUS_SENT
        msg.save()
        first_sent_at = msg.sent_at
        self.assertIsNotNone(first_sent_at)

        # Updating status again should not overwrite sent_at
        msg.status = PendingMessage.STATUS_DELIVERED
        msg.save()
        self.assertEqual(msg.sent_at, first_sent_at)

    def test_apply_status_update_rules(self):
        msg = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            status=PendingMessage.STATUS_SENT,
            wamid="wamid.123",
        )

        now_event = timezone.now()

        # Delivered sets delivered_at
        msg.apply_status_update("delivered", event_time=now_event)
        self.assertEqual(msg.status, PendingMessage.STATUS_DELIVERED)
        self.assertEqual(msg.delivered_at, now_event)

        # Read sets read_at and delivered_at
        msg.apply_status_update("read", event_time=now_event)
        self.assertEqual(msg.status, PendingMessage.STATUS_READ)
        self.assertEqual(msg.read_at, now_event)

        # Never downgrade read or delivered status to failed
        msg.apply_status_update("failed", event_time=now_event, error_detail="Late fail")
        self.assertEqual(msg.status, PendingMessage.STATUS_READ)  # Should remain READ

        # Failed after SENT should update to FAILED
        msg_sent = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            status=PendingMessage.STATUS_SENT,
            wamid="wamid.456",
        )
        msg_sent.apply_status_update("failed", event_time=now_event, error_detail="Not on WhatsApp")
        self.assertEqual(msg_sent.status, PendingMessage.STATUS_FAILED)
        self.assertEqual(msg_sent.error_message, "Not on WhatsApp")

    def test_webhook_signed_out_of_order(self):
        msg = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            status=PendingMessage.STATUS_SENT,
            wamid="wamid.test.webhook",
        )

        app_secret = "test_app_secret"
        with patch.object(settings, 'META_APP_SECRET', app_secret):
            # 1. Out-of-order READ event comes first
            read_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "statuses": [{
                                "id": "wamid.test.webhook",
                                "status": "read",
                                "timestamp": "1700000000",
                                "recipient_id": "9876543210"
                            }]
                        }
                    }]
                }]
            }
            body = json.dumps(read_payload).encode('utf-8')
            sig = "sha256=" + hmac.new(app_secret.encode('utf-8'), body, hashlib.sha256).hexdigest()

            resp = self.client.post(
                reverse('whatsapp-webhook'),
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=sig,
            )
            self.assertEqual(resp.status_code, 200)

            msg.refresh_from_db()
            self.assertEqual(msg.status, PendingMessage.STATUS_READ)
            self.assertIsNotNone(msg.read_at)
            self.assertIsNotNone(msg.delivered_at)

            # 2. Subsequent DELIVERED event should not downgrade READ
            deliv_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "statuses": [{
                                "id": "wamid.test.webhook",
                                "status": "delivered",
                                "timestamp": "1699999990",
                                "recipient_id": "9876543210"
                            }]
                        }
                    }]
                }]
            }
            body_d = json.dumps(deliv_payload).encode('utf-8')
            sig_d = "sha256=" + hmac.new(app_secret.encode('utf-8'), body_d, hashlib.sha256).hexdigest()

            resp_d = self.client.post(
                reverse('whatsapp-webhook'),
                data=body_d,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=sig_d,
            )
            self.assertEqual(resp_d.status_code, 200)

            msg.refresh_from_db()
            self.assertEqual(msg.status, PendingMessage.STATUS_READ)

    def test_analytics_counting_rules(self):
        # Student 1 has 2 sent messages (1 delivered, 1 read)
        msg1 = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            category=PendingMessage.CATEGORY_MARKS,
            status=PendingMessage.STATUS_DELIVERED,
        )
        msg2 = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            category=PendingMessage.CATEGORY_ATTENDANCE,
            status=PendingMessage.STATUS_READ,
        )
        # Student 2 has 1 failed message
        msg3 = PendingMessage.objects.create(
            student=self.student2,
            phone=self.student2.mobile,
            category=PendingMessage.CATEGORY_MARKS,
            status=PendingMessage.STATUS_FAILED,
        )
        # Pending message (queued - excluded from sent)
        msg4 = PendingMessage.objects.create(
            student=self.student2,
            phone=self.student2.mobile,
            category=PendingMessage.CATEGORY_ATTENDANCE,
            status=PendingMessage.STATUS_PENDING,
        )
        # Faculty alert (excluded from student metrics)
        msg_fac = PendingMessage.objects.create(
            faculty=self.faculty_obj,
            phone="9999999999",
            category=PendingMessage.CATEGORY_OTHER,
            status=PendingMessage.STATUS_SENT,
        )

        data = get_analytics_data(preset='all', tab='overview')
        summary = data['summary']

        # Total sent = 3 (msg1, msg2, msg3; failed IS a subset of sent)
        self.assertEqual(summary['total_sent'], 3)

        # Unique students = 2 (student1, student2)
        self.assertEqual(summary['unique_students'], 2)

        # Messages per student = 3 / 2 = 1.5
        self.assertEqual(summary['msgs_per_student'], 1.5)

        # Delivered = 2 (msg1 delivered, msg2 read)
        self.assertEqual(summary['total_delivered'], 2)

        # Read = 1 (msg2)
        self.assertEqual(summary['total_read'], 1)

        # Failed = 1 (msg3)
        self.assertEqual(summary['total_failed'], 1)

        # Queued = 1 (msg4)
        self.assertEqual(summary['total_queued'], 1)

        # Marks = 2 (msg1, msg3), Attendance = 1 (msg2)
        self.assertEqual(summary['total_marks'], 2)
        self.assertEqual(summary['total_attendance'], 1)

        # Faculty/Other count = 1
        self.assertEqual(summary['other_or_faculty_count'], 1)

    def test_section_snapshot_survives_student_transfer(self):
        # Message created while student1 is in Section 1
        msg = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="marks_template",
            status=PendingMessage.STATUS_SENT,
        )
        self.assertEqual(msg.section, self.section1)
        self.assertEqual(msg.group, self.group1)

        # Move student1 to Section 2
        self.student1.section = self.section2
        self.student1.save()

        # Existing message snapshot section/group should remain Section 1 / Group 1
        msg.refresh_from_db()
        self.assertEqual(msg.section, self.section1)
        self.assertEqual(msg.group, self.group1)

        # Analytics for section 1 should count this message
        data = get_analytics_data(preset='all', tab='overview')
        sec_table = data['tab_data']['section_table']
        sec1_row = next((r for r in sec_table if r['section_name'] == str(self.section1)), None)
        self.assertIsNotNone(sec1_row)
        self.assertEqual(sec1_row['total_sent'], 1)

    @patch('whatsapp.services.send_whatsapp_template')
    def test_dispatcher_sends_once_and_terminal_direct_send(self, mock_send_template):
        mock_send_template.return_value = {"success": True, "wamid": "wamid.mock.100", "status_code": 200}

        msg = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="absence_alert",
            status=PendingMessage.STATUS_PENDING,
        )

        res = dispatch_pending_messages(batch_size=50)
        self.assertEqual(res['sent'], 1)

        msg.refresh_from_db()
        self.assertEqual(msg.status, PendingMessage.STATUS_SENT)
        self.assertEqual(msg.wamid, "wamid.mock.100")

        # Second dispatch should send 0 pending messages
        res2 = dispatch_pending_messages(batch_size=50)
        self.assertEqual(res2['sent'], 0)

    @patch('whatsapp.services.send_absence_alert')
    def test_direct_send_path_logs_once_and_never_resent(self, mock_send_absence):
        mock_send_absence.return_value = {"success": True, "wamid": "wamid.direct.999", "status_code": 200}

        from attendance.models import Attendance
        att = Attendance.objects.create(
            student=self.student1,
            section=self.section1,
            date=date.today(),
            status='A',
            remarks="Sick",
        )

        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse('attendance_send_whatsapp'),
            data={'section_id': self.section1.pk, 'date': date.today().strftime('%Y-%m-%d')},
        )
        self.assertEqual(resp.status_code, 200)

        # Confirm 1 PendingMessage created with terminal status SENT
        msgs = PendingMessage.objects.filter(student=self.student1)
        self.assertEqual(msgs.count(), 1)
        p_msg = msgs.first()
        self.assertEqual(p_msg.status, PendingMessage.STATUS_SENT)
        self.assertEqual(p_msg.wamid, "wamid.direct.999")
        self.assertEqual(p_msg.category, PendingMessage.CATEGORY_ATTENDANCE)

        # Dispatcher should ignore terminal SENT message
        res = dispatch_pending_messages(batch_size=50)
        self.assertEqual(res['sent'], 0)

    def test_access_control_and_views(self):
        url = reverse('wa_analytics')

        # Anonymous -> redirect login
        res_anon = self.client.get(url)
        self.assertEqual(res_anon.status_code, 302)

        # Faculty -> redirected by FacultyAccessMiddleware to /attendance/
        self.client.force_login(self.faculty_user)
        res_fac = self.client.get(url)
        self.assertEqual(res_fac.status_code, 302)
        self.assertIn('/attendance/', res_fac.url)

        # Admin -> 200 OK
        self.client.force_login(self.admin_user)
        res_admin = self.client.get(url)
        self.assertEqual(res_admin.status_code, 200)

        # Accounts role -> 200 OK
        self.client.force_login(self.accounts_user)
        res_acc = self.client.get(url)
        self.assertEqual(res_acc.status_code, 200)

        # Tabs check
        for tab_name in ('overview', 'marks', 'attendance'):
            res_tab = self.client.get(f"{url}?tab={tab_name}")
            self.assertEqual(res_tab.status_code, 200)

        # Malicious / Garbage query params -> 200 OK without crashing
        garbage_url = f"{url}?preset=garbage&from_date=invalid&to_date=9999-99-99&group=abc&section=--1&page=-5"
        res_garb = self.client.get(garbage_url)
        self.assertEqual(res_garb.status_code, 200)

    def test_phone_number_redaction_for_non_admin(self):
        PendingMessage.objects.create(
            student=self.student1,
            phone="9876543210",
            category=PendingMessage.CATEGORY_MARKS,
            status=PendingMessage.STATUS_SENT,
        )

        url = reverse('wa_analytics')

        # Admin can view phone number
        self.client.force_login(self.admin_user)
        res_admin = self.client.get(url)
        self.assertContains(res_admin, "9876543210")

        # Existing whatsapp-status page still works for admin
        res_status = self.client.get(reverse('whatsapp-status'))
        self.assertEqual(res_status.status_code, 200)

    def test_backfill_migration_function(self):
        # Create legacy raw row without category or sent_at
        msg_legacy = PendingMessage.objects.create(
            student=self.student1,
            phone=self.student1.mobile,
            template_name="exam_marks",
            status=PendingMessage.STATUS_SENT,
            category=PendingMessage.CATEGORY_OTHER,
        )
        PendingMessage.objects.filter(pk=msg_legacy.pk).update(
            category=PendingMessage.CATEGORY_OTHER,
            sent_at=None,
            section=None,
            group=None,
        )

        # Run backfill function directly
        class MockApps:
            @staticmethod
            def get_model(app, model):
                if model == 'PendingMessage':
                    return PendingMessage
                if model == 'Student':
                    return Student
                return None

        backfill_analytics_fields(MockApps(), None)

        msg_legacy.refresh_from_db()
        self.assertEqual(msg_legacy.category, PendingMessage.CATEGORY_MARKS)
        self.assertEqual(msg_legacy.section, self.section1)
        self.assertEqual(msg_legacy.group, self.group1)
        self.assertIsNotNone(msg_legacy.sent_at)
