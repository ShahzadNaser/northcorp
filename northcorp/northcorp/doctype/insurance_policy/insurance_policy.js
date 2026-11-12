// Copyright (c) 2026, Shahzad Naser and contributors
// For license information, please see license.txt

const INS_POL = "northcorp.northcorp.doctype.insurance_policy.insurance_policy.";

frappe.ui.form.on("Insurance Policy", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	refresh(frm) {
		show_policy_indicators(frm);
		if (frm.is_new()) return;
		if (!frappe.user.has_role(["Accounts Manager", "Accounts User", "System Manager"])) return;

		const call = (method, args, msg) =>
			frappe.call({ method: INS_POL + method, args: Object.assign({ name: frm.doc.name }, args || {}), freeze: true })
				.then((r) => { if (msg) frappe.show_alert({ message: msg, indicator: "green" }); frm.reload_doc(); return r; });
		const open = ["Pending Check", "Active"].includes(frm.doc.status);

		if (open) {
			frm.add_custom_button(__("Confirm Policy Check"), () => {
				frm.save().then(() => call("confirm_check")).then((r) => {
					const issues = (r && r.message) || [];
					if (issues.length) {
						frappe.msgprint({ title: __("Policy Check Failed"), indicator: "red",
							message: __("Send these back to the broker for correction:") + "<ul><li>" + issues.join("</li><li>") + "</li></ul>" });
					} else {
						frappe.show_alert({ message: __("Policy check passed. The policy is now Active."), indicator: "green" });
					}
				});
			}, __("Actions"));

			frm.add_custom_button(__("Request Extension"), () => {
				frappe.prompt([
					{ fieldname: "new_expiry", fieldtype: "Date", label: __("New Expiry"), reqd: 1 },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason (e.g. project time extension)"), reqd: 1 },
				], (v) => call("request_extension", v, __("Extension request emailed to broker")), __("Request Extension"));
			}, __("Actions"));

			frm.add_custom_button(__("Request Sum Insured Change"), () => {
				frappe.prompt([
					{ fieldname: "new_sum_insured", fieldtype: "Currency", label: __("New Sum Insured"), reqd: 1 },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason (e.g. variations increased the contract value)"), reqd: 1 },
				], (v) => call("request_sum_insured_change", v, __("Request emailed to broker")), __("Request Sum Insured Change"));
			}, __("Actions"));

			frm.add_custom_button(__("Request Certificate (COI)"), () => {
				frappe.prompt([
					{ fieldname: "issued_to", fieldtype: "Data", label: __("Issued To"), reqd: 1 },
					{ fieldname: "purpose", fieldtype: "Data", label: __("Purpose") },
				], (v) => call("request_certificate", v, __("COI request emailed to broker")), __("Request Certificate"));
			}, __("Actions"));

			if (frm.doc.maintenance_months) {
				frm.add_custom_button(__("Notify Handover"), () => {
					frappe.prompt({ fieldname: "completion_date", fieldtype: "Date", label: __("Completion / Handover Date"), reqd: 1 },
						(v) => call("notify_handover", v, __("Handover notified to broker")), __("Notify Handover"));
				}, __("Actions"));
			}
		}

		if (frm.doc.status !== "Closed" && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Close Policy"), () => {
				frappe.confirm(__("Close this policy? It will no longer appear in expiry alerts."),
					() => call("close_policy", {}, __("Policy closed")));
			}, __("Actions"));
		}
	},
});

function show_policy_indicators(frm) {
	if (frm.is_new()) return;
	if (frm.doc.check_result === "Failed" && frm.doc.check_issues) {
		frm.dashboard.set_headline_alert(__("Policy check failed:") + "<br>" + frappe.utils.escape_html(frm.doc.check_issues).replace(/\n/g, "<br>"), "red");
	} else if (frm.doc.check_result === "Pending") {
		frm.dashboard.set_headline_alert(__("Check this policy against the contract, then use Actions > Confirm Policy Check."), "orange");
	}
	if (frm.doc.premium_due_date && !frm.doc.premium_paid) {
		const days = frappe.datetime.get_day_diff(frm.doc.premium_due_date, frappe.datetime.get_today());
		if (days <= 14) {
			frm.dashboard.add_comment(
				days < 0 ? __("Premium was due on {0} and isn't marked paid. Cover may be void.", [frappe.datetime.str_to_user(frm.doc.premium_due_date)])
					: __("Premium due in {0} days.", [days]),
				days < 0 ? "red" : "orange", true);
		}
	}
}
