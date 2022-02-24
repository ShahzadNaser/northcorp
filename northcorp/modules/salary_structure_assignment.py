# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe

def before_save(doc, method):
    if doc.base:
        emp_working_hours = frappe.db.get_value("Employee",doc.employee,'working_hours') or 8
        emp_working_days = frappe.db.get_value("Department",doc.department,'working_days') or 30

        doc.hourly_rate = round(doc.base/(emp_working_days*emp_working_hours), 2)
