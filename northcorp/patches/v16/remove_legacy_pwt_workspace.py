import frappe

WORKSPACE = "Project Wise Timesheet"


def execute():
    '''
    Delete the 2022 "Project Wise Timesheet" workspace.

    Since the Frappe v16 desk router, a workspace with the same name as a DocType
    takes over that DocType's routes (/desk/<module>/project-wise-timesheet/...),
    so the list view and saved reports such as "Electrical Dept - PWT Report"
    opened this empty workspace instead and crashed (content is null).
    The JSON was removed from the app in the same change so migrate doesn't
    recreate it. Other workspaces ("NorthCorp", "Project Timesheets") are untouched.
    '''
    ws = frappe.db.get_value("Workspace", WORKSPACE, ["module", "content"], as_dict=True)
    if not ws:
        return

    # only remove the legacy, layout-less record from this app
    if ws.module != "northcorp" or ws.content not in (None, "", "[]"):
        return

    frappe.delete_doc("Workspace", WORKSPACE, force=True, ignore_permissions=True)
