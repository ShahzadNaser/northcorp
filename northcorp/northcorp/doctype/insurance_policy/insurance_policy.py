# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, fmt_money, formatdate, getdate, now_datetime, nowdate

from northcorp.modules.insurance import check_finance, esc, html_table, send_email_from_doc

# Changing any of these after the check has passed sends the policy back to "Pending Check".
CHECKED_FIELDS = (
	"sum_insured", "tpl_limit", "deductible", "period_to", "maintenance_months",
	"req_sum_insured", "req_tpl_limit", "req_max_deductible", "req_period_to", "req_maintenance_months",
	"req_waiver_of_subrogation", "req_cross_liability", "req_primary_insurance",
	"chk_insured_names", "has_waiver_of_subrogation", "has_cross_liability", "has_primary_insurance",
)
DATE_FIELDS = ("period_to", "req_period_to")


class InsurancePolicy(Document):
	def validate(self):
		if getdate(self.period_to) < getdate(self.period_from):
			frappe.throw(_("Period To cannot be before Period From."))

		self.total_premium = flt(self.premium) + flt(self.vat)
		self.set_current_values()
		self.reset_check_if_changed()
		self.check_issues = "\n".join(self.get_check_issues()) or None
		self.set_status()

	def set_current_values(self):
		expiry = getdate(self.period_to)
		sum_insured = flt(self.sum_insured)
		for e in sorted(self.endorsements, key=lambda d: getdate(d.effective_date)):
			if e.endorsement_type == "Extension of Period" and e.new_expiry:
				expiry = max(expiry, getdate(e.new_expiry))
			if e.endorsement_type in ("Increase in Sum Insured", "Decrease in Sum Insured") and e.new_sum_insured:
				sum_insured = flt(e.new_sum_insured)
		self.current_expiry = expiry
		self.current_sum_insured = sum_insured

		if cint(self.maintenance_months):
			start = getdate(self.completion_date) if self.completion_date else expiry
			self.maintenance_end = add_months(start, cint(self.maintenance_months))
		else:
			self.maintenance_end = None

	def reset_check_if_changed(self):
		before = self.get_doc_before_save()
		if not before or self.check_result != "Passed":
			return
		def norm(doc, f):
			v = doc.get(f)
			if f in DATE_FIELDS:
				return str(getdate(v)) if v else ""
			return flt(v)

		if any(norm(self, f) != norm(before, f) for f in CHECKED_FIELDS):
			self.check_result = "Pending"
			self.checked_by = None
			self.checked_on = None
			frappe.msgprint(
				_("Cover details changed, so the policy check has to be confirmed again."),
				indicator="orange",
				alert=True,
			)

	def get_check_issues(self):
		money = lambda v: fmt_money(v, currency=self.currency)
		issues = []
		if not self.chk_insured_names:
			issues.append(_("Insured names not yet confirmed against the contract."))
		if flt(self.req_sum_insured) and flt(self.current_sum_insured) < flt(self.req_sum_insured):
			issues.append(_("Sum insured {0} is below the contract price {1}.").format(
				money(self.current_sum_insured), money(self.req_sum_insured)))
		if flt(self.req_tpl_limit) and flt(self.tpl_limit) < flt(self.req_tpl_limit):
			issues.append(_("TPL limit {0} is below the required {1}.").format(
				money(self.tpl_limit), money(self.req_tpl_limit)))
		if flt(self.req_max_deductible) and flt(self.deductible) > flt(self.req_max_deductible):
			issues.append(_("Deductible {0} is above the {1} the contract allows.").format(
				money(self.deductible), money(self.req_max_deductible)))
		if self.req_period_to and getdate(self.current_expiry) < getdate(self.req_period_to):
			issues.append(_("Cover ends {0}, before the required {1}.").format(
				formatdate(self.current_expiry), formatdate(self.req_period_to)))
		if cint(self.req_maintenance_months) and cint(self.maintenance_months) < cint(self.req_maintenance_months):
			issues.append(_("Maintenance period {0} months is shorter than the required {1}.").format(
				cint(self.maintenance_months), cint(self.req_maintenance_months)))
		for required, present, label in (
			("req_waiver_of_subrogation", "has_waiver_of_subrogation", _("Waiver of Subrogation")),
			("req_cross_liability", "has_cross_liability", _("Cross Liability")),
			("req_primary_insurance", "has_primary_insurance", _("Primary Insurance Clause")),
		):
			if self.get(required) and not self.get(present):
				issues.append(_("{0} is required by the contract but not confirmed on the policy.").format(label))
		return issues

	def set_status(self):
		if self.status in ("Closed", "Cancelled"):
			return
		if any(e.endorsement_type == "Cancellation" for e in self.endorsements):
			self.status = "Cancelled"
		elif self.check_result != "Passed":
			self.status = "Pending Check"
		elif getdate(nowdate()) > getdate(self.maintenance_end or self.current_expiry):
			self.status = "Expired"
		else:
			self.status = "Active"

	def after_insert(self):
		if self.insurance_request:
			frappe.db.set_value(
				"Insurance Request",
				self.insurance_request,
				{"insurance_policy": self.name, "status": "Policy Issued"},
			)

	def on_trash(self):
		if self.insurance_request:
			frappe.db.set_value(
				"Insurance Request", self.insurance_request, {"insurance_policy": None, "status": "Bound"}
			)

	def require_broker_email(self):
		if not self.broker_email:
			frappe.throw(_("Set the Broker Email on this policy first."))

	def email_broker(self, subject, body_html):
		self.require_broker_email()
		content = """<p>Dear {broker},</p>{body}{summary}<p>Regards,<br>{sender}<br>{company}</p>""".format(
			broker=esc(self.broker or _("Sir/Madam")),
			body=body_html,
			summary=html_table([
				(_("Policy No"), esc(self.policy_no)),
				(_("Insurance Type"), self.insurance_type),
				(_("Insurer"), esc(self.insurer)),
				(_("Project / Contract"), esc(self.project_name or self.title_of_contract or "-")),
				(_("Current Expiry"), formatdate(self.current_expiry)),
			]),
			sender=esc(frappe.utils.get_fullname(frappe.session.user)),
			company=esc(self.company),
		)
		send_email_from_doc(self, [self.broker_email], subject, content)


def get_policy(name):
	check_finance()
	doc = frappe.get_doc("Insurance Policy", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def confirm_check(name):
	doc = get_policy(name)
	issues = doc.get_check_issues()
	doc.check_result = "Failed" if issues else "Passed"
	doc.checked_by = frappe.session.user
	doc.checked_on = now_datetime()
	doc.save()
	return issues


@frappe.whitelist()
def request_extension(name, new_expiry, reason):
	doc = get_policy(name)
	if getdate(new_expiry) <= getdate(doc.current_expiry):
		frappe.throw(_("The new expiry must be after the current expiry {0}.").format(formatdate(doc.current_expiry)))
	doc.email_broker(
		_("Extension Request - Policy {0}").format(doc.policy_no),
		"<p>Please arrange an <b>extension of the period of insurance</b> from {0} to <b>{1}</b>.</p>"
		"<p>Reason: {2}</p><p>Please send the endorsement and the debit note for the additional premium.</p>".format(
			formatdate(doc.current_expiry), formatdate(new_expiry), esc(reason)),
	)


@frappe.whitelist()
def request_sum_insured_change(name, new_sum_insured, reason):
	doc = get_policy(name)
	doc.email_broker(
		_("Sum Insured Change Request - Policy {0}").format(doc.policy_no),
		"<p>Please arrange an endorsement to change the <b>sum insured</b> from {0} to <b>{1}</b>.</p>"
		"<p>Reason: {2}</p><p>Please send the endorsement and the debit note for any additional premium.</p>".format(
			fmt_money(doc.current_sum_insured, currency=doc.currency),
			fmt_money(flt(new_sum_insured), currency=doc.currency),
			esc(reason)),
	)


@frappe.whitelist()
def request_certificate(name, issued_to, purpose=None):
	doc = get_policy(name)
	doc.email_broker(
		_("Certificate of Insurance Request - Policy {0}").format(doc.policy_no),
		"<p>Please issue a <b>Certificate of Insurance</b> addressed to <b>{0}</b>{1}.</p>".format(
			esc(issued_to), " for " + esc(purpose) if purpose else ""),
	)
	doc.append("certificates", {"issued_to": issued_to, "purpose": purpose, "requested_on": nowdate()})
	doc.save()


@frappe.whitelist()
def notify_handover(name, completion_date):
	doc = get_policy(name)
	doc.email_broker(
		_("Project Completion / Start of Maintenance Period - Policy {0}").format(doc.policy_no),
		"<p>Please note the works were <b>completed and handed over on {0}</b>. "
		"The maintenance period of {1} months starts from this date. Please confirm the cover accordingly.</p>".format(
			formatdate(completion_date), cint(doc.maintenance_months)),
	)
	doc.completion_date = completion_date
	doc.save()


@frappe.whitelist()
def close_policy(name):
	doc = get_policy(name)
	doc.status = "Closed"
	doc.save()
