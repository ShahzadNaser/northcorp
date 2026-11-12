# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, fmt_money, format_datetime, get_datetime, now_datetime, time_diff_in_hours

from northcorp.modules.insurance import attached_file_urls, esc, html_table, send_email_from_doc


class InsuranceClaim(Document):
	def validate(self):
		if get_datetime(self.incident_datetime) > now_datetime():
			frappe.throw(_("Incident Date & Time can't be in the future."))

		self.hours_to_report = None
		self.late_reporting = 0
		if self.reported_to_broker_on:
			hours = time_diff_in_hours(self.reported_to_broker_on, self.incident_datetime)
			if hours < 0:
				frappe.throw(_("Reported to Broker On can't be before the incident."))
			self.hours_to_report = hours
			if cint(self.claim_notice_hours) and hours > cint(self.claim_notice_hours):
				self.late_reporting = 1

		self.net_cost = max(
			flt(self.estimated_loss) - flt(self.amount_settled) - flt(self.amount_recovered), 0
		)


@frappe.whitelist()
def notify_broker(name):
	"""Email the loss notification to the policy's broker and record when it was reported."""
	doc = frappe.get_doc("Insurance Claim", name)
	doc.check_permission("write")
	policy = frappe.get_doc("Insurance Policy", doc.insurance_policy)
	if not policy.broker_email:
		frappe.throw(_("Set the Broker Email on policy {0} first.").format(policy.name))

	content = """<p>Dear {broker},</p>
<p>Please register the following <b>loss notification</b> with the insurer and advise the next steps
(survey / loss adjuster and documents required).</p>
{summary}
<p>Regards,<br>{sender}<br>{company}</p>""".format(
		broker=esc(policy.broker or _("Sir/Madam")),
		summary=html_table([
			(_("Policy No"), esc(policy.policy_no)),
			(_("Insurance Type"), policy.insurance_type),
			(_("Insurer"), esc(policy.insurer)),
			(_("Project / Contract"), esc(policy.project_name or policy.title_of_contract or "-")),
			(_("Incident Date & Time"), format_datetime(doc.incident_datetime)),
			(_("Location"), esc(doc.incident_location or "-")),
			(_("What Happened"), esc(doc.description)),
			(_("Estimated Loss"), fmt_money(doc.estimated_loss, currency=doc.currency) if doc.estimated_loss else "-"),
		]),
		sender=esc(frappe.utils.get_fullname(frappe.session.user)),
		company=esc(policy.company),
	)
	send_email_from_doc(
		doc,
		[policy.broker_email],
		_("Loss Notification - Policy {0} - {1}").format(policy.policy_no, doc.name),
		content,
		file_urls=attached_file_urls(doc),
	)
	if not doc.reported_to_broker_on:
		doc.reported_to_broker_on = now_datetime()
	doc.save()
