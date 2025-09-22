import frappe
from frappe.utils import getdate

# Create customer
# api/method/smartclaims.api.create.create_company 
@frappe.whitelist()
def create_company(**kwargs):
    try:
        company_id = kwargs.get("company_id")
        if not company_id:
            frappe.local.response["http_status_code"] = 400  
            return {"status": "failed", "error": "Customer ID is required"}

        # Check for duplicates
        existing = frappe.get_all("Customer", filters={"customer_name": company_id})
        if existing:
            frappe.local.response["http_status_code"] = 409  
            return {"status": "failed", "error": f"Customer '{company_id}' already exists"}

        # Build customer doc with mandatory field
        customer_doc = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": company_id  
        })

        # Map other fields from JSON
        meta = frappe.get_meta("Customer")
        for key, value in kwargs.items():
            if key == "company_id":
                continue 
            if meta.has_field(key):
                customer_doc.set(key, value)

        # Insert doc
        customer_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201  
        return {"status": "success", "name": customer_doc.name}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403  
        return {"status": "failed", "error": str(e)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_company error")
        frappe.local.response["http_status_code"] = 500 
        return {"status": "failed", "error": str(e)}

# Create Supplier 
# api/method/smartclaims.api.create.create_provider
@frappe.whitelist()
def create_provider(**kwargs):
    try:
        # Use custom_provider_id as supplier_name
        supplier_name = kwargs.get("custom_provider_id") 
        if not supplier_name:
            frappe.local.response["http_status_code"] = 400  # Bad Request
            return {"status": "failed", "error": "Provider ID is required"}

        # Check for duplicates
        existing = frappe.get_all("Supplier", filters={"supplier_name": supplier_name})
        if existing:
            frappe.local.response["http_status_code"] = 409  # Conflict
            return {"status": "failed", "error": f"Provider '{supplier_name}' already exists"}

        # Build supplier doc with mandatory fields
        supplier_doc = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": supplier_name
        })

        # Map other fields from JSON
        meta = frappe.get_meta("Supplier")
        for key, value in kwargs.items():
            if key in ("supplier_name", "custom_provider_id"):
                continue  
            if meta.has_field(key):
                supplier_doc.set(key, value)

        # Insert doc
        supplier_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201  # Created
        return {"status": "success", "name": supplier_doc.name}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403  # Forbidden
        return {"status": "failed", "error": str(e)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_supplier error")
        frappe.local.response["http_status_code"] = 500  # Internal Server Error
        return {"status": "failed", "error": str(e)}
    
# Create Purchase Invoice
# api/method/smartclaims.api.create.create_purchase_invoice
@frappe.whitelist()
def create_purchase_invoice(**kwargs):
    try:
        # Mandatory fields
        invoice_type = kwargs.get("custom_invoice_type")
        if invoice_type == "Claims":
            supplier = kwargs.get("provider_id")
            custom_refund_id = None
            posting_date = kwargs.get("invoice_date")
            if not supplier or not posting_date:
                frappe.local.response["http_status_code"] = 400
                return {"status": "failed", "error": "Supplier and Invoice Date are required"}
        else:
            supplier = kwargs.get("refund_id")  
            custom_refund_id = kwargs.get("refund_id")
            posting_date = kwargs.get("request_date")
            if not custom_refund_id or not posting_date:
                frappe.local.response["http_status_code"] = 400
                return {"status": "failed", "error": "Refund ID and Request Date are required"}

        # Create Purchase Invoice doc
        pi_doc = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "supplier": supplier,
            "custom_refund_id":custom_refund_id,
            "posting_date": posting_date,
            "bill_no": kwargs.get("supplier_invoice_no", ""),
            "items": []
        })

        # Add items with calculated rate if provided
        total_qty = float(kwargs.get("total_qty", 0))
        total_amount = float(kwargs.get("total_amount", 0))
        default_rate = total_amount / total_qty if total_qty else 0
        items = kwargs.get("items", [])
        if items:
            for item in items:
                if "item_code" in item:
                    pi_doc.append("items", {
                        "item_code": item["item_code"],
                        "qty": item.get("qty", total_qty),
                        "rate": item.get("rate", default_rate)
                    })
        else:
            # Single item if none provided
            pi_doc.append("items", {
                "item_code": kwargs.get("default_item_code", "Item-Default"),
                "qty": total_qty,
                "rate": default_rate
            })

        # Map all other fields dynamically
        meta = frappe.get_meta("Purchase Invoice")
        skip_fields = ("provider_id", "invoice_date", "supplier_invoice_no", "items", "total_amount", "default_item_code")
        for key, value in kwargs.items():
            if key in skip_fields:
                continue
            if meta.has_field(key):
                pi_doc.set(key, value)

        # Insert doc
        pi_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"status": "success", "name": pi_doc.name}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403
        return {"status": "failed", "error": str(e)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_purchase_invoice error")
        frappe.local.response["http_status_code"] = 500
        return {"status": "failed", "error": str(e)}

# Create Sales Invoice
# api/method/smartclaims.api.create.create_sales_invoice
@frappe.whitelist()
def create_sales_invoice(**kwargs):
    try:
        # Mandatory fields
        invoice_number = kwargs.get("invoice_number")
        company = kwargs.get("company_id")
        customer = kwargs.get("company_id")
        posting_date = kwargs.get("invoice_date")

        if not invoice_number or not company or not posting_date:
            frappe.local.response["http_status_code"] = 400
            return {"status": "failed", "error": "Invoice Number, Company ID and Invoice Date are required"}
    

        # Create Sales Invoice doc
        si_doc = frappe.get_doc({
            "doctype": "Sales Invoice",
            "custom_company_id": company,
            "posting_date": posting_date,
            "customer":customer,
            "custom_invoice_number": invoice_number,
            "custom_cover_period_start": kwargs.get("cover_period_start"),
            "custom_cover_period_end": kwargs.get("cover_period_end"),
            "custom_next_invoice_date": kwargs.get("next_invoice_date"),
            "custom_insurance_type": kwargs.get("insurance_type"),
            "custom_card_option": kwargs.get("card_option"),
            "items": []
        })

        # Add items from JSON
        items = kwargs.get("items", [])
        if items:
            for item in items:
                qty = item.get("members", 1)
                amount = item.get("premium_amount", 0)
                rate = amount / qty if qty else 0

                si_doc.append("items", {
                    "item_code": item.get("plan"),
                    "qty": qty,
                    "rate": rate,
                    "amount": amount
                })

        # Set total manually if needed
        si_doc.set("custom_current_invoice_amount", kwargs.get("current_invoice_amount", 0))

        # Insert doc
        si_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"status": "success", "name": si_doc.name}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403
        return {"status": "failed", "error": str(e)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_sales_invoice error")
        frappe.local.response["http_status_code"] = 500
        return {"status": "failed", "error": str(e)}

# Create Credit Note
# api/method/smartclaims.api.create.create_credit_note
@frappe.whitelist()
def create_credit_note(**kwargs):
    try:
        invoice_number = kwargs.get("invoice_number")
        insurance_type = kwargs.get("insurance_type")

        # 🔹 Mandatory fields
        if not invoice_number or not insurance_type:
            frappe.local.response["http_status_code"] = 400
            return {"status": "failed", "error": "Invoice Number and Insurance Type are required"}

        # 🔹 Check for duplicates
        # sales_invoice = frappe.get_all(
        #     "Sales Invoice",
        #     filters={"name": invoice_number},  # or use custom_invoice_number if that's your field
        #     pluck="name"
        # )
        sales_invoice = frappe.get_all(
            "Sales Invoice",
            filters={"custom_invoice_number": invoice_number}, 
            pluck="custom_invoice_number"
        )
        if not sales_invoice:
            frappe.local.response["http_status_code"] = 404
            return {"status": "failed", "error": f"Invoice Number '{invoice_number}' not found"}

        # 🔹 Build Credit Note doc
        credit_note_doc = frappe.get_doc({"doctype": "Credit Note"})
        meta = frappe.get_meta("Credit Note")

        # Map only valid fields from kwargs
        for key, value in kwargs.items():
            if meta.has_field(key):
                credit_note_doc.set(key, value)

        # 🔹 Insert doc
        credit_note_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"status": "success", "name": credit_note_doc.name}

    except frappe.PermissionError as e:
        frappe.local.response["http_status_code"] = 403
        return {"status": "failed", "error": str(e)}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_credit_note error")
        frappe.local.response["http_status_code"] = 500
        return {"status": "failed", "error": str(e)}



@frappe.whitelist()
def create_rejected_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Rejection Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "provider_id": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "invoice_number": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Rejection Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"
        je.custom_journal_type = "Claims" 

        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("invoice_number"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('provider_id')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("provider_id"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("invoice_number"),
                "debit_in_account_currency": entry.get("debit", 0),
                "credit_in_account_currency": 0
            })

            # --- Credit row (Expense account from Purchase Invoice) ---
            if entry.get("invoice_number"):
                try:
                    pi_doc = frappe.get_doc("Purchase Invoice", entry.get("invoice_number"))
                    expense_account = None
                    if pi_doc.get("items"):
                        expense_account = pi_doc.items[0].get("expense_account")
                    
                    if not expense_account:
                        frappe.local.response["http_status_code"] = 400
                        return {"success": False, "message": f"Purchase Invoice {entry.get('invoice_number')} has no expense account set"}  
                    
                    je.append("accounts", {
                        "account": expense_account or "",
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": entry.get("credit", 0)
                    })

                except frappe.DoesNotExistError:
                    frappe.local.response["http_status_code"] = 404
                    return {"success": False, "message": f"Purchase Invoice {entry.get('invoice_number')} not found"}

        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Rejection Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}
    
@frappe.whitelist()
def create_withholding_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Withholding Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "provider_id": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "invoice_number": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Withholding Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"
        je.custom_journal_type = "Claims" 

        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("invoice_number"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('provider_id')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("provider_id"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("invoice_number"),
                "debit_in_account_currency": entry.get("debit", 0),
                "credit_in_account_currency": 0
            })

            # Withholding Account
            je.append("accounts", {
                        "account": "04-04-003 - Withholding Taxes - NMICL" or "",
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": entry.get("credit", 0)
                    })
                        
        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Withholding Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}
    
    
    
@frappe.whitelist()
def create_adjustment_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Adjustment Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "provider_id": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "invoice_number": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Adjustment Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"
        je.custom_journal_type = "Claims" 

        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("invoice_number"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('provider_id')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("provider_id"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("invoice_number"),
                "credit_in_account_currency": entry.get("credit", 0),
                "debit_in_account_currency": 0
            })

           # --- Credit row (Expense account from Purchase Invoice) ---
            if entry.get("invoice_number"):
                try:
                    pi_doc = frappe.get_doc("Purchase Invoice", entry.get("invoice_number"))
                    expense_account = None
                    if pi_doc.get("items"):
                        expense_account = pi_doc.items[0].get("expense_account")
                    
                    if not expense_account:
                        frappe.local.response["http_status_code"] = 400
                        return {"success": False, "message": f"Purchase Invoice {entry.get('invoice_number')} has no expense account set"}  
                    
                    je.append("accounts", {
                        "account": expense_account or "",
                        "credit_in_account_currency": 0,
                        "debit_in_account_currency": entry.get("debit", 0)
                    })

                except frappe.DoesNotExistError:
                    frappe.local.response["http_status_code"] = 404
                    return {"success": False, "message": f"Purchase Invoice {entry.get('invoice_number')} not found"}
                
                
        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Adjustment Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def create_refund_rejected_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Rejection Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "member_number": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "refund_id": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Rejection Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"   
        je.custom_journal_type = "Refund" 


        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("refund_id"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('member_number')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("member_number"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("refund_id"),
                "debit_in_account_currency": entry.get("debit", 0),
                "credit_in_account_currency": 0
            })

            # --- Credit row (Expense account from Purchase Invoice) ---
            if entry.get("refund_id"):
                try:
                    pi_doc = frappe.get_doc("Purchase Invoice", entry.get("refund_id"))
                    expense_account = None
                    if pi_doc.get("items"):
                        expense_account = pi_doc.items[0].get("expense_account")
                    
                    if not expense_account:
                        frappe.local.response["http_status_code"] = 400
                        return {"success": False, "message": f"Purchase Invoice {entry.get('refund_id')} has no expense account set"}  
                    
                    je.append("accounts", {
                        "account": expense_account or "",
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": entry.get("credit", 0)
                    })

                except frappe.DoesNotExistError:
                    frappe.local.response["http_status_code"] = 404
                    return {"success": False, "message": f"Purchase Invoice {entry.get('refund_id')} not found"}

        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Rejection Refund Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}
    

@frappe.whitelist()
def create_refund_withholding_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Withholding Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "member_number": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "refund_id": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Withholding Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"
        je.custom_journal_type = "Refund" 

        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("refund_id"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('member_number')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("member_number"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("refund_id"),
                "debit_in_account_currency": entry.get("debit", 0),
                "credit_in_account_currency": 0
            })

            # Withholding Account
            je.append("accounts", {
                        "account": "04-04-003 - Withholding Taxes - NMICL" or "",
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": entry.get("credit", 0)
                    })
                        
        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Withholding Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}
    
    
@frappe.whitelist()
def create_refund_adjustment_journal_entry(**kwargs):
    """
    Dummy JSON Input:
    {
        "type": "Adjustment Journal",
        "approval_date": "2025-09-17",
        "journal_number": "JN-00045",
        "entries": [
            {
                "provider_id": "01-02-00269 SUNYANI MUNICIPAL HOSPITAL",
                "invoice_number": "ACC-PINV-2025-00014",
                "debit": 900,
                "credit": 900
            }
        ]
    }
    """
    try:
        # Parse entries JSON string if passed as string
        entries = kwargs.get("accounts")
        if isinstance(entries, str):
            entries = frappe.parse_json(entries)

        if not entries:
            frappe.local.response["http_status_code"] = 400
            return {"success": False, "message": "Invalid JSON : No entries provided"}

        # Create parent Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.posting_date = getdate(kwargs.get("approval_date"))
        je.custom_type =  "Adjustment Journal"
        je.custom_journal_number = kwargs.get("journal_number")
        je.voucher_type = "Journal Entry"
        je.custom_journal_type = "Refund" 

        # Add child rows
        for entry in entries:
            pi_account = frappe.get_doc("Purchase Invoice", entry.get("refund_id"))
            if not pi_account.credit_to:
                frappe.local.response["http_status_code"] = 400
                return {"success": False, "message": f"Purchase Invoice {entry.get('member_number')} has no account set"}    
                

            je.append("accounts", {
                "account": pi_account.credit_to,
                "party_type": "Supplier",
                "party": entry.get("member_number"),
                "reference_type": "Purchase Invoice",
                "reference_name": entry.get("refund_id"),
                "credit_in_account_currency": entry.get("credit", 0),
                "debit_in_account_currency": 0
            })

           # --- Credit row (Expense account from Purchase Invoice) ---
            if entry.get("refund_id"):
                try:
                    pi_doc = frappe.get_doc("Purchase Invoice", entry.get("refund_id"))
                    expense_account = None
                    if pi_doc.get("items"):
                        expense_account = pi_doc.items[0].get("expense_account")
                    
                    if not expense_account:
                        frappe.local.response["http_status_code"] = 400
                        return {"success": False, "message": f"Purchase Invoice {entry.get('refund_id')} has no expense account set"}  
                    
                    je.append("accounts", {
                        "account": expense_account or "",
                        "credit_in_account_currency": 0,
                        "debit_in_account_currency": entry.get("debit", 0)
                    })

                except frappe.DoesNotExistError:
                    frappe.local.response["http_status_code"] = 404
                    return {"success": False, "message": f"Purchase Invoice {entry.get('refund_id')} not found"}
                
                
        je.insert(ignore_permissions=True)
        je.submit()
        frappe.db.commit()

        frappe.local.response["http_status_code"] = 201
        return {"success": True, "message": "Journal Entry created Successfully", "Journal Entry":je.as_dict()}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Adjustment Journal Entry API Error")
        frappe.local.response["http_status_code"] = 500
        return {"success": False, "message": str(e)}


