import sys
sys.stdout.reconfigure(encoding='utf-8')

endpoints = """
# ===== BC007 — SỔ NHẬT KÝ CHUNG =====
@app.route("/api/journal")
@with_db_lock
def get_journal():
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt = datetime.strptime(t_date, "%d/%m/%Y").date()

        org_where = ""
        org_params = []
        if org_ids:
            org_where = f" AND ORGANIZATION_ID IN ({','.join(['?']*len(org_ids))})"
            org_params = list(org_ids)

        cur = get_connection().cursor()
        
        sql = f\"\"\"
            SELECT 
                TRAN_DATE, 
                TRAN_NO, 
                DESCRIPTION, 
                ACCOUNT_ID, 
                ACCOUNT_ID_CONTRA, 
                DEBIT_CREDIT, 
                AMOUNT
            FROM dbo.LEDGER_VIEW
            WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            ORDER BY TRAN_DATE, TRAN_NO
        \"\"\"
        params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
        cur.execute(sql, params)
        
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
            "data": rows
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            logger.error(f"Error in BC007 get_journal: {msg}")
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500

# ===== BC008 — SỔ CHI TIẾT TÀI KHOẢN =====
@app.route("/api/account_details")
@with_db_lock
def get_account_details():
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        account_id = request.args.get("account_id", "")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

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
        
        # 1. Tính số dư đầu kỳ (Đầu năm + Lũy kế đến ngày from_dt)
        open_bal_deb = 0
        open_bal_crd = 0
        
        # Số dư đầu năm
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
            
        # Cộng thêm phát sinh từ đầu năm đến trước from_dt
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
                
        # Chuẩn hóa số dư (chỉ để dư 1 bên)
        net_open = open_bal_deb - open_bal_crd
        if net_open >= 0:
            open_bal_deb = net_open
            open_bal_crd = 0
        else:
            open_bal_deb = 0
            open_bal_crd = abs(net_open)

        # 2. Lấy chi tiết phát sinh trong kỳ
        sql_trans = f\"\"\"
            SELECT 
                TRAN_DATE, 
                TRAN_NO, 
                DESCRIPTION, 
                ACCOUNT_ID, 
                ACCOUNT_ID_CONTRA, 
                DEBIT_CREDIT, 
                AMOUNT
            FROM dbo.LEDGER_VIEW
            WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            ORDER BY TRAN_DATE, TRAN_NO
        \"\"\"
        cur.execute(sql_trans, [account_id, from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params)
        
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
            "opening_balance": {
                "deb": open_bal_deb,
                "crd": open_bal_crd
            },
            "data": rows
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            logger.error(f"Error in BC008 get_account_details: {msg}")
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500

"""

lines = open('server.py', 'r', encoding='utf-8').readlines()
for i, line in enumerate(lines):
    if "# ===== DEBUG ENDPOINT (XÓA SAU KHI DEBUG XONG) =====" in line:
        insert_idx = i
        break

lines.insert(insert_idx, endpoints)

with open('server.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Endpoints inserted successfully")
