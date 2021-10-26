# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

@frappe.whitelist()
def set_project_status(project, status):
    '''
    set status for project and all related tasks
    '''
    if not status in ('Completed', 'Cancelled', 'Defect Liability Period'):
        frappe.throw(_('Status must be Cancelled or Completed'))

    project = frappe.get_doc('Project', project)
    frappe.has_permission(doc = project, throw = True)

    if status in ('Completed', 'Cancelled'):
        for task in frappe.get_all('Task', dict(project = project.name)):
            frappe.db.set_value('Task', task.name, 'status', status)

    project.status = status
    project.save()
