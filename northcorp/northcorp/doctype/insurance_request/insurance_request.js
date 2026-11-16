// Copyright (c) 2026, Shahzad Naser and contributors
// For license information, please see license.txt

const INS_REQ = "northcorp.northcorp.doctype.insurance_request.insurance_request.";
const FINANCE_ROLES = ["Accounts Manager", "Accounts User", "System Manager"];
const FINANCE_MANAGER_ROLES = ["Accounts Manager", "System Manager"];

frappe.ui.form.on("Insurance Request", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const is_finance = frappe.user.has_role(FINANCE_ROLES);
		const is_manager = frappe.user.has_role(FINANCE_MANAGER_ROLES);
		const status = frm.doc.status;
		const call = (method, args, msg) =>
			frappe.call({ method: INS_REQ + method, args: Object.assign({ name: frm.doc.name }, args || {}), freeze: true })
				.then(() => { if (msg) frappe.show_alert({ message: msg, indicator: "green" }); frm.reload_doc(); });

		if (is_finance && ["Draft", "Sent to Brokers", "Quotes Received"].includes(status)) {
			frm.add_custom_button(__("Send to Brokers"), () => {
				frappe.confirm(__("Email this request to each broker that hasn't received it yet?"),
					() => call("send_to_brokers", {}, __("Request sent")));
			}, __("Actions"));
			if (status !== "Draft") {
				frm.add_custom_button(__("Resend to All Brokers"), () => {
					frappe.confirm(__("Email this request again to every broker in the table?"),
						() => call("send_to_brokers", { resend: 1 }, __("Request sent")));
				}, __("Actions"));
			}
		}

		if (is_manager && ["Sent to Brokers", "Quotes Received"].includes(status)) {
			frm.add_custom_button(__("Approve Selected Quote"), () => {
				const q = (frm.doc.quotes || []).find((r) => r.selected);
				if (!q) {
					frappe.msgprint(__("Tick Selected on the quote you want to approve."));
					return;
				}
				frappe.confirm(
					__("Approve the quote from {0} ({1}), premium {2}?", [q.insurer, q.broker,
						format_currency(q.premium, frm.doc.currency)]),
					() => call("approve_quote", {}, __("Quote approved")));
			}, __("Actions"));
		}

		if (is_finance && status === "Quote Approved") {
			frm.add_custom_button(__("Bind Cover (Email Broker)"), () => {
				frappe.confirm(__("Email the selected broker to bind the cover?"),
					() => call("mark_bound", {}, __("Binding instruction sent")));
			}, __("Actions"));
		}

		if (is_finance && status === "Bound" && !frm.doc.insurance_policy) {
			frm.add_custom_button(__("Create Insurance Policy"), () => {
				frappe.model.open_mapped_doc({ method: INS_REQ + "make_policy", frm: frm });
			}, __("Actions"));
		}

		if (!["Policy Issued", "Cancelled"].includes(status)) {
			frm.add_custom_button(__("Cancel Request"), () => {
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(v) => call("cancel_request", { reason: v.reason }, __("Request cancelled")),
					__("Cancel Request"));
			}, __("Actions"));
		}

		if ((frm.doc.quotes || []).length > 1) {
			frm.set_intro(__("Compare the quotes below on premium, deductible, TPL limit, maintenance cover and exclusions, then tick Selected on one."), "blue");
		}
	},
});

frappe.ui.form.on("Insurance Request Broker", {
	broker(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.broker) return;
		frappe.db.get_value("Supplier", row.broker, "email_id").then((r) => {
			if (r.message && r.message.email_id && !row.email) {
				frappe.model.set_value(cdt, cdn, "email", r.message.email_id);
			}
		});
	},
});

frappe.ui.form.on("Insurance Quote", {
	premium: (frm, cdt, cdn) => set_quote_total(cdt, cdn),
	vat: (frm, cdt, cdn) => set_quote_total(cdt, cdn),
	selected(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.selected) return;
		(frm.doc.quotes || []).forEach((q) => {
			if (q.name !== row.name && q.selected) frappe.model.set_value(q.doctype, q.name, "selected", 0);
		});
	},
});

function set_quote_total(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_premium", flt(row.premium) + flt(row.vat));
}
