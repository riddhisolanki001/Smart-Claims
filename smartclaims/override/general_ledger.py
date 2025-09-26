import frappe
from erpnext.accounts import general_ledger as gl_module
from erpnext.accounts.general_ledger import distribute_gl_based_on_cost_center_allocation, toggle_debit_credit_if_negative,merge_similar_entries
from erpnext.accounts.utils import (
	get_account_currency
)
from frappe.utils import flt

def custom_process_gl_map(gl_map, merge_entries=True, precision=None, from_repost=False):
    if not gl_map:
        return []

    doc = frappe._dict(gl_map[0]) if gl_map else None
    if doc and doc.voucher_type == "Payment Entry":
        pe = frappe.get_doc("Payment Entry", doc.voucher_no)
        if pe.apply_tax_withholding_amount:
            if gl_map[0].voucher_type != "Period Closing Voucher":
                gl_map = distribute_gl_based_on_cost_center_allocation(gl_map, precision, from_repost)

            # Skip merging entries
            # if merge_entries:
            #     gl_map = merge_similar_entries(gl_map, precision)

            gl_map = toggle_debit_credit_if_negative(gl_map)
            return gl_map
        
        else:
            if gl_map[0].voucher_type != "Period Closing Voucher":
                gl_map = distribute_gl_based_on_cost_center_allocation(gl_map, precision, from_repost)

            if merge_entries:
                gl_map = merge_similar_entries(gl_map, precision)

            gl_map = toggle_debit_credit_if_negative(gl_map)
            return gl_map

gl_module.process_gl_map = custom_process_gl_map


from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

def custom_add_tax_gl_entries(self, gl_entries):
    if self.apply_tax_withholding_amount:
        if gl_entries:
            first_account = gl_entries[0]["account"]  # Store first account

        for d in self.get("taxes"):
            account_currency = get_account_currency(d.account_head)
            if account_currency != self.company_currency:
                frappe.throw(_("Currency for {0} must be {1}").format(d.account_head, self.company_currency))

            # Determine debit/credit based on payment type and tax type
            if self.payment_type in ("Pay", "Internal Transfer"):
                dr_or_cr = "debit" if d.add_deduct_tax == "Add" else "credit"
                rev_dr_or_cr = "credit" if dr_or_cr == "debit" else "debit"
                against = self.party or self.paid_from
            elif self.payment_type == "Receive":
                dr_or_cr = "credit" if d.add_deduct_tax == "Add" else "debit"
                rev_dr_or_cr = "credit" if dr_or_cr == "debit" else "debit"
                against = self.party or self.paid_to

            # Create reversal entry first (for proper ordering)
            if not d.included_in_paid_amount:
                reversal_entry = {
                    "account": first_account,  # <-- Use first GL entry account
                    "against": against,
                    rev_dr_or_cr: d.tax_amount,
                    rev_dr_or_cr + "_in_account_currency": d.base_tax_amount if account_currency == self.company_currency else d.tax_amount,
                    rev_dr_or_cr + "_in_transaction_currency": d.base_tax_amount / self.transaction_exchange_rate,
                    "cost_center": self.cost_center,
                    "post_net_value": True,
                }

                # Only set party_type/party if the account is Receivable/Payable
                account_type = frappe.get_value("Account", first_account, "account_type")
                if account_type in ("Receivable", "Payable"):
                    reversal_entry["party_type"] = "Supplier"  
                    reversal_entry["party"] = self.party

                gl_entries.append(self.get_gl_dict(reversal_entry, account_currency, item=d))

            # Then append the original tax entry
            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": d.account_head,
                        "against": against,
                        dr_or_cr: d.tax_amount,
                        dr_or_cr + "_in_account_currency": d.base_tax_amount if account_currency == self.company_currency else d.tax_amount,
                        dr_or_cr + "_in_transaction_currency": d.base_tax_amount / self.transaction_exchange_rate,
                        "cost_center": d.cost_center,
                        "post_net_value": True,
                    },
                    account_currency,
                    item=d,
                )
            )
    else:
        for d in self.get("taxes"):
            account_currency = get_account_currency(d.account_head)
            if account_currency != self.company_currency:
                frappe.throw(_("Currency for {0} must be {1}").format(d.account_head, self.company_currency))

            if self.payment_type in ("Pay", "Internal Transfer"):
                dr_or_cr = "debit" if d.add_deduct_tax == "Add" else "credit"
                rev_dr_or_cr = "credit" if dr_or_cr == "debit" else "debit"
                against = self.party or self.paid_from
            elif self.payment_type == "Receive":
                dr_or_cr = "credit" if d.add_deduct_tax == "Add" else "debit"
                rev_dr_or_cr = "credit" if dr_or_cr == "debit" else "debit"
                against = self.party or self.paid_to

            payment_account = self.get_party_account_for_taxes()
            tax_amount = d.tax_amount
            base_tax_amount = d.base_tax_amount

            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": d.account_head,
                        "against": against,
                        dr_or_cr: tax_amount,
                        dr_or_cr + "_in_account_currency": base_tax_amount
                        if account_currency == self.company_currency
                        else d.tax_amount,
                        dr_or_cr + "_in_transaction_currency": base_tax_amount
                        / self.transaction_exchange_rate,
                        "cost_center": d.cost_center,
                        "post_net_value": True,
                    },
                    account_currency,
                    item=d,
                )
            )

            if not d.included_in_paid_amount:
                if get_account_currency(payment_account) != self.company_currency:
                    if self.payment_type == "Receive":
                        exchange_rate = self.target_exchange_rate
                    elif self.payment_type in ["Pay", "Internal Transfer"]:
                        exchange_rate = self.source_exchange_rate
                    base_tax_amount = flt((tax_amount / exchange_rate), self.precision("paid_amount"))

                gl_entries.append(
                    self.get_gl_dict(
                        {
                            "account": payment_account,
                            "against": against,
                            rev_dr_or_cr: tax_amount,
                            rev_dr_or_cr + "_in_account_currency": base_tax_amount
                            if account_currency == self.company_currency
                            else d.tax_amount,
                            rev_dr_or_cr + "_in_transaction_currency": base_tax_amount
                            / self.transaction_exchange_rate,
                            "cost_center": self.cost_center,
                            "post_net_value": True,
                        },
                        account_currency,
                        item=d,
                    )
                )        


def get_party_name_map():
	party_map = {}

	customers = frappe.get_all("Customer", fields=["name", "customer_name"])
	party_map["Customer"] = {c.name: c.customer_name for c in customers}

	suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name"])
	party_map["Supplier"] = {s.name: s.supplier_name for s in suppliers}

	employees = frappe.get_all("Employee", fields=["name", "employee_name"])
	party_map["Employee"] = {e.name: e.employee_name for e in employees}
	return party_map

PaymentEntry.add_tax_gl_entries = custom_add_tax_gl_entries

from erpnext.accounts.report.general_ledger import general_ledger as gl_report
from erpnext.accounts.report.general_ledger.general_ledger import get_gl_entries,convert_to_presentation_currency,get_conditions,get_currency

def custom_get_gl_entries(filters, accounting_dimensions):
    currency_map = get_currency(filters)
    select_fields = """, debit, credit, debit_in_account_currency,
        credit_in_account_currency """

    if filters.get("show_remarks"):
        if remarks_length := frappe.db.get_single_value("Accounts Settings", "general_ledger_remarks_length"):
            select_fields += f",substr(remarks, 1, {remarks_length}) as 'remarks'"
        else:
            select_fields += """,remarks"""

    order_by_statement = "order by posting_date, account, creation"

    if filters.get("include_dimensions"):
        order_by_statement = "order by posting_date, creation"

    if filters.get("categorize_by") == "Categorize by Voucher":
        order_by_statement = "order by posting_date, voucher_type, voucher_no"
    if filters.get("categorize_by") == "Categorize by Account":
        order_by_statement = "order by account, posting_date, creation"

    if filters.get("include_default_book_entries"):
        filters["company_fb"] = frappe.get_cached_value(
            "Company", filters.get("company"), "default_finance_book"
        )

    dimension_fields = ""
    if accounting_dimensions:
        dimension_fields = ", ".join(accounting_dimensions) + ","

    transaction_currency_fields = ""
    if filters.get("add_values_in_transaction_currency"):
        transaction_currency_fields = (
            "debit_in_transaction_currency, credit_in_transaction_currency, transaction_currency,"
        )

    # CASE 1: Supplier filter applied (special handling)
    if filters.get("party_type") == "Supplier" and filters.get("party_name"):
        company_abbr = frappe.get_cached_value("Company", filters.get("company"), "abbr")

        gl_entries = frappe.db.sql(
            f"""
            select
                name as gl_entry, posting_date, account, party_type, party,
                voucher_type, voucher_subtype, voucher_no, {dimension_fields}
                cost_center, project, {transaction_currency_fields}
                against_voucher_type, against_voucher, account_currency,
                against, is_opening, creation {select_fields}
            from `tabGL Entry`
            where company=%(company)s
              and account != '04-04-003 - Withholding Taxes - {company_abbr}'
              and not (
                  party_type = 'Supplier'
                  and against = party
                  and voucher_type = 'Payment Entry'
              )
              {get_conditions(filters)}
            {order_by_statement}
            """,
            filters,
            as_dict=1,
        )

        # then add withholding GL manually
        extra_entries = []
        for gl_entry in gl_entries:
            if gl_entry.voucher_type == "Payment Entry":
                pe = frappe.get_doc("Payment Entry", gl_entry.voucher_no)
                if pe.apply_tax_withholding_amount:
                    withholding_gl = frappe.db.sql(
                        f"""
                        SELECT name as gl_entry, posting_date, account, party_type, party,
                             voucher_type, voucher_no, cost_center, project,
                            against_voucher_type, against_voucher, account_currency,
                            against, is_opening, creation,
                            COALESCE(debit, 0) as debit,
                            COALESCE(credit, 0) as credit,
                            COALESCE(debit_in_account_currency, 0) as debit_in_account_currency,
                            COALESCE(credit_in_account_currency, 0) as credit_in_account_currency,
                            COALESCE(debit_in_transaction_currency, 0) as debit_in_transaction_currency,
                            COALESCE(credit_in_transaction_currency, 0) as credit_in_transaction_currency
                        FROM `tabGL Entry`
                        WHERE voucher_type = 'Payment Entry'
                        AND voucher_no = %s
                        AND account = '04-04-003 - Withholding Taxes - {company_abbr}'
                        """,
                        gl_entry.voucher_no,
                        as_dict=True,
                    )
                    extra_entries.extend(withholding_gl)

        gl_entries.extend(extra_entries)

    # CASE 2: Normal flow
    else:
        gl_entries = frappe.db.sql(
            f"""
            select
                name as gl_entry, posting_date, account, party_type, party,
                voucher_type, voucher_subtype, voucher_no, {dimension_fields}
                cost_center, project, {transaction_currency_fields}
                against_voucher_type, against_voucher, account_currency,
                against, is_opening, creation {select_fields}
            from `tabGL Entry`
            where company=%(company)s {get_conditions(filters)}
            {order_by_statement}
            """,
            filters,
            as_dict=1,
        )

    # Add party_name map
    party_name_map = get_party_name_map()
    for gl_entry in gl_entries:
        if gl_entry.party_type and gl_entry.party:
            gl_entry.party_name = party_name_map.get(gl_entry.party_type, {}).get(gl_entry.party)

    # Currency conversion if needed
    if filters.get("presentation_currency"):
        return convert_to_presentation_currency(gl_entries, currency_map, filters)
    else:
        return gl_entries


gl_report.get_gl_entries = custom_get_gl_entries