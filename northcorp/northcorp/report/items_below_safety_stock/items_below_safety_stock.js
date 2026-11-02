// Copyright (c) 2026, Shahzad Naser and contributors
// For license information, please see license.txt

frappe.query_reports["Items Below Safety Stock"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (["shortage", "suggested_order"].includes(column.fieldname) && data) {
			value = "<b>" + value + "</b>";
		}
		if (column.fieldname === "requested_qty" && data && data.requested_qty > 0) {
			value = "<span style='color:#1f6f43'><b>" + value + "</b></span>";
		}
		return value;
	},
};
