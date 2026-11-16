# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt
"""Shared helpers for Insurance Request / Policy / Claim / Subcontractor Insurance Certificate:
emails to brokers, permissions, the Project dashboard links and the daily insurance alerts."""

import frappe
from frappe import _
from frappe.core.doctype.communication.email import make as make_communication
from frappe.utils import add_days, date_diff, escape_html, formatdate, get_url_to_form, getdate, nowdate

FINANCE_ROLES = ("Accounts Manager", "Accounts User", "System Manager")
FINANCE_MANAGER_ROLES = ("Accounts Manager", "System Manager")

# Daily insurance alert digest. Project-related alerts also go to the person who raised the request.
INSURANCE_ALERT_RECIPIENTS = [
	"farooq.gujjar@northcorp.ae",
]

POLICY_EXPIRY_ALERT_DAYS = (60, 30, 14, 7, 1)
PREMIUM_ALERT_DAYS = (14, 7, 3, 1, 0)
SUBCONTRACTOR_ALERT_DAYS = (30, 14, 7, 1)


def esc(value):
	return escape_html(value or "")


def html_table(rows):
	cells = "".join(
		'<tr><td style="padding:4px 10px;border:1px solid #ddd;background:#f7f7f7;width:35%"><b>{0}</b></td>'
		'<td style="padding:4px 10px;border:1px solid #ddd">{1}</td></tr>'.format(esc(label), value)
		for label, value in rows
	)
	return '<table style="border-collapse:collapse;margin:10px 0">{0}</table>'.format(cells)


def is_finance(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(FINANCE_ROLES))


def check_finance():
	frappe.only_for(list(FINANCE_ROLES))


def check_finance_manager():
	frappe.only_for(list(FINANCE_MANAGER_ROLES))


def attached_file_urls(doc, exclude=()):
	urls = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
		pluck="file_url",
	)
	return [u for u in urls if u and u not in set(exclude)]


def send_email_from_doc(doc, recipients, subject, content, file_urls=None):
	"""Send through the standard Communication, so the email and any reply show on the document's timeline.

	file_urls: only these files (already attached to the document) are attached to the email.
	"""
	attachments = []
	if file_urls:
		attachments = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
				"file_url": ["in", list(file_urls)],
			},
			pluck="name",
		)
	make_communication(
		doctype=doc.doctype,
		name=doc.name,
		subject=subject,
		content=content,
		recipients=", ".join(recipients),
		send_email=True,
		attachments=attachments,
	)


# ---------------------------------------------------------------- permissions
# Project teams see only policies linked to a project (User Permissions on Project then
# limit them to their own projects). Company-wide policies (fire, motor, medical...) stay with Finance.


def policy_query_conditions(user=None, **kwargs):
	if is_finance(user):
		return ""
	return "ifnull(`tabInsurance Policy`.`project`, '') != ''"


def policy_has_permission(doc, ptype=None, user=None, **kwargs):
	if not is_finance(user) and not doc.get("project"):
		return False
	return None


# ---------------------------------------------------------------- project dashboard


def project_dashboard(data):
	data.setdefault("transactions", []).append(
		{
			"label": _("Insurance"),
			"items": [
				"Insurance Request",
				"Insurance Policy",
				"Insurance Claim",
				"Subcontractor Insurance Certificate",
			],
		}
	)
	return data


# ---------------------------------------------------------------- daily alerts


def send_insurance_alerts():
	"""Daily: update statuses, then email one digest of everything that needs action."""
	today = getdate(nowdate())
	items = []  # (section, doctype, name, message, extra_recipient)

	update_statuses(today)

	policies = frappe.get_all(
		"Insurance Policy",
		filters={"status": ["in", ["Active", "Pending Check"]]},
		fields=[
			"name", "policy_no", "insurance_type", "project", "project_name", "status", "creation",
			"current_expiry", "maintenance_end", "maintenance_months", "completion_date",
			"premium_due_date", "premium_paid", "insurance_request",
		],
	)
	for p in policies:
		label = "{0} {1}{2}".format(p.insurance_type, p.policy_no, " ({0})".format(p.project_name) if p.project_name else "")
		requester = frappe.db.get_value("Insurance Request", p.insurance_request, "requested_by") if p.insurance_request else None

		days = date_diff(p.current_expiry, today)
		is_construction_cover = p.maintenance_months and not p.completion_date
		if days in POLICY_EXPIRY_ALERT_DAYS:
			msg = _("Cover expires on {0} ({1} days).").format(formatdate(p.current_expiry), days)
			if is_construction_cover:
				msg += " " + _("If the works won't be finished by then, request an extension now.")
			items.append(("Policies expiring", "Insurance Policy", p.name, label + ": " + msg, requester))

		if p.maintenance_end and p.maintenance_end != p.current_expiry:
			mdays = date_diff(p.maintenance_end, today)
			if mdays in POLICY_EXPIRY_ALERT_DAYS:
				items.append(("Policies expiring", "Insurance Policy", p.name, label + ": " + _(
					"Maintenance period cover ends on {0} ({1} days).").format(formatdate(p.maintenance_end), mdays), requester))

		if p.premium_due_date and not p.premium_paid:
			pdays = date_diff(p.premium_due_date, today)
			if pdays < 0:
				items.append(("Premium payment", "Insurance Policy", p.name, label + ": " + _(
					"Premium was due on {0} and isn't marked paid. Under the premium payment warranty the cover may be void.").format(
					formatdate(p.premium_due_date)), None))
			elif pdays in PREMIUM_ALERT_DAYS:
				items.append(("Premium payment", "Insurance Policy", p.name, label + ": " + _(
					"Premium due on {0} ({1} days).").format(formatdate(p.premium_due_date), pdays), None))

		if p.status == "Pending Check" and date_diff(today, getdate(p.creation)) >= 7 and today.weekday() == 0:
			items.append(("Policy check pending", "Insurance Policy", p.name, label + ": " + _(
				"Issued policy not yet checked against the contract."), None))

		if p.insurance_type == "Contractors All Risk" and p.project and is_construction_cover:
			project_end = frappe.db.get_value("Project", {"name": p.project, "status": "Open"}, "expected_end_date")
			if project_end and getdate(project_end) > getdate(p.current_expiry) and (today.weekday() == 0 or days in POLICY_EXPIRY_ALERT_DAYS):
				items.append(("Extension needed", "Insurance Policy", p.name, label + ": " + _(
					"Project expected end {0} is after the cover expiry {1}. Request a period extension.").format(
					formatdate(project_end), formatdate(p.current_expiry)), requester))

	for c in frappe.get_all(
		"Subcontractor Insurance Certificate",
		fields=["name", "subcontractor_name", "subcontractor", "insurance_type", "project_name", "valid_to", "owner"],
		filters={"valid_to": [">=", add_days(today, -1)]},
	):
		days = date_diff(c.valid_to, today)
		if days in SUBCONTRACTOR_ALERT_DAYS or days == -1:
			msg = _("expired on {0}").format(formatdate(c.valid_to)) if days < 0 else _("expires on {0} ({1} days)").format(formatdate(c.valid_to), days)
			items.append(("Subcontractor certificates", "Subcontractor Insurance Certificate", c.name, "{0} - {1}{2}: {3}. {4}".format(
				c.subcontractor_name or c.subcontractor, c.insurance_type,
				" ({0})".format(c.project_name) if c.project_name else "", msg,
				_("Ask the subcontractor for the renewed certificate.")), c.owner))

	for cl in frappe.get_all(
		"Insurance Claim",
		filters={"reported_to_broker_on": ["is", "not set"], "status": "Reported"},
		fields=["name", "policy_no", "incident_datetime", "owner"],
	):
		items.append(("Claims not reported to broker", "Insurance Claim", cl.name, _(
			"Incident on {0} under policy {1} hasn't been reported to the broker.").format(
			formatdate(cl.incident_datetime), cl.policy_no), cl.owner))

	if items:
		send_digest(items)


def update_statuses(today):
	for p in frappe.get_all(
		"Insurance Policy",
		filters={"status": "Active"},
		fields=["name", "current_expiry", "maintenance_end"],
	):
		if today > getdate(p.maintenance_end or p.current_expiry):
			frappe.db.set_value("Insurance Policy", p.name, "status", "Expired", update_modified=False)

	from northcorp.northcorp.doctype.subcontractor_insurance_certificate.subcontractor_insurance_certificate import get_status

	for c in frappe.get_all("Subcontractor Insurance Certificate", fields=["name", "valid_to", "status"]):
		status = get_status(c.valid_to)
		if status != c.status:
			frappe.db.set_value("Subcontractor Insurance Certificate", c.name, "status", status, update_modified=False)


def send_digest(items):
	per_recipient = {}
	for item in items:
		recipients = set(INSURANCE_ALERT_RECIPIENTS)
		extra = item[4]
		if extra and extra not in ("Administrator", "Guest"):
			email = frappe.db.get_value("User", extra, "email")
			if email:
				recipients.add(email)
		for r in recipients:
			per_recipient.setdefault(r, []).append(item)

	for recipient, rows in per_recipient.items():
		sections = {}
		for section, doctype, name, msg, _extra in rows:
			sections.setdefault(section, []).append(
				'<li><a href="{0}">{1}</a> - {2}</li>'.format(get_url_to_form(doctype, name), esc(name), esc(msg))
			)
		body = "".join("<h4>{0}</h4><ul>{1}</ul>".format(esc(s), "".join(lines)) for s, lines in sections.items())
		frappe.sendmail(
			recipients=[recipient],
			subject=_("Insurance alerts - {0}").format(formatdate(nowdate())),
			message="<p>{0}</p>{1}".format(_("These insurance items need action:"), body),
		)
