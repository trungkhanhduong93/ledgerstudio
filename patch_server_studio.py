import os
import re

file_path = r"D:\IACC HCM\iPOS ACC\ACC PMKT\LedgerStudio\server.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

new_methods = """
# ===== API XUẤT EXCEL CHUYÊN DỤNG (XỬ LÝ DỮ LIỆU LỚN) =====
from io import BytesIO
from flask import send_file
import xlsxwriter

@app.route("/api/export_excel_backend")
@with_db_lock
def export_excel_backend():
    try:
        report_type = request.args.get("report_type")
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        account_id = request.args.get("account_id", "")
        
        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt = datetime.strptime(t_date, "%d/%m/%Y").date()
        
        org_where = ""
        org_params = []
        if org_ids:
            org_where = f" AND ORGANIZATION_ID IN ({','.join(['?']*len(org_ids))})"
            org_params = list(org_ids)

        cur = get_connection().cursor()
        
        if report_type == "BC007":
            title = "SỔ NHẬT KÝ CHUNG"
            sql = f\"\"\"
                SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                FROM dbo.LEDGER_VIEW
                WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                ORDER BY TRAN_DATE, TRAN_NO
            \"\"\"
            params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
            headers = ["Ngày HT", "Số CT", "Diễn giải", "TK Nợ", "TK Có", "Phát sinh Nợ", "Phát sinh Có"]
        elif report_type == "BC008":
            title = "SỔ CHI TIẾT TÀI KHOẢN"
            sql = f\"\"\"
                SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                FROM dbo.LEDGER_VIEW
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                ORDER BY TRAN_DATE, TRAN_NO
            \"\"\"
            params = [account_id, from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
            headers = ["Ngày HT", "Số CT", "Diễn giải", "TK Đối ứng", "Phát sinh Nợ", "Phát sinh Có", "Dư Nợ", "Dư Có"]
            
            open_bal_deb = 0
            open_bal_crd = 0
            first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")
            sql_open = f\"\"\"
                SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                       SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                FROM dbo.BALANCE_VIEW
                WHERE ACCOUNT_ID LIKE ? + '%' AND BAL_DATE = ? {org_where}
            \"\"\"
            cur.execute(sql_open, [account_id, first_day_of_year] + org_params)
            r_open = cur.fetchone()
            if r_open:
                open_bal_deb += float(r_open[0] or 0)
                open_bal_crd += float(r_open[1] or 0)
                
            if from_dt > date(from_dt.year, 1, 1):
                sql_lk = f\"\"\"
                    SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                           SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                    FROM dbo.LEDGER_VIEW
                    WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}
                \"\"\"
                cur.execute(sql_lk, [account_id, first_day_of_year, from_dt.strftime("%Y%m%d")] + org_params)
                r_lk = cur.fetchone()
                if r_lk:
                    open_bal_deb += float(r_lk[0] or 0)
                    open_bal_crd += float(r_lk[1] or 0)
        else:
            return jsonify({"status": "error", "message": "Report type không hỗ trợ xuất Excel trực tiếp từ backend."}), 400

        cur.execute(sql, params)
        rows = cur.fetchall()
        total_rows = len(rows)

        SPLIT_LIMIT = 500000
        sheets_data = {}
        
        if total_rows > SPLIT_LIMIT:
            for r in rows:
                dt = r[0]
                year_key = f"Năm {dt.year}"
                if year_key not in sheets_data: sheets_data[year_key] = []
                sheets_data[year_key].append(r)
                
            new_sheets = {}
            for k, s_rows in sheets_data.items():
                if len(s_rows) > SPLIT_LIMIT:
                    for r in s_rows:
                        dt = r[0]
                        quarter = (dt.month - 1) // 3 + 1
                        q_key = f"{k} - Q{quarter}"
                        if q_key not in new_sheets: new_sheets[q_key] = []
                        new_sheets[q_key].append(r)
                else:
                    new_sheets[k] = s_rows
            sheets_data = new_sheets
            
            final_sheets = {}
            for k, s_rows in sheets_data.items():
                if len(s_rows) > SPLIT_LIMIT:
                    for r in s_rows:
                        dt = r[0]
                        m_key = f"{k} - Th{dt.month}"
                        if m_key not in final_sheets: final_sheets[m_key] = []
                        final_sheets[m_key].append(r)
                else:
                    final_sheets[k] = s_rows
            sheets_data = final_sheets
        else:
            sheets_data["Data"] = rows
            
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        header_format = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#D3D3D3'})
        num_format = workbook.add_format({'num_format': '#,##0'})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        
        for sheet_name, s_rows in sheets_data.items():
            ws = workbook.add_worksheet(sheet_name[:31])
            ws.write(0, 0, title, workbook.add_format({'bold': True, 'font_size': 14}))
            ws.write(1, 0, f"Từ {f_date} đến {t_date}")
            if report_type == "BC008":
                ws.write(2, 0, f"Tài khoản: {account_id}")
            
            start_row = 4
            for col_num, col_name in enumerate(headers):
                ws.write(start_row, col_num, col_name, header_format)
                
            current_row = start_row + 1
            
            if report_type == "BC008":
                if sheet_name == list(sheets_data.keys())[0]:
                    ws.write(current_row, 2, "Số dư đầu kỳ")
                    ws.write(current_row, 6, open_bal_deb if open_bal_deb > open_bal_crd else 0, num_format)
                    ws.write(current_row, 7, open_bal_crd if open_bal_crd > open_bal_deb else 0, num_format)
                    current_row += 1
                running_deb = open_bal_deb
                running_crd = open_bal_crd
            
            for r in s_rows:
                ws.write(current_row, 0, r[0], date_format)
                ws.write(current_row, 1, r[1] or "")
                ws.write(current_row, 2, r[2] or "")
                
                if report_type == "BC007":
                    ws.write(current_row, 3, r[3] or "")
                    ws.write(current_row, 4, r[4] or "")
                    amt = float(r[6] or 0)
                    is_deb = (r[5] == 'DEB')
                    ws.write(current_row, 5, amt if is_deb else 0, num_format)
                    ws.write(current_row, 6, amt if not is_deb else 0, num_format)
                else:
                    ws.write(current_row, 3, r[3] or "")
                    amt = float(r[5] or 0)
                    is_deb = (r[4] == 'DEB')
                    ws.write(current_row, 4, amt if is_deb else 0, num_format)
                    ws.write(current_row, 5, amt if not is_deb else 0, num_format)
                    
                    if is_deb: running_deb += amt
                    else: running_crd += amt
                    
                    bal_d = running_deb - running_crd
                    if bal_d > 0:
                        ws.write(current_row, 6, bal_d, num_format)
                        ws.write(current_row, 7, 0, num_format)
                    else:
                        ws.write(current_row, 6, 0, num_format)
                        ws.write(current_row, 7, -bal_d, num_format)
                current_row += 1
                
            ws.freeze_panes(start_row + 1, 0)
            
        workbook.close()
        output.seek(0)
        
        return send_file(output, as_attachment=True, download_name=f"{report_type}_Export.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        msg = str(e)
        logger.error(f"Error in export_excel_backend: {msg}")
        return jsonify({"status": "error", "message": msg}), 500

@app.route("/api/journal")
@with_db_lock
def get_journal():
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10000))

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt = datetime.strptime(t_date, "%d/%m/%Y").date()

        org_where = ""
        org_params = []
        if org_ids:
            org_where = f" AND ORGANIZATION_ID IN ({','.join(['?']*len(org_ids))})"
            org_params = list(org_ids)

        cur = get_connection().cursor()
        
        count_sql = f\"\"\"
            SELECT COUNT(*),
                   SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM dbo.LEDGER_VIEW
            WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
        \"\"\"
        base_params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
        cur.execute(count_sql, base_params)
        c_row = cur.fetchone()
        total_rows = c_row[0] or 0
        total_deb = float(c_row[1] or 0)
        total_crd = float(c_row[2] or 0)
        
        offset = (page - 1) * page_size
        paged_sql = f\"\"\"
            WITH CTE AS (
                SELECT 
                    TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                    ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW
                WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT * FROM CTE WHERE RowNum > ? AND RowNum <= ?
        \"\"\"
        cur.execute(paged_sql, base_params + [offset, offset + page_size])
        
        rows = []
        for r in cur.fetchall():
            rows.append({
                "tran_date": r[0].strftime("%d/%m/%Y") if r[0] else "",
                "tran_no": r[1] or "",
                "description": r[2] or "",
                "account_id": r[3] or "",
                "contra_account_id": r[4] or "",
                "debit_credit": r[5] or "",
                "amount": float(r[6] or 0)
            })

        return jsonify({
            "status": "ok",
            "data": rows,
            "period_sums": {"deb": total_deb, "crd": total_crd},
            "pagination": {
                "total_rows": total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page
            }
        })
    except Exception as e:
        msg = str(e)
        logger.error(f"Error in BC007 get_journal: {msg}")
        return jsonify({"status": "error", "message": msg}), 500

@app.route("/api/account_details")
@with_db_lock
def get_account_details():
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        account_id = request.args.get("account_id", "")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10000))

        if not account_id:
            return jsonify({"status": "error", "message": "Vui lòng chọn tài khoản!"}), 400

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt = datetime.strptime(t_date, "%d/%m/%Y").date()
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        org_where = ""
        org_params = []
        if org_ids:
            org_where = f" AND ORGANIZATION_ID IN ({','.join(['?']*len(org_ids))})"
            org_params = list(org_ids)

        cur = get_connection().cursor()
        
        open_bal_deb = 0
        open_bal_crd = 0
        sql_open = f\"\"\"
            SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM dbo.BALANCE_VIEW
            WHERE ACCOUNT_ID LIKE ? + '%' AND BAL_DATE = ? {org_where}
        \"\"\"
        cur.execute(sql_open, [account_id, first_day_of_year] + org_params)
        r_open = cur.fetchone()
        if r_open:
            open_bal_deb += float(r_open[0] or 0)
            open_bal_crd += float(r_open[1] or 0)
            
        if from_dt > date(from_dt.year, 1, 1):
            sql_lk = f\"\"\"
                SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                       SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                FROM dbo.LEDGER_VIEW
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}
            \"\"\"
            cur.execute(sql_lk, [account_id, first_day_of_year, from_dt.strftime("%Y%m%d")] + org_params)
            r_lk = cur.fetchone()
            if r_lk:
                open_bal_deb += float(r_lk[0] or 0)
                open_bal_crd += float(r_lk[1] or 0)

        base_params = [account_id, from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
        
        offset = (page - 1) * page_size
        
        stats_sql = f\"\"\"
            WITH CTE AS (
                SELECT DEBIT_CREDIT, AMOUNT,
                       ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT 
                COUNT(*),
                SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN RowNum <= ? AND DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN RowNum <= ? AND DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM CTE
        \"\"\"
        cur.execute(stats_sql, base_params + [offset, offset])
        s_row = cur.fetchone()
        
        total_rows = s_row[0] or 0
        total_deb = float(s_row[1] or 0)
        total_crd = float(s_row[2] or 0)
        offset_deb = float(s_row[3] or 0)
        offset_crd = float(s_row[4] or 0)

        paged_sql = f\"\"\"
            WITH CTE AS (
                SELECT 
                    TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                    ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT * FROM CTE WHERE RowNum > ? AND RowNum <= ?
        \"\"\"
        cur.execute(paged_sql, base_params + [offset, offset + page_size])
        
        rows = []
        for r in cur.fetchall():
            rows.append({
                "tran_date": r[0].strftime("%d/%m/%Y") if r[0] else "",
                "tran_no": r[1] or "",
                "description": r[2] or "",
                "contra_account_id": r[3] or "",
                "debit_credit": r[4] or "",
                "amount": float(r[5] or 0)
            })

        return jsonify({
            "status": "ok",
            "opening_balance": {"deb": open_bal_deb, "crd": open_bal_crd},
            "offset_balance": {"deb": offset_deb, "crd": offset_crd},
            "period_sums": {"deb": total_deb, "crd": total_crd},
            "data": rows,
            "pagination": {
                "total_rows": total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page
            }
        })
    except Exception as e:
        msg = str(e)
        logger.error(f"Error in BC008 get_account_details: {msg}")
        return jsonify({"status": "error", "message": msg}), 500
"""

start_idx = content.find("@app.route(\"/api/journal\")")
end_idx = content.find("# ===== END API =====")
if end_idx == -1:
    end_idx = content.find('if __name__ == "__main__":')

if start_idx != -1 and end_idx != -1:
    patched = content[:start_idx] + new_methods + "\n" + content[end_idx:]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print("Patched server.py successfully!")
else:
    print("Could not find insertion points!")
