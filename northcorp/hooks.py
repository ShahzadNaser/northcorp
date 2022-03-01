from . import __version__ as app_version

app_name = "northcorp"
app_title = "northcorp"
app_publisher = "Shahzad Naser"
app_description = "northcorp"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "shahzadnaser1122@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/northcorp/css/northcorp.css"
# app_include_js = "/assets/northcorp/js/northcorp.js"

# include js, css files in header of web template
# web_include_css = "/assets/northcorp/css/northcorp.css"
# web_include_js = "/assets/northcorp/js/northcorp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "northcorp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "northcorp.install.before_install"
# after_install = "northcorp.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "northcorp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Payroll Entry": "northcorp.modules.payroll_entry.CustomPayrollEntry",
	"Salary Slip": "northcorp.modules.salary_slip.CustomSalarySlip"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Salary Slip":{
		"before_save" :  "northcorp.modules.salary_slip.before_save",
		"before_submit" :  "northcorp.modules.salary_slip.before_submit"
	},
   	"Salary Structure Assignment":{
		"before_save" :  "northcorp.modules.salary_structure_assignment.before_save"
	},
	"Attendance":{
		"before_submit":"northcorp.modules.attendance.before_submit",
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"northcorp.tasks.all"
# 	],
# 	"daily": [
# 		"northcorp.tasks.daily"
# 	],
# 	"hourly": [
# 		"northcorp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"northcorp.tasks.weekly"
# 	]
# 	"monthly": [
# 		"northcorp.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "northcorp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "northcorp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "northcorp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

user_data_fields = [
	{
		"doctype": "{doctype_1}",
		"filter_by": "{filter_by}",
		"redact_fields": ["{field_1}", "{field_2}"],
		"partial": 1,
	},
	{
		"doctype": "{doctype_2}",
		"filter_by": "{filter_by}",
		"partial": 1,
	},
	{
		"doctype": "{doctype_3}",
		"strict": False,
	},
	{
		"doctype": "{doctype_4}"
	}
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"northcorp.auth.validate"
# ]


doctypes_list = ["Purchase Order", "Purchase Order Item", "Supplier", "Project", "Request for Quotation"]

fixtures = [
    {"doctype": "Client Script", "filters": [
        [
            "dt", "in", doctypes_list
        ]
    ]},
    {"doctype": "Property Setter", "filters": [
        [
            "doc_type", "in", doctypes_list
        ]
    ]},
    {"doctype": "Custom Field", "filters": [
        [
            "dt", "in", doctypes_list
        ]
    ]}
]

# from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
# from northcorp.modules.project import set_project_status

# SalarySlip.get_data_for_eval = get_data_for_eval


override_whitelisted_methods = {
	'erpnext.projects.doctype.project.project.set_project_status' : 'northcorp.modules.project.set_project_status'
}
