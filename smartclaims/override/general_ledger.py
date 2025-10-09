import frappe
from erpnext.accounts import general_ledger as gl_module
from erpnext.accounts.general_ledger import distribute_gl_based_on_cost_center_allocation, toggle_debit_credit_if_negative,merge_similar_entries
from erpnext.accounts.utils import (
    get_account_currency
)
from frappe.utils import flt
from collections import OrderedDict
from frappe.utils import cstr, getdate


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
                    "against": d.account_head,
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

PaymentEntry.add_tax_gl_entries = custom_add_tax_gl_entries

from erpnext.accounts.report.general_ledger import general_ledger as gl_report
from erpnext.accounts.report.general_ledger.general_ledger import get_gl_entries,get_conditions
from erpnext.accounts.report.utils import convert_to_presentation_currency, get_currency,convert

def get_party_name_map():
    party_map = {}

    customers = frappe.get_all("Customer", fields=["name", "customer_name"])
    party_map["Customer"] = {c.name: c.customer_name for c in customers}

    suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name"])
    party_map["Supplier"] = {s.name: s.supplier_name for s in suppliers}

    employees = frappe.get_all("Employee", fields=["name", "employee_name"])
    party_map["Employee"] = {e.name: e.employee_name for e in employees}
    return party_map


def convert_to_presentation_currency(gl_entries, currency_info, filters=None):
    """
    Take a list of GL Entries and change the 'debit' and 'credit' values to currencies
    in `currency_info`.
    :param gl_entries:
    :param currency_info:
    :return:
    """
    converted_gl_list = []
    presentation_currency = currency_info["presentation_currency"]
    company_currency = currency_info["company_currency"]

    account_currencies = list(set(entry["account_currency"] for entry in gl_entries))
    exchange_gain_or_loss = False

    if filters and isinstance(filters.get("account"), list):
        account_filter = filters.get("account")
        gain_loss_account = frappe.db.get_value("Company", filters.company, "exchange_gain_loss_account")

        exchange_gain_or_loss = len(account_filter) == 1 and account_filter[0] == gain_loss_account

    for entry in gl_entries:
        debit = flt(entry["debit"])
        credit = flt(entry["credit"])
        debit_in_account_currency = flt(entry["debit_in_account_currency"])
        credit_in_account_currency = flt(entry["credit_in_account_currency"])
        account_currency = entry["account_currency"]

        if (
            len(account_currencies) == 1
            and account_currency == presentation_currency
            and not exchange_gain_or_loss
        ) and not (filters and filters.get("show_amount_in_company_currency")):
            entry["debit"] = debit_in_account_currency
            entry["credit"] = credit_in_account_currency
        else:
            date = currency_info["report_date"]
            converted_debit_value = convert(debit, presentation_currency, company_currency, date)
            converted_credit_value = convert(credit, presentation_currency, company_currency, date)

            if entry.get("debit"):
                entry["debit"] = converted_debit_value

            if entry.get("credit"):
                entry["credit"] = converted_credit_value

        converted_gl_list.append(entry)

    return converted_gl_list


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
        wht_account = f"04-04-003 - Withholding Taxes - {company_abbr}"

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

        adjusted_entries = []

        for e in gl_entries:
            if e["voucher_type"] == "Payment Entry":
                pe = frappe.get_doc("Payment Entry", e["voucher_no"])
                if pe.apply_tax_withholding_amount:
                    wht_total = sum(
                        x["debit"] for x in gl_entries 
                        if x["voucher_no"] == e["voucher_no"] and x["against"] == wht_account
                    )

                    if e["against"] != wht_account and e["debit"] > 0:
                        e["debit"] -= wht_total
                        e["debit_in_account_currency"] -= wht_total
            # Always append entry (whether adjusted or not)
            adjusted_entries.append(e)

        gl_entries = adjusted_entries
       
    elif filters.get("account"):
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
            {get_conditions(filters)}
            {order_by_statement}
            """,
            filters,
            as_dict=1,
        )

        processed_entries = []

        for gl_entry in gl_entries:
            if gl_entry.voucher_type == "Payment Entry":
                pe = frappe.get_doc("Payment Entry", gl_entry.voucher_no)
                if pe.paid_from == gl_entry.account and pe.apply_tax_withholding_amount:
                    withholding = frappe.db.get_value(
                        "GL Entry",
                        {
                            "voucher_type": "Payment Entry",
                            "voucher_no": gl_entry.voucher_no,
                            "account": f"04-04-003 - Withholding Taxes - {company_abbr}"
                        },
                        "credit"
                    )
                    if withholding:
                        # adjust bank side
                        net_credit = gl_entry.credit - withholding

                        bank_entry = gl_entry.copy()
                        bank_entry.credit = net_credit
                        bank_entry.debit = 0
                        bank_entry.credit_in_account_currency = net_credit
                        bank_entry.debit_in_account_currency = 0
                        bank_entry.net_amount = -net_credit
                        processed_entries.append(bank_entry)
                        continue

            processed_entries.append(gl_entry)

        gl_entries = processed_entries


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



def group_by_field(group_by):
    if group_by == "Categorize by Party":
        return "party"
    elif group_by in ["Categorize by Voucher (Consolidated)", "Categorize by Account"]:
        return "account"
    else:
        return "voucher_no"

def get_account_type_map(company):
    account_type_map = frappe._dict(
        frappe.get_all("Account", fields=["name", "account_type"], filters={"company": company}, as_list=1)
    )

    return account_type_map

def custom_get_accountwise_gle(filters, accounting_dimensions, gl_entries, gle_map, totals):
    entries = []
    consolidated_gle = OrderedDict()
    group_by = group_by_field(filters.get("categorize_by"))
    group_by_voucher_consolidated = filters.get("categorize_by") == "Categorize by Voucher (Consolidated)"

    if filters.get("show_net_values_in_party_account"):
        account_type_map = get_account_type_map(filters.get("company"))

    immutable_ledger = frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger")

    def update_value_in_dict(data, key, gle):
        data[key].debit += gle.debit
        data[key].credit += gle.credit

        data[key].debit_in_account_currency += gle.debit_in_account_currency
        data[key].credit_in_account_currency += gle.credit_in_account_currency

        if filters.get("add_values_in_transaction_currency") and key not in ["opening", "closing", "total"]:
            data[key].debit_in_transaction_currency += gle.debit_in_transaction_currency
            data[key].credit_in_transaction_currency += gle.credit_in_transaction_currency

        if filters.get("show_net_values_in_party_account") and account_type_map.get(data[key].account) in (
            "Receivable",
            "Payable",
        ):
            net_value = data[key].debit - data[key].credit
            net_value_in_account_currency = (
                data[key].debit_in_account_currency - data[key].credit_in_account_currency
            )

            if net_value < 0:
                dr_or_cr = "credit"
                rev_dr_or_cr = "debit"
            else:
                dr_or_cr = "debit"
                rev_dr_or_cr = "credit"

            data[key][dr_or_cr] = abs(net_value)
            data[key][dr_or_cr + "_in_account_currency"] = abs(net_value_in_account_currency)
            data[key][rev_dr_or_cr] = 0
            data[key][rev_dr_or_cr + "_in_account_currency"] = 0

        if data[key].against_voucher and gle.against_voucher:
            data[key].against_voucher += ", " + gle.against_voucher

    from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
    show_opening_entries = filters.get("show_opening_entries")
 
    apply_tax_withholding = False

    # Get all unique voucher_nos from the GL entries
    if filters.get("categorize_by") == "Categorize by Voucher (Consolidated)":
        voucher_nos = list({gle.get("voucher_no") for gle in gl_entries if gle.get("voucher_type") == "Payment Entry"})

        for voucher_no in voucher_nos:
            # Safely fetch Payment Entry
            if frappe.db.exists("Payment Entry", voucher_no):
                apply_flag = frappe.db.get_value("Payment Entry", voucher_no, "apply_tax_withholding_amount")
                if apply_flag:
                    apply_tax_withholding = True
                    break

        if apply_tax_withholding:
            for gle in gl_entries:
                update_value_in_dict(totals, "total", gle)
                update_value_in_dict(totals, "closing", gle)

            entries = gl_entries[:]  # copy all as-is
            return totals, entries


    # --- otherwise continue your normal logic ---
    for gle in gl_entries:
        group_by_value = gle.get(group_by)
        gle.voucher_type = gle.voucher_type

        if gle.posting_date < from_date or (cstr(gle.is_opening) == "Yes" and not show_opening_entries):
            if not group_by_voucher_consolidated:
                update_value_in_dict(gle_map[group_by_value].totals, "opening", gle)
                update_value_in_dict(gle_map[group_by_value].totals, "closing", gle)

            update_value_in_dict(totals, "opening", gle)
            update_value_in_dict(totals, "closing", gle)

        elif gle.posting_date <= to_date or (cstr(gle.is_opening) == "Yes" and show_opening_entries):
            if not group_by_voucher_consolidated:
                update_value_in_dict(gle_map[group_by_value].totals, "total", gle)
                update_value_in_dict(gle_map[group_by_value].totals, "closing", gle)
                update_value_in_dict(totals, "total", gle)
                update_value_in_dict(totals, "closing", gle)

                gle_map[group_by_value].entries.append(gle)

            elif group_by_voucher_consolidated:
                keylist = [
                    gle.get("posting_date"),
                    gle.get("voucher_type"),
                    gle.get("voucher_no"),
                    gle.get("account"),
                    gle.get("party_type"),
                    gle.get("party"),
                ]

                if immutable_ledger:
                    keylist.append(gle.get("creation"))

                if filters.get("include_dimensions"):
                    for dim in accounting_dimensions:
                        keylist.append(gle.get(dim))
                    keylist.append(gle.get("cost_center"))
                    keylist.append(gle.get("project"))

                key = tuple(keylist)
                if key not in consolidated_gle:
                    consolidated_gle.setdefault(key, gle)
                else:
                    update_value_in_dict(consolidated_gle, key, gle)

    for value in consolidated_gle.values():
        update_value_in_dict(totals, "total", value)
        update_value_in_dict(totals, "closing", value)
        entries.append(value)

    return totals, entries


gl_report.get_gl_entries = custom_get_gl_entries
gl_report.get_accountwise_gle = custom_get_accountwise_gle