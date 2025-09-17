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
            first_account = gl_entries[0]["account"]  # Store first account (Health Services)

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
                    "account": first_account,  # <-- Use first GL entry account (Health Services)
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
                    reversal_entry["party_type"] = "Supplier"  # or "Customer" depending on the party
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


