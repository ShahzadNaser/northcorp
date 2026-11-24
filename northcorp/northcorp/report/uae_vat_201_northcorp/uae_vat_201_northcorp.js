// Copyright (c) 2026, Shahzad Naser and contributors
// For license information, please see license.txt

// Same filters as the standard UAE VAT 201 report.
frappe.query_reports["UAE VAT 201 Northcorp"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Section headings in bold, as in the standard report
		if (data && data.legend && (data.legend.includes("VAT on Sales") || data.legend.includes("VAT on Expenses"))) {
			value = "<b>" + value + "</b>";
		}
		return value;
	},
};
