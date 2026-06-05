
import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import (
	add_to_date,
	flt,
	fmt_money,
	format_time,
	formatdate,
	get_link_to_report,
	get_url_to_form,
	get_url_to_list,
	now_datetime,
	today,
)
from erpnext.accounts.utils import get_balance_on, get_count_on, get_fiscal_year

from erpnext.setup.doctype.email_digest.email_digest import EmailDigest

class CustomEmailDigest(EmailDigest):
    def set_accounting_cards(self, context):
        """Create accounting cards if checked"""

        cache = frappe.cache()
        context.cards = []
        for key in (
            "income",
            "expenses_booked",
            "income_year_to_date",
            "expense_year_to_date",
            "bank_balance",
            "credit_balance",
            "invoiced_amount",
            "custom_retentions",
            "payables",
            "custom_supplier_advances",
            "sales_orders_to_bill",
            "purchase_orders_to_bill",
            "sales_order",
            "purchase_order",
            "sales_orders_to_deliver",
            "purchase_orders_to_receive",
            "sales_invoice",
            "purchase_invoice",
            "new_quotations",
            "pending_quotations",
        ):
            if self.get(key):
                cache_key = f"email_digest:card:{self.company}:{self.frequency}:{key}:{self.from_date}"
                card = cache.get(cache_key)

                if card:
                    card = frappe.safe_eval(card)

                else:
                    card = frappe._dict(getattr(self, "get_" + key)())

                    # format values
                    if card.last_value:
                        card.diff = int(flt(card.value - card.last_value) / card.last_value * 100)
                        if card.diff < 0:
                            card.diff = str(card.diff)
                            card.gain = False
                        else:
                            card.diff = "+" + str(card.diff)
                            card.gain = True

                        if key == "credit_balance":
                            card.last_value = card.last_value * -1
                        card.last_value = self.fmt_money(
                            card.last_value, False if key in ("bank_balance", "credit_balance") else True
                        )

                    if card.billed_value:
                        card.billed = int(flt(card.billed_value) / card.value * 100)
                        card.billed = "% Billed " + str(card.billed)

                    if card.delivered_value:
                        card.delivered = int(flt(card.delivered_value) / card.value * 100)
                        if key == "pending_sales_orders":
                            card.delivered = "% Delivered " + str(card.delivered)
                        else:
                            card.delivered = "% Received " + str(card.delivered)

                    if key == "credit_balance":
                        card.value = card.value * -1
                    card.value = self.fmt_money(
                        card.value, False if key in ("bank_balance", "credit_balance") else True
                    )

                    cache.set_value(cache_key, card, expires_in_sec=24 * 60 * 60)

                context.cards.append(card)

    def get_payables(self):
        account = "Creditors - NRC" if self.get("company") == "NORTHCORP LLC" else "Creditors - NRI"
        return self.get_type_balance("payables", "Payable", root_type=None, account=account)

    def get_custom_supplier_advances(self):
        account = "Supplier Advances - NRC" if self.get("company") == "NORTHCORP LLC" else "Supplier Advances - NRI"
        return self.get_type_balance("custom_supplier_advances", "Payable", root_type=None, account=account)

    def get_custom_retentions(self):
        account = "Customer Retentions - NRC" if self.get("company") == "NORTHCORP LLC" else "Customer Retentions - NRI"
        return self.get_type_balance("custom_retentions", "Receivable", root_type=None, account=account)


    def get_type_balance(self, fieldname, account_type, root_type=None, account=None):

        temp_filters={"account_type": account_type, "company": self.company, "is_group": 0}

        if account:
            temp_filters["name"] = account

        frappe.log_error(temp_filters, "====temp_filters====") 
        if root_type:
            temp_filters["root_type"] = root_type
            accounts = [
                d.name
                for d in frappe.db.get_all(
                    "Account",
                    filters=temp_filters
                    )
            ]
        else:
            accounts = [
                d.name
                for d in frappe.db.get_all(
                    "Account", filters=temp_filters
                )
            ]

        balance = prev_balance = 0.0
        count = 0
        for account in accounts:
            balance += get_balance_on(account, date=self.future_to_date, in_account_currency=False)
            count += get_count_on(account, fieldname, date=self.future_to_date)
            prev_balance += get_balance_on(account, date=self.past_to_date, in_account_currency=False)

        if fieldname in ("bank_balance", "credit_balance"):
            label = ""
            if fieldname == "bank_balance":
                filters = {
                    "root_type": "Asset",
                    "account_type": "Bank",
                    "report_date": self.future_to_date,
                    "company": self.company,
                }
                label = get_link_to_report(
                    "Account Balance", label=_(self.meta.get_label(fieldname)), filters=filters
                )
            else:
                filters = {
                    "root_type": "Liability",
                    "account_type": "Bank",
                    "report_date": self.future_to_date,
                    "company": self.company,
                }
                label = get_link_to_report(
                    "Account Balance", label=_(self.meta.get_label(fieldname)), filters=filters
                )

            return {"label": label, "value": balance, "last_value": prev_balance}
        else:
            if account_type == "Payable":
                label = get_link_to_report(
                    "Accounts Payable",
                    label=_(self.meta.get_label(fieldname)),
                    filters={"report_date": self.future_to_date, "company": self.company},
                )
            elif account_type == "Receivable":
                label = get_link_to_report(
                    "Accounts Receivable",
                    label=_(self.meta.get_label(fieldname)),
                    filters={"report_date": self.future_to_date, "company": self.company},
                )
            else:
                label = _(self.meta.get_label(fieldname))

            return {"label": label, "value": balance, "last_value": prev_balance, "count": count}
