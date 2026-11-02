# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import formatdate, get_url, nowdate

# Items Below Safety Stock - Weekly Email (cron "0 8 * * 1" = Monday 08:00, see hooks.py)
# One email per company with the items that company stocks which are below safety stock (+ CSV attachment).
# Only items that had stock in that company at some point in the last STOCK_DAYS days are included.
# Moved from the Server Script "Items Below Safety Stock - Weekly Email"; adds Requested (MR) qty.
SAFETY_STOCK_RECIPIENTS = {
	"NORTHCORP INDUSTRY LLC": [
		"radheshyam@northcorp.ae",
		"joby.john@northcorp.ae",
		"farooq.gujjar@northcorp.ae",
		"devanand.suresh@northcorp.ae",
		"naseer.basheer@northcorp.ae",
	],
	"NORTHCORP LLC": [
		"radheshyam@northcorp.ae",
		"farooq.gujjar@northcorp.ae",
		"devanand.suresh@northcorp.ae",
		"naseer.basheer@northcorp.ae",
	],
}
STOCK_DAYS = 365

# requested_qty = Bin.indented_qty: qty on submitted Material Requests not yet converted to a Purchase Order.
SAFETY_STOCK_SQL = """
	SELECT
		i.item_group AS item_group,
		i.name AS item_code,
		i.item_name AS item_name,
		i.stock_uom AS uom,
		IFNULL(s.actual_qty, 0) AS actual_qty,
		i.safety_stock AS safety_stock,
		i.safety_stock - IFNULL(s.actual_qty, 0) AS shortage,
		IFNULL(s.requested_qty, 0) AS requested_qty,
		IFNULL(r.reorder_level, 0) AS reorder_level,
		IFNULL(r.reorder_qty, 0) AS reorder_qty,
		GREATEST(i.safety_stock - IFNULL(s.actual_qty, 0), IFNULL(r.reorder_qty, 0)) AS suggested_order
	FROM `tabItem` i
	LEFT JOIN (
		SELECT b.item_code, SUM(b.actual_qty) AS actual_qty, SUM(b.indented_qty) AS requested_qty
		FROM `tabBin` b
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %(company)s
		GROUP BY b.item_code
	) s ON s.item_code = i.name
	LEFT JOIN (
		SELECT ir.parent AS item_code,
			SUM(ir.warehouse_reorder_level) AS reorder_level,
			SUM(ir.warehouse_reorder_qty) AS reorder_qty
		FROM `tabItem Reorder` ir
		JOIN `tabWarehouse` w ON w.name = ir.warehouse
		WHERE ir.parenttype = 'Item' AND w.company = %(company)s
		GROUP BY ir.parent
	) r ON r.item_code = i.name
	WHERE i.is_stock_item = 1
		AND i.disabled = 0
		AND i.safety_stock > 0
		AND IFNULL(s.actual_qty, 0) < i.safety_stock
		AND (
			IFNULL(s.actual_qty, 0) > 0
			OR EXISTS (
				SELECT 1
				FROM `tabStock Ledger Entry` sle
				WHERE sle.item_code = i.name
					AND sle.company = %(company)s
					AND sle.is_cancelled = 0
					AND sle.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(days)s DAY)
					AND (sle.qty_after_transaction > 0 OR sle.actual_qty < 0)
			)
		)
	ORDER BY i.item_group, i.name
"""

CSV_FIELDS = [
	("Item Group", "item_group"),
	("Item Code", "item_code"),
	("Item Name", "item_name"),
	("UOM", "uom"),
	("Actual Qty", "actual_qty"),
	("Safety Stock", "safety_stock"),
	("Shortage", "shortage"),
	("Requested Qty (MR)", "requested_qty"),
	("Reorder Level", "reorder_level"),
	("Reorder Qty", "reorder_qty"),
	("Suggested Order", "suggested_order"),
]


def send_items_below_safety_stock_email(test_to=None):
	"""Weekly email. For a test run send everything to one address:
	bench --site <site> execute northcorp.tasks.send_items_below_safety_stock_email --kwargs "{'test_to': 'you@northcorp.ae'}"
	"""
	today = formatdate(nowdate(), "dd-MMM-yyyy")
	sent = []
	for company, recipients in SAFETY_STOCK_RECIPIENTS.items():
		rows = frappe.db.sql(SAFETY_STOCK_SQL, {"company": company, "days": STOCK_DAYS}, as_dict=True)
		if not rows:
			continue

		users = frappe.get_all(
			"User",
			filters=[["name", "in", recipients], ["enabled", "=", 1]],
			fields=["name", "first_name", "full_name"],
		)
		names = ", ".join([u.first_name or u.full_name or u.name for u in users])
		short = "NRI" if "INDUSTRY" in company else "NRC"

		html = frappe.render_template(
			"northcorp/templates/emails/items_below_safety_stock.html",
			{
				"rows": rows,
				"company": company,
				"short": company,
				"names": names,
				"today": today,
				"zero": len([r for r in rows if not r.actual_qty]),
				"requested": len([r for r in rows if r.requested_qty]),
				"groups": len({r.item_group for r in rows}),
				"report_url": get_url("/app/query-report/Items Below Safety Stock")
				+ "?company="
				+ company.replace(" ", "%20"),
			},
		)
		subject = (
			("[TEST] " if test_to else "")
			+ "Items below safety stock - "
			+ company
			+ " - "
			+ str(len(rows))
			+ " items ("
			+ today
			+ ")"
		)
		frappe.sendmail(
			recipients=[test_to] if test_to else [u.name for u in users],
			subject=subject,
			message=html,
			attachments=[
				{
					"fname": "Items below safety stock - " + short + " - " + nowdate() + ".csv",
					"fcontent": get_csv(rows),
				}
			],
		)
		sent.append([company, len(rows), [u.full_name for u in users]])
	return sent


def get_csv(rows):
	def cell(x):
		return '"' + str(x if x is not None else "").replace('"', '""') + '"'

	lines = [",".join([label for label, _ in CSV_FIELDS])]
	for r in rows:
		lines.append(",".join([cell(r.get(field)) for _, field in CSV_FIELDS]))
	return "\n".join(lines) + "\n"
