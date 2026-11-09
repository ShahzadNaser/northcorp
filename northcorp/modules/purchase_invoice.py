import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import make_purchase_receipt

# Final state of "Purchase Invoices Workflow" / "Purchase Receipt Workflow"
PI_FINAL_STATE = "Submitted"
PR_FINAL_STATE = "Submitted"
# Marks receipts made by this module; used to find them again on invoice cancel
AUTO_REMARK = "Auto-created from Purchase Invoice {0}"


def on_update_after_submit(doc, method=None):
	"""When a Purchase Invoice reaches its final workflow state, create and submit a
	Purchase Receipt for its PO-linked service lines (non-stock, non-asset items).

	- Same item names and descriptions as the invoice lines.
	- Only the balance still open on each PO line is received, so receipts already
	  made against the PO (full or partial) are taken into account.
	- At most one auto receipt per invoice.
	"""
	if doc.get("workflow_state") != PI_FINAL_STATE or not doc.has_value_changed("workflow_state"):
		return
	if doc.update_stock or doc.is_return:
		return
	if frappe.db.exists(
		"Purchase Receipt Item", {"purchase_invoice": doc.name, "docstatus": ["<", 2]}
	):
		return

	service_items = get_service_items(doc)
	if not service_items:
		return

	pr = build_purchase_receipt(doc, service_items)
	if not pr.items:
		return

	pr.flags.ignore_permissions = True
	pr.insert()
	# Submitting from code puts the PR in the first submitted workflow state
	# ("Accounts - To Approve"); move it to the final state so it doesn't wait there.
	pr.submit()
	if pr.meta.get_workflow():
		pr.db_set("workflow_state", PR_FINAL_STATE, update_modified=False)

	frappe.msgprint(
		_("Purchase Receipt {0} created and submitted for the service items.").format(
			frappe.bold(pr.name)
		),
		alert=True,
		indicator="green",
	)


def before_cancel(doc, method=None):
	"""Cancel the Purchase Receipt(s) auto-created from this invoice.

	Runs before the invoice is cancelled so Frappe's linked-document check doesn't
	block the cancellation. Receipts made by hand from the invoice are not touched;
	they still block the cancellation in the standard way. If a receipt can't be
	cancelled (e.g. a Landed Cost Voucher points to it), the invoice cancellation
	stops with that error and nothing is cancelled.
	"""
	for name in get_auto_receipts(doc.name):
		pr = frappe.get_doc("Purchase Receipt", name)
		pr.flags.ignore_permissions = True
		pr.cancel()
		set_cancelled_workflow_state(pr)
		pr.add_comment(
			"Info", _("Cancelled automatically with Purchase Invoice {0}").format(doc.name)
		)
		frappe.msgprint(
			_("Purchase Receipt {0} cancelled with this invoice.").format(frappe.bold(name)),
			alert=True,
			indicator="orange",
		)


def get_auto_receipts(invoice):
	parents = frappe.get_all(
		"Purchase Receipt Item",
		filters={"purchase_invoice": invoice, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	if not parents:
		return []
	return frappe.get_all(
		"Purchase Receipt",
		filters={
			"name": ["in", parents],
			"docstatus": 1,
			"remarks": ["like", AUTO_REMARK.format(invoice) + "%"],
		},
		pluck="name",
	)


def set_cancelled_workflow_state(pr):
	if not pr.meta.get_workflow():
		return
	workflow = frappe.get_doc("Workflow", pr.meta.get_workflow())
	states = [s.state for s in workflow.states if str(s.doc_status) == "2"]
	if not states or pr.get(workflow.workflow_state_field) in states:
		return
	state = "Cancelled" if "Cancelled" in states else states[0]
	pr.db_set(workflow.workflow_state_field, state, update_modified=False)


def get_service_items(doc):
	codes = list({d.item_code for d in doc.items if d.item_code and d.purchase_order})
	if not codes:
		return set()
	return set(
		frappe.get_all(
			"Item",
			filters={"name": ["in", codes], "is_stock_item": 0, "is_fixed_asset": 0},
			pluck="name",
		)
	)


def build_purchase_receipt(doc, service_items):
	pr = make_purchase_receipt(doc.name)
	pi_rows = {d.name: d for d in doc.items}

	rows = [d for d in pr.items if d.item_code in service_items and d.purchase_order]
	default_wh = next((d.warehouse for d in rows if d.warehouse), None)

	po_balance = get_po_balance([d.purchase_order_item for d in rows if d.purchase_order_item])

	final = []
	for d in rows:
		balance = po_balance.get(d.purchase_order_item, 0)
		if balance <= 0:
			continue  # PO line already fully received

		qty = min(flt(d.qty), balance)
		po_balance[d.purchase_order_item] = balance - qty

		src = pi_rows.get(d.purchase_invoice_item)
		if src:
			d.item_name = src.item_name
			d.description = src.description
		if not d.warehouse and default_wh:
			d.warehouse = default_wh

		d.qty = qty
		d.received_qty = qty
		d.rejected_qty = 0
		d.stock_qty = qty * flt(d.conversion_factor or 1)
		d.amount = qty * flt(d.rate)
		final.append(d)

	pr.set("items", final)
	pr.posting_date = doc.posting_date
	pr.set_posting_time = 1
	pr.remarks = AUTO_REMARK.format(doc.name) + " (service items)"
	return pr


def get_po_balance(po_detail_names):
	"""Open qty per PO line. received_qty counts every submitted receipt against the PO."""
	if not po_detail_names:
		return {}
	return {
		r.name: flt(r.qty) - flt(r.received_qty)
		for r in frappe.get_all(
			"Purchase Order Item",
			filters={"name": ["in", list(set(po_detail_names))]},
			fields=["name", "qty", "received_qty"],
		)
	}
