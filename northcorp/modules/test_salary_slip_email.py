# Run with: bench --site <site> run-tests --module northcorp.modules.test_salary_slip_email

import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from northcorp.modules import salary_slip as module
from northcorp.modules.salary_slip import (
    CustomSalarySlip,
    get_salary_slip_password,
    get_salary_slip_recipient,
)

BOTH_EMAILS = {"personal_email": "me@personal.test", "prefered_email": "me@work.test"}
DATE_OF_BIRTH = date(1990, 3, 5)


class TestSalarySlipRecipient(unittest.TestCase):
    def recipient_for(self, emails):
        with patch.object(module, "frappe") as frappe:
            frappe.db.get_value.return_value = emails
            return get_salary_slip_recipient("HR-EMP-TEST")

    def test_personal_email_wins_over_preferred(self):
        self.assertEqual(self.recipient_for(BOTH_EMAILS), "me@personal.test")

    def test_falls_back_to_preferred_without_personal(self):
        emails = {"personal_email": None, "prefered_email": "me@work.test"}
        self.assertEqual(self.recipient_for(emails), "me@work.test")

    def test_no_address_returns_nothing(self):
        self.assertFalse(self.recipient_for({"personal_email": None, "prefered_email": None}))
        self.assertIsNone(self.recipient_for(None))


class TestSalarySlipPassword(unittest.TestCase):
    def password_for(self, date_of_birth):
        with patch.object(module, "frappe") as frappe, patch.object(module, "getdate", lambda value: value):
            frappe.db.get_value.return_value = date_of_birth
            return get_salary_slip_password("HR-EMP-TEST")

    def test_is_date_of_birth_as_ddmmyyyy(self):
        self.assertEqual(self.password_for(DATE_OF_BIRTH), "05031990")

    def test_no_date_of_birth_returns_nothing(self):
        self.assertIsNone(self.password_for(None))


class TestEmailSalarySlip(unittest.TestCase):
    def send(self, emails=BOTH_EMAILS, date_of_birth=DATE_OF_BIRTH, in_test=True, posting_date=None, template=None):
        slip = SimpleNamespace(
            doctype="Salary Slip",
            name="SLIP-TEST",
            employee="HR-EMP-TEST",
            employee_name="Test Employee",
            start_date="2026-10-01",
            end_date="2026-10-31",
            posting_date=posting_date or date(2026, 10, 31),
            as_dict=lambda: {},
        )
        settings = SimpleNamespace(
            email_template=template,
            encrypt_salary_slips_in_emails=0,
            password_policy=None,
            sender_email="payroll@work.test",
        )

        with (
            patch.object(module, "frappe", MagicMock()) as frappe,
            patch.object(module, "_", lambda text: text),
            patch.object(module, "getdate", lambda value=None: value or date(2026, 11, 5)),
            patch.object(module, "formatdate", lambda value: value),
        ):
            frappe.db.get_value.side_effect = lambda doctype, name, fields, **kwargs: (
                date_of_birth if fields == "date_of_birth" else emails
            )
            frappe.get_single.return_value = settings
            frappe.render_template.return_value = "From template"
            frappe.flags.in_test = in_test
            CustomSalarySlip.email_salary_slip(slip)

        return frappe

    def test_sends_to_personal_email(self):
        args = self.send().sendmail.call_args.kwargs
        self.assertEqual(args["recipients"], ["me@personal.test"])
        self.assertEqual(args["reference_name"], "SLIP-TEST")
        self.assertIsNone(args["send_after"])

    def test_always_encrypted_with_date_of_birth(self):
        # encrypt_salary_slips_in_emails is off in these tests
        self.assertEqual(self.send().attach_print.call_args.kwargs["password"], "05031990")

    def test_message_explains_how_to_open_without_revealing_password(self):
        message = self.send().sendmail.call_args.kwargs["message"]
        self.assertIn("Dear Test Employee,", message)
        self.assertIn("2026-10-01 to 2026-10-31", message)
        self.assertIn("DDMMYYYY", message)
        self.assertNotIn("Please see attachment", message)
        # 05031990 appears only as the worked example, which is also this employee's password here,
        # so check a different date of birth is never written into the email
        other = self.send(date_of_birth=date(1985, 12, 25)).sendmail.call_args.kwargs["message"]
        self.assertNotIn("25121985", other)

    def test_template_message_still_gets_instructions(self):
        message = self.send(template="Payslip").sendmail.call_args.kwargs["message"]
        self.assertTrue(message.startswith("From template"))
        self.assertIn("DDMMYYYY", message)

    def test_queued_outside_tests(self):
        frappe = self.send(in_test=False)
        frappe.sendmail.assert_not_called()
        self.assertEqual(frappe.enqueue.call_args.kwargs["recipients"], ["me@personal.test"])

    def test_future_posting_date_is_delayed(self):
        posting_date = date(2026, 11, 5) + timedelta(days=3)
        frappe = self.send(posting_date=posting_date)
        self.assertEqual(frappe.sendmail.call_args.kwargs["send_after"], posting_date)

    def test_no_address_warns_instead_of_sending(self):
        frappe = self.send(emails={"personal_email": None, "prefered_email": None})
        frappe.sendmail.assert_not_called()
        frappe.msgprint.assert_called_once()

    def test_no_date_of_birth_is_never_sent_unencrypted(self):
        frappe = self.send(date_of_birth=None)
        frappe.sendmail.assert_not_called()
        frappe.enqueue.assert_not_called()
        frappe.msgprint.assert_called_once()
