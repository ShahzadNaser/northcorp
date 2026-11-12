// Copyright (c) 2026, Shahzad Naser and contributors
// For license information, please see license.txt

frappe.ui.form.on("Insurance Claim", {
	refresh(frm) {
		if (frm.doc.late_reporting) {
			frm.dashboard.set_headline_alert(
				__("Reported {0} hours after the incident, beyond the policy's {1}-hour limit. The insurer may reject the claim.",
					[flt(frm.doc.hours_to_report, 1), frm.doc.claim_notice_hours]), "red");
		}
		if (frm.is_new() || frm.doc.reported_to_broker_on) return;
		frm.dashboard.set_headline_alert(__("Not yet reported to the broker. Report it the same day."), "orange");
		frm.add_custom_button(__("Notify Broker"), () => {
			frappe.confirm(__("Email this loss notification to the policy's broker?"), () => {
				frappe.call({
					method: "northcorp.northcorp.doctype.insurance_claim.insurance_claim.notify_broker",
					args: { name: frm.doc.name },
					freeze: true,
				}).then(() => {
					frappe.show_alert({ message: __("Loss notification emailed to broker"), indicator: "green" });
					frm.reload_doc();
				});
			});
		});
	},
});
