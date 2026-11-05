# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

# Items Below Safety Stock - stock items whose stock per company is below the item's safety stock.
# Moved from the UI Script Report of the same name; adds Requested Qty (open Material Requests)
# and On Order Qty (open Purchase Orders).

import frappe
from frappe import _


def execute(filters: dict | None = None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
	return [
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 160},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("Actual Qty"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Safety Stock"), "fieldname": "safety_stock", "fieldtype": "Float", "width": 100},
		{"label": _("Shortage"), "fieldname": "shortage", "fieldtype": "Float", "width": 100},
		{"label": _("Requested Qty (MR)"), "fieldname": "requested_qty", "fieldtype": "Float", "width": 130},
		{"label": _("On Order Qty (PO)"), "fieldname": "ordered_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 100},
		{"label": _("Reorder Qty"), "fieldname": "reorder_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Suggested Order"), "fieldname": "suggested_order", "fieldtype": "Float", "width": 120},
	]


def get_data(filters: dict) -> list[dict]:
	# requested_qty = Bin.indented_qty: qty on submitted Material Requests not yet converted to a
	# Purchase Order (ERPNext keeps it per warehouse; stopped/closed/cancelled MRs are excluded).
	# ordered_qty = Bin.ordered_qty: qty on submitted Purchase Orders not yet received.
	return frappe.db.sql(
		"""
		SELECT
			c.name AS company,
			i.item_group AS item_group,
			i.name AS item_code,
			i.item_name AS item_name,
			i.stock_uom AS uom,
			IFNULL(s.actual_qty, 0) AS actual_qty,
			i.safety_stock AS safety_stock,
			i.safety_stock - IFNULL(s.actual_qty, 0) AS shortage,
			IFNULL(s.requested_qty, 0) AS requested_qty,
			IFNULL(s.ordered_qty, 0) AS ordered_qty,
			IFNULL(r.reorder_level, 0) AS reorder_level,
			IFNULL(r.reorder_qty, 0) AS reorder_qty,
			GREATEST(i.safety_stock - IFNULL(s.actual_qty, 0),
				IFNULL(r.reorder_qty, 0)) AS suggested_order
		FROM `tabItem` i
		CROSS JOIN `tabCompany` c
		LEFT JOIN (
			SELECT b.item_code, w.company,
				SUM(b.actual_qty) AS actual_qty,
				SUM(b.indented_qty) AS requested_qty,
				SUM(b.ordered_qty) AS ordered_qty
			FROM `tabBin` b
			JOIN `tabWarehouse` w ON w.name = b.warehouse
			GROUP BY b.item_code, w.company
		) s ON s.item_code = i.name AND s.company = c.name
		LEFT JOIN (
			SELECT ir.parent AS item_code, w.company,
				SUM(ir.warehouse_reorder_level) AS reorder_level,
				SUM(ir.warehouse_reorder_qty) AS reorder_qty
			FROM `tabItem Reorder` ir
			JOIN `tabWarehouse` w ON w.name = ir.warehouse
			WHERE ir.parenttype = 'Item'
			GROUP BY ir.parent, w.company
		) r ON r.item_code = i.name AND r.company = c.name
		WHERE i.is_stock_item = 1
			AND i.disabled = 0
			AND i.safety_stock > 0
			AND IFNULL(s.actual_qty, 0) < i.safety_stock
			AND (s.item_code IS NOT NULL OR r.item_code IS NOT NULL) -- only items this company actually stocks (stock records or a reorder rule in its warehouses)
			AND (%(company)s = '' OR c.name = %(company)s)
		ORDER BY c.name, i.item_group, i.name
		""",
		{"company": filters.get("company") or ""},
		as_dict=True,
	)
