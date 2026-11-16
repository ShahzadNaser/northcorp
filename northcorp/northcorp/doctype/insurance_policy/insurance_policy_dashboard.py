from frappe import _


def get_data():
	return {
		"fieldname": "insurance_policy",
		"transactions": [
			{"label": _("Claims"), "items": ["Insurance Claim"]},
		],
	}
