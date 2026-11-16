# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate

EXPIRING_DAYS = 30


class SubcontractorInsuranceCertificate(Document):
	def validate(self):
		if getdate(self.valid_to) < getdate(self.valid_from):
			frappe.throw(_("Valid To cannot be before Valid From."))
		self.status = get_status(self.valid_to)


def get_status(valid_to):
	today = getdate(nowdate())
	valid_to = getdate(valid_to)
	if valid_to < today:
		return "Expired"
	if valid_to <= getdate(add_days(today, EXPIRING_DAYS)):
		return "Expiring Soon"
	return "Valid"
