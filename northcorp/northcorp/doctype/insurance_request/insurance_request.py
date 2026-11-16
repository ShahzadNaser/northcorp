# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt, fmt_money, formatdate, getdate, now_datetime, nowdate

from northcorp.modules.insurance import (
	attached_file_urls,
	check_finance,
	check_finance_manager,
	esc,
	html_table,
	send_email_from_doc,
)

LOCKED_STATUSES = ("Quote Approved", "Bound", "Policy Issued", "Cancelled")


class InsuranceRequest(Document):
	def validate(self):
		if self.construction_start and self.construction_end:
			if getdate(self.construction_end) < getdate(self.construction_start):
				frappe.throw(_("Construction Period To cannot be before Construction Period From."))

		for q in self.quotes:
			q.total_premium = flt(q.premium) + flt(q.vat)

		if len([q for q in self.quotes if q.selected]) > 1:
			frappe.throw(_("Select only one quote."))

		if self.status == "Sent to Brokers" and self.quotes:
			self.status = "Quotes Received"

		self.validate_locked()

	def validate_locked(self):
		"""Once a quote is approved, the chosen quote can no longer be switched."""
		before = self.get_doc_before_save()
		if not before or before.status not in LOCKED_STATUSES:
			return
		old = {q.name for q in before.quotes if q.selected}
		new = {q.name for q in self.quotes if q.selected}
		if old != new:
			frappe.throw(_("The approved quote can't be changed after approval."))

	def selected_quote(self):
		return next((q for q in self.quotes if q.selected), None)

	def broker_email(self, broker):
		return next((b.email for b in self.brokers if b.broker == broker), None)

	def summary_html(self):
		money = lambda v: fmt_money(v, currency=self.currency) if v else "-"
		date = lambda v: formatdate(v) if v else "-"
		rows = [
			(_("Insurance Type"), self.insurance_type),
			(_("Insured"), "{0} (as Principal) and/or {1} (as {2})".format(
				esc(self.principal or "-"), esc(self.company), esc(self.northcorp_role or "-"))),
			(_("Title of Contract"), esc(self.title_of_contract or "-")),
			(_("Site Location"), esc(self.site_location or "-")),
			(_("Contract Price"), money(self.contract_price)),
			(_("Construction Period"), "{0} to {1}".format(date(self.construction_start), date(self.construction_end))),
			(_("Maintenance Period"), "{0} months".format(self.maintenance_months) if self.maintenance_months else "-"),
			(_("Principal's Existing & Surrounding Property"), money(self.principals_property)),
			(_("Third Party Liability Limit"), money(self.tpl_limit)),
			(_("Maximum Deductible Allowed"), money(self.max_deductible)),
			(_("Insured Parties Required"), esc(self.additional_insured or "-")),
			(_("Required Clauses"), ", ".join(c for c, req in (
				(_("Waiver of Subrogation"), self.req_waiver_of_subrogation),
				(_("Cross Liability"), self.req_cross_liability),
				(_("Primary Insurance"), self.req_primary_insurance),
			) if req) or "-"),
			(_("Cover Required By"), date(self.required_by)),
		]
		return html_table(rows)


def get_request(name):
	doc = frappe.get_doc("Insurance Request", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def send_to_brokers(name, resend=0):
	"""Email the request separately to each broker (brokers don't see each other)."""
	check_finance()
	doc = get_request(name)
	if doc.status not in ("Draft", "Sent to Brokers", "Quotes Received"):
		frappe.throw(_("A request in status {0} can't be sent to brokers.").format(doc.status))
	if not doc.brokers:
		frappe.throw(_("Add at least one broker in the Brokers table."))

	resend = frappe.utils.cint(resend)
	sent = []
	for b in doc.brokers:
		if b.sent_on and not resend:
			continue
		greeting = esc(b.contact_person or b.broker)
		content = """<p>Dear {greeting},</p>
<p>Please arrange quotations from at least 2-3 insurers for the cover below.
For each quote, please state the premium, deductible, key exclusions, the maintenance period terms
(visits only or extended maintenance cover), and the quote validity.</p>
{summary}
<p>{notes}</p>
<p>The contract insurance clause and supporting documents are attached.</p>
<p>Regards,<br>{sender}<br>{company}</p>""".format(
			greeting=greeting,
			summary=doc.summary_html(),
			notes=esc(doc.notes or ""),
			sender=esc(frappe.utils.get_fullname(frappe.session.user)),
			company=esc(doc.company),
		)
		subject = _("Insurance Quotation Request - {0} - {1}").format(
			doc.insurance_type, doc.project_name or doc.title_of_contract or doc.name
		)
		# Never attach other brokers' quote documents.
		files = attached_file_urls(doc, exclude=[q.attachment for q in doc.quotes if q.attachment])
		send_email_from_doc(doc, [b.email], subject, content, file_urls=files)
		b.sent_on = now_datetime()
		sent.append(b.broker)

	if not sent:
		frappe.throw(_("All brokers have already been sent this request. Use Resend to send again."))

	if doc.status == "Draft":
		doc.status = "Sent to Brokers"
	doc.save()
	return sent


@frappe.whitelist()
def approve_quote(name):
	check_finance_manager()
	doc = get_request(name)
	if doc.status not in ("Sent to Brokers", "Quotes Received"):
		frappe.throw(_("Only a request with quotes can be approved."))
	quote = doc.selected_quote()
	if not quote:
		frappe.throw(_("Tick Selected on the quote you want to approve."))
	if len(doc.quotes) < 2:
		frappe.msgprint(
			_("Only one quote was received. The usual practice is to compare at least 2-3 quotes."),
			indicator="orange",
			alert=True,
		)
	if doc.requested_by == frappe.session.user:
		frappe.throw(_("The person who raised the request can't approve the quote."))

	doc.status = "Quote Approved"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save()


@frappe.whitelist()
def mark_bound(name):
	"""Instruct the selected broker to bind the cover, then mark the request Bound."""
	check_finance()
	doc = get_request(name)
	if doc.status != "Quote Approved":
		frappe.throw(_("Approve a quote first."))
	quote = doc.selected_quote()
	email = doc.broker_email(quote.broker)
	if not email:
		frappe.throw(_("Add broker {0} with an email to the Brokers table.").format(quote.broker))

	content = """<p>Dear {broker},</p>
<p>Please bind the cover below with <b>{insurer}</b> as per your quote{ref}
(premium {premium} + VAT {vat}), and send us the policy schedule, wording and invoice.</p>
{summary}
<p>Regards,<br>{sender}<br>{company}</p>""".format(
		broker=esc(quote.broker),
		insurer=esc(quote.insurer),
		ref=" ref. " + esc(quote.quote_ref) if quote.quote_ref else "",
		premium=fmt_money(quote.premium, currency=doc.currency),
		vat=fmt_money(quote.vat, currency=doc.currency),
		summary=doc.summary_html(),
		sender=esc(frappe.utils.get_fullname(frappe.session.user)),
		company=esc(doc.company),
	)
	subject = _("Binding Instruction - {0} - {1}").format(
		doc.insurance_type, doc.project_name or doc.title_of_contract or doc.name
	)
	send_email_from_doc(doc, [email], subject, content)

	doc.status = "Bound"
	doc.bound_on = nowdate()
	doc.save()


@frappe.whitelist()
def cancel_request(name, reason):
	doc = get_request(name)
	if doc.status in ("Policy Issued", "Cancelled"):
		frappe.throw(_("This request can't be cancelled."))
	doc.status = "Cancelled"
	doc.cancel_reason = reason
	doc.save()


@frappe.whitelist()
def make_policy(source_name, target_doc=None):
	check_finance()
	source = frappe.get_doc("Insurance Request", source_name)
	if source.status != "Bound":
		frappe.throw(_("Mark the request as Bound before creating the policy."))
	if source.insurance_policy:
		frappe.throw(_("Policy {0} already exists for this request.").format(source.insurance_policy))

	def postprocess(src, target):
		quote = src.selected_quote()
		target.insurance_request = src.name
		target.period_from = src.construction_start
		target.period_to = src.construction_end
		target.req_sum_insured = src.contract_price
		target.req_tpl_limit = src.tpl_limit
		target.req_max_deductible = src.max_deductible
		target.req_maintenance_months = src.maintenance_months
		target.req_period_to = src.construction_end
		target.req_insured_parties = src.additional_insured
		target.req_waiver_of_subrogation = src.req_waiver_of_subrogation
		target.req_cross_liability = src.req_cross_liability
		target.req_primary_insurance = src.req_primary_insurance
		if quote:
			target.insurer = quote.insurer
			target.broker = quote.broker
			target.broker_email = src.broker_email(quote.broker)
			target.premium = quote.premium
			target.vat = quote.vat
			target.sum_insured = quote.sum_insured or src.contract_price
			target.tpl_limit = quote.tpl_limit
			target.deductible = quote.deductible
			target.deductible_terms = quote.deductible_terms
			target.maintenance_months = quote.maintenance_months or src.maintenance_months
			target.maintenance_cover = quote.maintenance_cover

	return get_mapped_doc(
		"Insurance Request",
		source_name,
		{
			"Insurance Request": {
				"doctype": "Insurance Policy",
				"field_map": {
					"insurance_type": "insurance_type",
					"company": "company",
					"project": "project",
					"principal": "principal",
					"title_of_contract": "title_of_contract",
					"site_location": "site_location",
					"currency": "currency",
					"principals_property": "principals_property",
				},
				"field_no_map": ["status", "naming_series"],
			}
		},
		target_doc,
		postprocess,
	)
