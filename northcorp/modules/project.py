# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _

try:
    from erpnext.projects.doctype.project.project import get_tasks_in_dependency_order
except ImportError:
    # erpnext < 16.5x: no dependency ordering, close tasks in any order
    def get_tasks_in_dependency_order(project, status):
        return frappe.get_all("Task", filters={"project": project, "status": ["!=", status]}, pluck="name")

@frappe.whitelist()
def set_project_status(project: str, status: str):
    '''
    set status for project and all related tasks
    (erpnext's version plus the 'Defect Liability Period' project status)
    '''
    if status not in ('Completed', 'Cancelled', 'Defect Liability Period'):
        frappe.throw(_('Status must be Cancelled, Completed or Defect Liability Period'))

    project = frappe.get_doc('Project', project)
    project.check_permission("write")

    if status in ('Completed', 'Cancelled'):
        for task_name in get_tasks_in_dependency_order(project.name, status):
            task = frappe.get_doc("Task", task_name)
            task.status = status
            task.flags.ignore_reschedule = True
            # same as erpnext: write access on the project is enough to close its tasks
            task.save(ignore_permissions=True)

    project.status = status
    project.save()
