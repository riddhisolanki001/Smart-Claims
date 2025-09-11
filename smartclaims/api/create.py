import frappe

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
