import pyodbc
import logging
logger = logging.getLogger(__name__)
import threading
global_db_lock = threading.RLock()
from functools import wraps

def with_db_lock(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        with global_db_lock:
            # Thử lần 1
            resp = f(*args, **kwargs)
            
            status_code = 200
            msg = ""
            
            if isinstance(resp, tuple):
                if len(resp) > 1:
                    status_code = resp[1]
                if hasattr(resp[0], 'get_data'):
                    try: msg = resp[0].get_data(as_text=True).lower()
                    except: pass
                else:
                    msg = str(resp[0]).lower()
            elif hasattr(resp, 'status_code'):
                status_code = resp.status_code
                try: msg = resp.get_data(as_text=True).lower()
                except: pass
                
            if status_code == 500:
                is_conn_error = any(kw in msg for kw in (
                    "connection", "cursor", "closed", "hy000", "08s01", "communication link failure"
                ))
                if is_conn_error:
                    # Connection lỗi → Invalidate pool để xóa kết nối hỏng
                    try:
                        invalidate_pool()
                    except Exception:
                        pass
                    # Thử lần 2 với kết nối mới sạch sẽ
                    resp = f(*args, **kwargs)
                    
            return resp
    return decorated_function

from flask import Flask, jsonify, request, session, send_from_directory
from flask_cors import CORS
from datetime import datetime, date
import os
import sys
import threading

import hashlib
import subprocess
import platform
import xlsx_report as XR

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def _read_app_version():
    """Đọc version.txt (build_exe.py tự tăng mỗi lần build, và nhúng kèm vào EXE qua --add-data).
    Frontend lấy qua /api/version để hiển thị -> KHÔNG hardcode version ở index.html nữa."""
    try:
        with open(resource_path('version.txt'), 'r', encoding='utf-8') as f:
            v = f.read().strip()
            return v if v else 'dev'
    except Exception:
        return 'dev'

APP_VERSION = _read_app_version()

app = Flask(__name__)
app.secret_key = 'IACC_SECRET_SUPREME_2026'
CORS(app, supports_credentials=True)

# ===== GZIP COMPRESSION =====
# JSON nén rất tốt (5–10× nhỏ hơn) → giảm bandwidth + parse time cho payload 500k dòng
import gzip
import io as _io
@app.after_request
def _gzip_response(response):
    try:
        accept_enc = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accept_enc.lower():
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.headers.get('Content-Encoding'):
            return response
        # File tĩnh (send_from_directory) đi đường direct_passthrough VÀ cũng bị tính là
        # is_streamed, nhưng nó có Content-Length rõ ràng nên nén an toàn → phải xét TRƯỚC
        # nhánh is_streamed. Trước đây get_data() ném RuntimeError trên direct_passthrough,
        # bị nuốt ở except cuối hàm ⇒ index.html CHƯA TỪNG được nén, mỗi lần mở app tải nguyên.
        if response.direct_passthrough:
            clen = response.content_length
            if clen is None or clen > 8 * 1024 * 1024:   # chặn ngưỡng, không ôm file lớn vào RAM
                return response
            response.direct_passthrough = False
        # ⚠️ Response dạng STREAM (các endpoint xuất CSV dùng stream_with_context):
        # get_data() sẽ NUỐT TRỌN generator vào RAM rồi mới gửi → mất sạch tác dụng streaming
        # mà chính các endpoint đó được viết ra để có. Hệ quả: file lớn thì trình duyệt đứng
        # im không nhận được byte nào cho tới khi chạy xong, RAM phình theo kích thước file.
        elif response.is_streamed:
            return response
        ctype = (response.content_type or '').lower()
        # Chỉ nén text/JSON, không nén binary đã nén sẵn
        if not (ctype.startswith('application/json') or ctype.startswith('text/')
                or ctype.startswith('application/javascript')):
            return response
        data = response.get_data()
        if len(data) < 1024:  # payload nhỏ thì bỏ qua, overhead không đáng
            return response
        buf = _io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=5) as gz:
            gz.write(data)
        compressed = buf.getvalue()
        response.set_data(compressed)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(compressed))
        response.headers['Vary'] = 'Accept-Encoding'
    except Exception:
        pass
    return response

def kill_process_on_port(port):
    """Giải phóng port nếu có process khác đang chiếm đóng (Tránh lỗi cache bản cũ)."""
    try:
        if platform.system() == "Windows":
            # Tìm PID đang dùng port
            cmd = f'netstat -ano | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True).decode()
            for line in output.splitlines():
                if "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    if int(pid) != os.getpid(): # Đừng tự sát
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
    except:
        pass

# Thực hiện dọn dẹp port ngay khi khởi chạy
kill_process_on_port(5050)

def check_odbc_driver(driver_name="ODBC Driver 17 for SQL Server"):
    """Kiểm tra driver ODBC có tồn tại không."""
    return True

def install_odbc_driver():
    """Chạy script cài driver ODBC."""
    try:
        script_path = resource_path("install_driver.ps1")
        if not os.path.exists(script_path):
            return False, "Script cài driver không tìm thấy"

        # Chạy PowerShell script với admin rights
        cmd = f'powershell -ExecutionPolicy Bypass -File "{script_path}"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)

        if result.returncode == 0:
            return True, "Cài đặt driver thành công"
        else:
            return False, f"Lỗi cài đặt: {result.stderr}"
    except Exception as e:
        return False, str(e)

# In-memory metadata cache: key = database name
_meta_cache = {}

# Cache đơn vị "ngoài cây 00" theo database (dùng cho LCTT BC009/BC010)
_external_orgs_cache = {}

# Connection pool: key = hash(db_config) → pyodbc connection
# Tránh mở-đóng connection mỗi request (tiết kiệm 200-500ms / request)
_conn_pool = {}
_pool_lock = threading.Lock()
# Lần cuối mỗi connection được dùng — để khỏi bắn "SELECT 1" dò sống trước mọi request.
import time
_conn_last_used = {}
_POOL_PROBE_AFTER_SEC = 30

def _pool_key(db_config):
    """Tạo key ổn định từ db_config (không chứa password plaintext trong key)."""
    raw = f"{db_config.get('server')}|{db_config.get('database')}|{db_config.get('user')}"
    return hashlib.md5(raw.encode()).hexdigest()

def _make_conn(db_config):
    conn_str = (
        f"DRIVER={{{db_config['driver']}}};"
        f"SERVER={db_config['server']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['user']};"
        f"PWD={db_config['password']};"
        "Trusted_Connection=no;"
    )
    conn = pyodbc.connect(conn_str, timeout=5)
    conn.autocommit = True  # Tránh treo transaction và khóa bảng
    # SET NOCOUNT ON: bỏ thông báo "X rows affected" → giảm round-trip & overhead network
    try:
        conn.execute("SET NOCOUNT ON")
    except Exception:
        pass
    return conn

@app.route("/api/version")
def get_version():
    """Public (không cần đăng nhập) — màn hình login cũng hiển thị version."""
    return jsonify({"status": "ok", "version": APP_VERSION})


@app.route("/")
def index():
    resp = send_from_directory(resource_path("."), "index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/<path:filename>")
def serve_static(filename):
    resp = send_from_directory(resource_path("."), filename)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

def get_connection():
    """Trả connection từ pool, tạo mới nếu chưa có hoặc đã chết."""
    db_config = session.get('db_config')
    if not db_config:
        raise Exception("Vui lòng đăng nhập SQL Server trước!")

    key = _pool_key(db_config)

    with _pool_lock:
        conn = _conn_pool.get(key)
        if conn is not None:
            # Test connection còn sống không — nhưng CHỈ khi đã nhàn rỗi một lúc.
            # "SELECT 1" là một vòng đi-về tới SQL Server; bắn nó trước MỌI request khiến
            # mỗi thao tác gánh thêm nguyên một round-trip mạng (thấy rõ khi server ở xa).
            # Connection vừa dùng cách đây vài giây thì gần như chắc chắn còn sống, mà nếu
            # có chết thật thì @with_db_lock đã bắt lỗi kết nối, invalidate_pool rồi chạy
            # lại lần 2 với connection sạch → vẫn an toàn, chỉ mất 1 lần thử.
            if (time.time() - _conn_last_used.get(key, 0)) < _POOL_PROBE_AFTER_SEC:
                _conn_last_used[key] = time.time()
                return conn
            try:
                conn.cursor().execute("SELECT 1").fetchone()
                _conn_last_used[key] = time.time()
                return conn
            except Exception:
                try: conn.close()
                except: pass
                _conn_pool.pop(key, None)
                _conn_last_used.pop(key, None)

        # Tạo connection mới
        conn = _make_conn(db_config)
        _conn_pool[key] = conn
        _conn_last_used[key] = time.time()
        return conn

def close_pool_for(db_config):
    """Đóng connection trong pool khi logout."""
    if not db_config:
        return
    key = _pool_key(db_config)
    with _pool_lock:
        conn = _conn_pool.pop(key, None)
        _conn_last_used.pop(key, None)   # bỏ luôn mốc thời gian, giữ 2 dict luôn khớp nhau
    if conn:
        try: conn.close()
        except: pass

def invalidate_pool():
    """Drop connection hiện tại khỏi pool (gọi khi query lỗi — có thể do conn chết giữa chừng)."""
    db_config = session.get('db_config')
    close_pool_for(db_config)

@app.route("/api/check_driver")
def check_driver():
    """Kiểm tra driver ODBC có tồn tại."""
    has_driver = check_odbc_driver()
    return jsonify({"has_driver": has_driver, "drivers": pyodbc.drivers()})

@app.route("/api/install_driver", methods=["POST"])
def install_driver():
    """Cài đặt ODBC driver."""
    success, message = install_odbc_driver()
    return jsonify({"success": success, "message": message})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.json
        # Nếu đã login trước đó với config khác → đóng connection cũ
        old = session.get('db_config')
        if old:
            close_pool_for(old)

        # Test kết nối bằng cách tạo conn mới và lưu vào pool luôn
        conn = _make_conn(data)
        # Giữ lại trong pool (không close)
        key = _pool_key(data)
        with _pool_lock:
            _conn_pool[key] = conn

        session['db_config'] = data
        _meta_cache.pop(data.get('database'), None)
        return jsonify({"status": "ok", "message": "Kết nối SQL Server thành công!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi kết nối: {str(e)}"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    db_config = session.get('db_config')
    db_name = (db_config or {}).get('database')
    close_pool_for(db_config)
    session.pop('db_config', None)
    if db_name:
        _meta_cache.pop(db_name, None)
    return jsonify({"status": "ok"})

@app.route("/api/metadata")
@with_db_lock
def get_metadata():
    try:
        db_name = session.get('db_config', {}).get('database', 'N/A')

        if db_name in _meta_cache:
            return jsonify(_meta_cache[db_name])

        conn = get_connection()
        cursor = conn.cursor()

        # Gộp toàn bộ dimension tables thành 1 batch query
        batch_sql = """
            SELECT 'account'   AS kind, CAST(ACCOUNT_ID      AS NVARCHAR(100)), ACCOUNT_NAME, NULL    FROM dbo.DM_ACCOUNT WITH (NOLOCK)     WHERE ACTIVE=1
            UNION ALL
            SELECT 'org',              CAST(ORGANIZATION_ID AS NVARCHAR(100)), ORGANIZATION_NAME, ADDRESS FROM dbo.DM_ORGANIZATION WITH (NOLOCK) WHERE ACTIVE=1
            UNION ALL
            SELECT 'pr_detail',        CAST(PR_DETAIL_ID    AS NVARCHAR(100)), PR_DETAIL_NAME, NULL FROM dbo.DM_PR_DETAIL WITH (NOLOCK)   WHERE ACTIVE=1
            UNION ALL
            SELECT 'job',              CAST(JOB_ID          AS NVARCHAR(100)), JOB_NAME,        NULL FROM dbo.DM_JOB WITH (NOLOCK)         WHERE ACTIVE=1
            UNION ALL
            SELECT 'item',             CAST(ITEM_ID         AS NVARCHAR(100)), ITEM_NAME,       NULL FROM dbo.DM_ITEM WITH (NOLOCK)        WHERE ACTIVE=1
            UNION ALL
            SELECT 'expense',          CAST(EXPENSE_ID      AS NVARCHAR(100)), EXPENSE_NAME,    NULL FROM dbo.DM_EXPENSE WITH (NOLOCK)     WHERE ACTIVE=1
            UNION ALL
            SELECT 'product',          CAST(PRODUCT_ID      AS NVARCHAR(100)), PRODUCT_NAME,    NULL FROM dbo.DM_PRODUCT WITH (NOLOCK)     WHERE ACTIVE=1
            UNION ALL
            SELECT 'warehouse',        CAST(WAREHOUSE_ID    AS NVARCHAR(100)), WAREHOUSE_NAME,  NULL FROM dbo.DM_WAREHOUSE WITH (NOLOCK)   WHERE ACTIVE=1
            UNION ALL
            SELECT 'unit',             CAST(UNIT_ID         AS NVARCHAR(100)), UNIT_NAME,       NULL FROM dbo.DM_UNIT WITH (NOLOCK)        WHERE ACTIVE=1
            UNION ALL
            SELECT 'banks',            CAST(BANK_ID         AS NVARCHAR(100)), BANK_NAME,       NULL FROM dbo.DM_BANK WITH (NOLOCK)        WHERE ACTIVE=1
        """
        cursor.execute(batch_sql)
        accounts, orgs, pr_details, jobs, items, expenses, products, warehouses, units, banks = [], [], [], [], [], [], [], [], [], []
        bucket = {
            'account': accounts, 'org': orgs, 'pr_detail': pr_details,
            'job': jobs, 'item': items, 'expense': expenses, 'product': products,
            'warehouse': warehouses, 'unit': units, 'banks': banks
        }
        for kind, id_val, name_val, extra_val in cursor.fetchall():
            item = {"id": (id_val or '').strip(), "name": name_val or ''}
            if extra_val: item["address"] = extra_val
            bucket[kind].append(item)

        cursor.execute("SELECT CAST(TRAN_ID AS NVARCHAR(100)), TRAN_NAME FROM dbo.SYS_TRAN WITH (NOLOCK) WHERE ACTIVE=1")
        sys_trans = {r[0].strip(): r[1].strip() if r[1] else '' for r in cursor.fetchall() if r[0]}

        # Thông tin công ty cho tiêu đề báo cáo — lấy từ dbo.SYS_SYSTEMVAR (key-value)
        company = {"name": "", "address": "", "tax_code": ""}
        try:
            cursor.execute("""SELECT VAR_NAME, VAR_VALUE FROM dbo.SYS_SYSTEMVAR WITH (NOLOCK)
                              WHERE VAR_NAME IN ('COMPANY_NAME','PARENT_COMPANY','ADDRESS','TAX_FILE_NUMBER')""")
            sv = {r[0]: (r[1] or '').strip() for r in cursor.fetchall()}
            company = {
                "name":     sv.get('COMPANY_NAME') or sv.get('PARENT_COMPANY') or '',
                "address":  sv.get('ADDRESS', ''),
                "tax_code": sv.get('TAX_FILE_NUMBER', ''),
            }
        except Exception:
            pass

        cursor.execute("SELECT DISTINCT TRAN_ID FROM dbo.LEDGER WITH (NOLOCK) WHERE TRAN_ID IS NOT NULL ORDER BY TRAN_ID")
        tran_ids = [{"id": r[0], "name": sys_trans.get(r[0].strip(), r[0])} for r in cursor.fetchall()]

        # Lấy row count từ metadata SQL Server (tức thì, không scan bảng)
        # index_id 0=heap, 1=clustered → IN (0,1) đảm bảo lấy đúng 1 cái
        cursor.execute("""
            SELECT ISNULL(SUM(row_count), 0)
            FROM sys.dm_db_partition_stats
            WHERE object_id = OBJECT_ID('dbo.LEDGER') AND index_id IN (0, 1)
        """)
        global_total = int(cursor.fetchone()[0] or 0)

        result = {
            "status": "ok",
            "db_info": {"database": db_name},
            "company": company,
            "global_total": global_total,
            "accounts": accounts, "orgs": orgs, "pr_details": pr_details,
            "tran_ids": tran_ids, "jobs": jobs, "items": items,
            "products": products, "expenses": expenses, "warehouses": warehouses,
            "units": units, "banks": banks
        }
        _meta_cache[db_name] = result
        return jsonify(result)
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()  # Conn có thể đã chết → drop khỏi pool
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500

@app.route("/api/metadata/refresh", methods=["POST"])
def refresh_metadata():
    db_name = session.get('db_config', {}).get('database')
    if db_name:
        _meta_cache.pop(db_name, None)
    return jsonify({"status": "ok"})

# Whitelist cột được phép sort cho từng endpoint — tránh SQL injection
LEDGER_SORT_WHITELIST = {
    "TRAN_DATE":         "L.TRAN_DATE",
    "TRAN_NO":           "L.TRAN_NO",
    "TRAN_ID":           "L.TRAN_ID",
    "ACCOUNT_ID":        "L.ACCOUNT_ID",
    "ACCOUNT_ID_CONTRA": "L.ACCOUNT_ID_CONTRA",
    "DESCRIPTION":       "L.DESCRIPTION",
    "AMOUNT":            "L.AMOUNT",
    "ORGANIZATION_ID":   "L.ORGANIZATION_ID",
    "PR_DETAIL_ID":      "L.PR_DETAIL_ID",
    "JOB_ID":            "L.JOB_ID",
    "ITEM_ID":           "L.ITEM_ID",
    "PRODUCT_ID":        "L.PRODUCT_ID",
    "EXPENSE_ID":        "L.EXPENSE_ID",
}

PURCHASE_SORT_WHITELIST = {col: f"P.{col}" for col in [
    "ORGANIZATION_ID","TRAN_ID","TRAN_NO","TRAN_DATE","VAT_TRAN_NO","VAT_TRAN_DATE",
    "PO_TRAN_NO","WAREHOUSE_ID","WAREHOUSE_NAME","ITEM_ID","DESCRIPTION","UNIT_ID",
    "QUANTITY","UNIT_ID_WH","QUANTITY_WH","UNIT_PRICE","DISCOUNT_AMOUNT","PURCHASE_COST",
    "VAT_TAX_RATE","VAT_TAX_AMOUNT","TOTAL_AMOUNT","ACCOUNT_ID_COST","PR_DETAIL_ID",
    "PR_DETAIL_NAME","EXPENSE_ID","JOB_ID","JOB_NAME"
]}
PURCHASE_SORT_WHITELIST["ORGANIZATION_NAME"] = "O.ORGANIZATION_NAME"
PURCHASE_SORT_WHITELIST["EXPENSE_NAME"]      = "E.EXPENSE_NAME"

WAREHOUSE_SORT_WHITELIST = {col: f"W.{col}" for col in [
    "ISSUE_RECEIVE","ORGANIZATION_ID","TRAN_ID","TRAN_NO","TRAN_DATE",
    "WAREHOUSE_ID","WAREHOUSE_NAME","WAREHOUSE_ID_ISSUE","ITEM_ID","ITEM_NAME",
    "UNIT_ID_WH","QUANTITY","UNIT_ID_EXTRA","QUANTITY_EXTRA","UNIT_PRICE","AMOUNT",
    "ACCOUNT_ID","ACCOUNT_ID_CONTRA","PR_DETAIL_ID","PR_DETAIL_NAME",
    "EXPENSE_ID","EXPENSE_NAME","JOB_ID","JOB_NAME"
]}
WAREHOUSE_SORT_WHITELIST["ORGANIZATION_NAME"]    = "O.ORGANIZATION_NAME"
WAREHOUSE_SORT_WHITELIST["WAREHOUSE_NAME_ISSUE"] = "WI.WAREHOUSE_NAME"


def _resolve_order_by(request_args, whitelist, default_sql):
    """Trả về ORDER BY clause an toàn từ request args."""
    col = request_args.get("order_by", "").strip()
    direction = request_args.get("order_dir", "desc").strip().lower()
    direction = "ASC" if direction == "asc" else "DESC"
    sql_col = whitelist.get(col)
    if not sql_col:
        return default_sql
    return f"{sql_col} {direction}"


def _apply_date_search(s_date, clauses, params):
    """Parse input ngày (cột 'Ngày CT') thành WHERE filter SARGable nhất có thể.

    Các dạng hỗ trợ:
      - "dd/mm/yyyy"   → exact date (SARGable)
      - "mm/yyyy"      → range toàn bộ tháng (SARGable)
      - "yyyy"         → range toàn bộ năm (SARGable)
      - "dd/mm"        → DAY(..)=dd AND MONTH(..)=mm (non-SARGable nhưng cơ hội dùng data lọc nhỏ hơn CONVERT+LIKE)
      - "dd"           → DAY(..)=dd (non-SARGable)
      - khác           → fallback CONVERT+LIKE (tương thích cũ)
    """
    s = s_date.strip()
    parts = [p for p in s.split('/') if p != '']
    try:
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100: y += 2000
            dt = date(y, m, d)
            clauses.append("L.TRAN_DATE = ?")
            params.append(dt.strftime("%Y%m%d"))
            return
        if len(parts) == 2:
            a, b = int(parts[0]), int(parts[1])
            # Phân biệt "mm/yyyy" vs "dd/mm"
            if b >= 1900:  # "mm/yyyy"
                month, year = a, b
                if 1 <= month <= 12:
                    start = date(year, month, 1)
                    end   = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)
                    clauses.append("L.TRAN_DATE >= ? AND L.TRAN_DATE < ?")
                    params.extend([start.strftime("%Y%m%d"), end.strftime("%Y%m%d")])
                    return
            # "dd/mm"
            if 1 <= a <= 31 and 1 <= b <= 12:
                clauses.append("DAY(L.TRAN_DATE) = ? AND MONTH(L.TRAN_DATE) = ?")
                params.extend([a, b])
                return
        if len(parts) == 1:
            n = int(parts[0])
            if n >= 1900:  # cả năm
                start = date(n, 1, 1)
                end   = date(n+1, 1, 1)
                clauses.append("L.TRAN_DATE >= ? AND L.TRAN_DATE < ?")
                params.extend([start.strftime("%Y%m%d"), end.strftime("%Y%m%d")])
                return
            if 1 <= n <= 31:  # ngày trong tháng
                clauses.append("DAY(L.TRAN_DATE) = ?")
                params.append(n)
                return
    except (ValueError, TypeError):
        pass
    # Fallback: giữ behavior cũ cho input không theo pattern
    clauses.append("CONVERT(VARCHAR(10), L.TRAN_DATE, 103) LIKE ?")
    params.append(f"%{s}%")

def _build_where(request_args):
    """Xây dựng WHERE clause + params từ request args. Trả về (where_sql, params, has_join_search)."""
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    clauses = ["L.TRAN_DATE >= ?", "L.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    # IN filters
    for field, arg in [
        ("L.TRAN_ID",          "tran_ids"),
        ("L.ORGANIZATION_ID",  "org_ids"),
        ("L.JOB_ID",           "job_ids"),
        ("L.PR_DETAIL_ID",     "pr_detail_ids"),
        ("L.ITEM_ID",          "item_ids"),
        ("L.PRODUCT_ID",       "product_ids"),
        ("L.EXPENSE_ID",       "expense_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    # Tài khoản / TK đối ứng: nếu chọn TK mẹ (vd 641) → match cả TK con (6411..6419)
    # Dùng LIKE 'xxx%' (SARGable) thay cho IN exact match
    for field, arg in [
        ("L.ACCOUNT_ID",       "acc_ids"),
        ("L.ACCOUNT_ID_CONTRA", "contra_acc_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            like_clauses = [f"{field} LIKE ?" for _ in vals]
            clauses.append("(" + " OR ".join(like_clauses) + ")")
            params.extend([f"{v}%" for v in vals])

    # LIKE search trên cột LEDGER
    # ID fields: trailing wildcard → dùng được index (100x nhanh hơn)
    # TEXT fields: contains → chấp nhận chậm do người dùng cần tìm keyword giữa câu
    ID_PREFIX_FIELDS = [
        ("L.TRAN_NO",          "tran_no"),
        ("L.TRAN_ID",          "s_tran_id"),
        ("L.ACCOUNT_ID",       "s_acc_id"),
        ("L.ACCOUNT_ID_CONTRA", "s_contra_id"),
        ("L.ORGANIZATION_ID",  "s_org_id"),
    ]
    TEXT_CONTAINS_FIELDS = [
        ("L.DESCRIPTION",      "s_desc"),
    ]

    for field, arg in ID_PREFIX_FIELDS:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")  # trailing wildcard — SARGable

    for field, arg in TEXT_CONTAINS_FIELDS:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    # Tìm theo ngày — parse thành filter SARGable thay vì CONVERT+LIKE
    s_date = request_args.get("s_date", "").strip()
    if s_date:
        _apply_date_search(s_date, clauses, params)

    # LIKE trên cột JOIN — NAME: dùng contains vì tên VN thường có tiền tố
    # (VD: "Phí điện", "Phí nước" → gõ "điện" tìm keyword giữa câu)
    join_clauses = []
    join_params  = []
    for field, arg in [
        ("PD.PR_DETAIL_NAME", "s_pr_name"),
        ("E.EXPENSE_NAME",    "s_exp_name"),
        ("O.ORGANIZATION_NAME","s_org_name"),
        ("I.ITEM_NAME",       "s_item_name"),
        ("P.ITEM_NAME",       "s_prod_name"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            join_clauses.append(f"{field} LIKE ?")
            join_params.append(f"%{val}%")

    return " AND ".join(clauses), params, join_clauses, join_params

@app.route("/api/ledger")
@with_db_lock
def get_ledger():
    try:
        page      = int(request.args.get("page",     1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        # Nếu frontend biết total từ lần query trước (đổi trang) → skip COUNT+SUM
        known_total  = request.args.get("known_total")
        known_deb    = request.args.get("known_deb")
        known_crd    = request.args.get("known_crd")
        skip_count   = page > 1 and known_total is not None and not export_all

        where_sql, params, join_clauses, join_params = _build_where(request.args)

        order_by_sql = _resolve_order_by(request.args, LEDGER_SORT_WHITELIST, "L.TRAN_DATE DESC, L.TRAN_NO")

        offset = (page - 1) * page_size

        # ---- CÁC CỘT LEDGER CƠ BẢN (không JOIN) ----
        BASE_COLS = """
            L.TRAN_DATE, L.TRAN_NO, L.TRAN_ID, L.DEBIT_CREDIT,
            L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA,
            L.PR_DETAIL_ID, L.DESCRIPTION, L.COMMENTS,
            L.AMOUNT, L.JOB_ID,
            L.ITEM_ID, L.PRODUCT_ID,
            L.EXPENSE_ID, L.ORGANIZATION_ID, L.BANK_ID, L.BANK_ID_CONTRA,
            L.EXPENSE_ID_CONTRA, L.PR_DETAIL_ID_CONTRA, L.JOB_ID_CONTRA, L.ITEM_ID_CONTRA
        """

        if join_clauses:
            # Có search trên cột tên → buộc phải JOIN các bảng dimension liên quan
            join_filter = " AND ".join(join_clauses)

            # Chỉ JOIN đúng bảng cần thiết cho search
            needed = set()
            for c in join_clauses:
                if 'PD.' in c: needed.add('pd')
                if 'E.'  in c: needed.add('e')
                if 'O.'  in c: needed.add('o')
                if 'I.'  in c: needed.add('i')
                if 'P.'  in c: needed.add('p')

            joins = ["FROM dbo.LEDGER L WITH (NOLOCK)"]
            if 'pd' in needed: joins.append("LEFT JOIN dbo.DM_PR_DETAIL   PD WITH (NOLOCK) ON L.PR_DETAIL_ID    = PD.PR_DETAIL_ID")
            if 'i'  in needed: joins.append("LEFT JOIN dbo.DM_ITEM         I  WITH (NOLOCK) ON L.ITEM_ID         = I.ITEM_ID")
            if 'p'  in needed: joins.append("LEFT JOIN dbo.DM_ITEM         P  WITH (NOLOCK) ON L.PRODUCT_ID      = P.ITEM_ID")
            if 'e'  in needed: joins.append("LEFT JOIN dbo.DM_EXPENSE      E  WITH (NOLOCK) ON L.EXPENSE_ID      = E.EXPENSE_ID")
            if 'o'  in needed: joins.append("LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON L.ORGANIZATION_ID = O.ORGANIZATION_ID")
            JOIN_TABLES = " ".join(joins)

            count_sql = f"""
                SELECT
                    COUNT(*) AS total_rows,
                    SUM(CASE WHEN L.DEBIT_CREDIT='DEB' THEN L.AMOUNT ELSE 0 END) AS sum_deb,
                    SUM(CASE WHEN L.DEBIT_CREDIT='CRD' THEN L.AMOUNT ELSE 0 END) AS sum_crd
                {JOIN_TABLES}
                WHERE {where_sql}
                AND {join_filter}
            """

            # Phân trang ROW_NUMBER(): tương thích SQL Server 2005+ (bao gồm cả SQL Server 2008)
            paged_sql = f"""
                SELECT * FROM (
                    SELECT {BASE_COLS},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {JOIN_TABLES}
                    WHERE {where_sql}
                    AND {join_filter}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            count_params = params + join_params
            data_params  = params + join_params
        else:
            # KHÔNG có join search → không JOIN gì cả (nhanh nhất có thể)
            # Tên dimension sẽ được map ở Python từ _meta_cache
            count_sql = f"""
                SELECT
                    COUNT(*) AS total_rows,
                    SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END) AS sum_deb,
                    SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END) AS sum_crd
                FROM dbo.LEDGER L WITH (NOLOCK)
                WHERE {where_sql}
            """

            paged_sql = f"""
                SELECT * FROM (
                    SELECT {BASE_COLS},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    FROM dbo.LEDGER L WITH (NOLOCK)
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            count_params = params
            data_params  = params

        conn   = get_connection()
        cursor = conn.cursor()

        if export_all:
            if join_clauses:
                sql = f"""
                    SELECT {BASE_COLS}
                    {JOIN_TABLES}
                    WHERE {where_sql}
                    AND {join_filter}
                    ORDER BY {order_by_sql}
                """
                cursor.execute(sql, data_params)
            else:
                sql = f"""
                    SELECT {BASE_COLS}
                    FROM dbo.LEDGER L WITH (NOLOCK)
                    WHERE {where_sql}
                    ORDER BY {order_by_sql}
                """
                cursor.execute(sql, data_params)
            columns  = [col[0] for c_idx, col in enumerate(cursor.description)]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            total_debit = 0
            total_credit = 0
            # Note: with export_all we don't calculate sum in python for large sets, or we can calculate it
            for r in raw_rows:
                dc = r[columns.index('DEBIT_CREDIT')] if 'DEBIT_CREDIT' in columns else None
                amt = float(r[columns.index('AMOUNT')] or 0) if 'AMOUNT' in columns else 0
                if dc == 'DEB': total_debit += amt
                elif dc == 'CRD': total_credit += amt
        else:
            # Query 1: COUNT + SUM — chỉ chạy khi page=1 hoặc frontend không biết total
            if skip_count:
                total_rows   = int(known_total)
                total_debit  = float(known_deb or 0)
                total_credit = float(known_crd or 0)
            else:
                cursor.execute(count_sql, count_params)
                count_row    = cursor.fetchone()
                total_rows   = count_row[0] or 0
                total_debit  = float(count_row[1] or 0)
                total_credit = float(count_row[2] or 0)
            
            # Query 2: Data trang hiện tại (ROW_NUMBER)
            cursor.execute(paged_sql, data_params + [offset, offset + page_size])
            columns  = [col[0] for col in cursor.description]
            raw_rows = cursor.fetchall()

        # Chuẩn bị dimension maps từ cache (để post-enrich khi không JOIN)
        db_name = session.get('db_config', {}).get('database', 'N/A')
        meta = _meta_cache.get(db_name)
        if meta is None:
            # Cache chưa có → populate bằng cách truy vấn dimension nhẹ
            # (xảy ra 1 lần sau khi login trực tiếp vào ledger mà chưa mở filter)
            try:
                cur2 = conn.cursor()
                cur2.execute("""
                    SELECT 'pr_details' k, CAST(PR_DETAIL_ID AS NVARCHAR(100)), PR_DETAIL_NAME FROM dbo.DM_PR_DETAIL WITH (NOLOCK) WHERE ACTIVE=1
                    UNION ALL SELECT 'items',    CAST(ITEM_ID AS NVARCHAR(100)),   ITEM_NAME    FROM dbo.DM_ITEM WITH (NOLOCK)     WHERE ACTIVE=1
                    UNION ALL SELECT 'products', CAST(PRODUCT_ID AS NVARCHAR(100)), PRODUCT_NAME FROM dbo.DM_PRODUCT WITH (NOLOCK)  WHERE ACTIVE=1
                    UNION ALL SELECT 'expenses', CAST(EXPENSE_ID AS NVARCHAR(100)), EXPENSE_NAME FROM dbo.DM_EXPENSE WITH (NOLOCK)  WHERE ACTIVE=1
                    UNION ALL SELECT 'orgs',     CAST(ORGANIZATION_ID AS NVARCHAR(100)), ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WITH (NOLOCK) WHERE ACTIVE=1
                    UNION ALL SELECT 'tran_ids', CAST(TRAN_ID AS NVARCHAR(100)), TRAN_NAME FROM dbo.SYS_TRAN WITH (NOLOCK) WHERE ACTIVE=1
                    UNION ALL SELECT 'banks',    CAST(BANK_ID AS NVARCHAR(100)), BANK_NAME FROM dbo.DM_BANK WITH (NOLOCK) WHERE ACTIVE=1
                    UNION ALL SELECT 'jobs',     CAST(JOB_ID AS NVARCHAR(100)), JOB_NAME  FROM dbo.DM_JOB WITH (NOLOCK)  WHERE ACTIVE=1
                """)
                partial = {'pr_details': [], 'items': [], 'products': [], 'expenses': [], 'orgs': [], 'tran_ids': [], 'banks': [], 'jobs': []}
                for k, i, n in cur2.fetchall():
                    partial[k].append({'id': (i or '').strip(), 'name': n or ''})
                meta = partial
            except Exception:
                meta = {}
        meta = meta or {}
        def _build_map(key):
            return {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get(key, [])}
        pr_map   = _build_map('pr_details')
        item_map = _build_map('items')
        prod_map = _build_map('products')
        exp_map  = _build_map('expenses')
        org_map  = _build_map('orgs')
        tran_map = _build_map('tran_ids')
        bank_map = _build_map('banks')
        job_map  = _build_map('jobs')

        # Tối ưu cho payload lớn (500k+ dòng): pre-compute column indices, tránh
        # dict(zip()) + .get() trong vòng lặp nóng. Build dict trực tiếp bằng index.
        col_idx = {c: i for i, c in enumerate(columns)}
        idx_pr     = col_idx.get('PR_DETAIL_ID', -1)
        idx_pr_contra = col_idx.get('PR_DETAIL_ID_CONTRA', -1)
        idx_item   = col_idx.get('ITEM_ID', -1)
        idx_item_contra = col_idx.get('ITEM_ID_CONTRA', -1)
        idx_prod   = col_idx.get('PRODUCT_ID', -1)
        idx_exp    = col_idx.get('EXPENSE_ID', -1)
        idx_exp_contra = col_idx.get('EXPENSE_ID_CONTRA', -1)
        idx_org    = col_idx.get('ORGANIZATION_ID', -1)
        idx_tran   = col_idx.get('TRAN_ID', -1)
        idx_bank   = col_idx.get('BANK_ID', -1)
        idx_bank_contra = col_idx.get('BANK_ID_CONTRA', -1)
        idx_date   = col_idx.get('TRAN_DATE', -1)
        idx_job    = col_idx.get('JOB_ID', -1)
        idx_job_contra = col_idx.get('JOB_ID_CONTRA', -1)
        has_pr_name   = 'PR_DETAIL_NAME' in col_idx
        has_pr_name_contra = 'PR_DETAIL_NAME_CONTRA' in col_idx
        has_item_name = 'ITEM_NAME' in col_idx
        has_item_name_contra = 'ITEM_NAME_CONTRA' in col_idx
        has_prod_name = 'PRODUCT_NAME' in col_idx
        has_exp_name  = 'EXPENSE_NAME' in col_idx
        has_exp_name_contra = 'EXPENSE_NAME_CONTRA' in col_idx
        has_org_name  = 'ORGANIZATION_NAME' in col_idx
        has_tran_name = 'TRAN_NAME' in col_idx
        has_bank_name = 'BANK_NAME' in col_idx
        has_bank_name_contra = 'BANK_NAME_CONTRA' in col_idx
        has_job_name = 'JOB_NAME' in col_idx
        has_job_name_contra = 'JOB_NAME_CONTRA' in col_idx

        def _strip(v):
            return v.strip() if isinstance(v, str) else (v or '')

        rows = []
        rows_append = rows.append
        for raw in raw_rows:
            r = {columns[i]: raw[i] for i in range(len(columns))}
            if idx_date != -1:
                dv = raw[idx_date]
                if isinstance(dv, (date, datetime)):
                    r['TRAN_DATE'] = dv.strftime("%d/%m/%Y")
            if not has_pr_name and idx_pr != -1:
                r['PR_DETAIL_NAME']    = pr_map.get(_strip(raw[idx_pr]), '')
            if not has_pr_name_contra and idx_pr_contra != -1:
                r['PR_DETAIL_NAME_CONTRA'] = pr_map.get(_strip(raw[idx_pr_contra]), '')
            if not has_item_name and idx_item != -1:
                r['ITEM_NAME']         = item_map.get(_strip(raw[idx_item]), '')
            if not has_item_name_contra and idx_item_contra != -1:
                r['ITEM_NAME_CONTRA']  = item_map.get(_strip(raw[idx_item_contra]), '')
            if not has_prod_name and idx_prod != -1:
                r['PRODUCT_NAME']      = item_map.get(_strip(raw[idx_prod]), '')
            if not has_exp_name and idx_exp != -1:
                r['EXPENSE_NAME']      = exp_map.get(_strip(raw[idx_exp]), '')
            if not has_exp_name_contra and idx_exp_contra != -1:
                r['EXPENSE_NAME_CONTRA'] = exp_map.get(_strip(raw[idx_exp_contra]), '')
            if not has_job_name and idx_job != -1:
                r['JOB_NAME']          = job_map.get(_strip(raw[idx_job]), '')
            if not has_job_name_contra and idx_job_contra != -1:
                r['JOB_NAME_CONTRA']   = job_map.get(_strip(raw[idx_job_contra]), '')
            if not has_org_name and idx_org != -1:
                r['ORGANIZATION_NAME'] = org_map.get(_strip(raw[idx_org]), '')
            if not has_tran_name and idx_tran != -1:
                r['TRAN_NAME']         = tran_map.get(_strip(raw[idx_tran]), '')
            if not has_bank_name and idx_bank != -1:
                r['BANK_NAME']         = bank_map.get(_strip(raw[idx_bank]), '')
            if not has_bank_name_contra and idx_bank_contra != -1:
                r['BANK_NAME_CONTRA']  = bank_map.get(_strip(raw[idx_bank_contra]), '')
            rows_append(r)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows":  total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size) if not export_all else 1,
                "page": page if not export_all else 1
            },
            "summary": {
                "total_debit":  total_debit,
                "total_credit": total_credit
            }
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# Cột lấy trực tiếp từ PURCHASE_VIEW (P). View đã có WAREHOUSE_NAME và JOB_NAME.
# Chỉ ORGANIZATION_NAME và EXPENSE_NAME phải JOIN bảng dimension.
PURCHASE_BASE_COLUMNS = [
    "ORGANIZATION_ID",
    "TRAN_ID", "TRAN_NO", "TRAN_DATE",
    "VAT_TRAN_NO", "VAT_TRAN_DATE", "PO_TRAN_NO",
    "WAREHOUSE_ID", "WAREHOUSE_NAME",
    "ITEM_ID", "DESCRIPTION", "UNIT_ID",
    "QUANTITY", "UNIT_ID_WH", "QUANTITY_WH",
    "UNIT_PRICE", "DISCOUNT_AMOUNT", "PURCHASE_COST",
    "VAT_TAX_RATE", "VAT_TAX_AMOUNT", "TOTAL_AMOUNT",
    "ACCOUNT_ID_COST",
    "EXPENSE_ID",
    "JOB_ID", "JOB_NAME",
    "PR_DETAIL_ID", "PR_DETAIL_NAME",
]

def _build_purchase_where(request_args):
    """WHERE + params cho dbo.PURCHASE_VIEW. Dùng alias P. Trả (where_sql, params)."""
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    clauses = ["P.TRAN_DATE >= ?", "P.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    for field, arg in [
        ("P.TRAN_ID",        "tran_ids"),
        ("P.ORGANIZATION_ID", "org_ids"),
        ("P.JOB_ID",         "job_ids"),
        ("P.ITEM_ID",        "item_ids"),
        ("P.EXPENSE_ID",     "expense_ids"),
        ("P.PR_DETAIL_ID",   "pr_detail_ids"),
        ("P.WAREHOUSE_ID",   "wh_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    # ID prefix LIKE
    for field, arg in [
        ("P.TRAN_NO",        "tran_no"),
        ("P.TRAN_ID",        "s_tran_id"),
        ("P.ORGANIZATION_ID", "s_org_id"),
        ("P.WAREHOUSE_ID",   "s_wh_id"),
        ("P.ITEM_ID",        "s_item_id"),
        ("P.VAT_TRAN_NO",    "s_inv_no"),
        ("P.PO_TRAN_NO",     "s_po_no"),
        ("P.EXPENSE_ID",     "s_exp_id"),
        ("P.JOB_ID",         "s_job_id"),
        ("P.ACCOUNT_ID_COST", "s_acc_cost"),
        ("P.PR_DETAIL_ID",   "s_pr_id"),
        ("P.UNIT_ID",        "s_unit_id"),
        ("P.UNIT_ID_WH",     "s_unit_id_wh"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    # text contains LIKE (cột đến từ JOIN dimension)
    for field, arg in [
        ("P.DESCRIPTION",      "s_desc"),
        ("O.ORGANIZATION_NAME", "s_org_name"),
        ("P.WAREHOUSE_NAME",   "s_wh_name"),
        ("E.EXPENSE_NAME",     "s_exp_name"),
        ("P.JOB_NAME",         "s_job_name"),
        ("P.PR_DETAIL_NAME",   "s_pr_name"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    # Search ngày VAT_TRAN_DATE — chỉ hỗ trợ dd/mm/yyyy
    vd = request_args.get("s_vat_date", "").strip()
    if vd:
        try:
            parts = [p for p in vd.split('/') if p]
            if len(parts) == 3:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100: y += 2000
                clauses.append("P.VAT_TRAN_DATE = ?")
                params.append(f"{y:04d}{m:02d}{d:02d}")
            else:
                clauses.append("CONVERT(VARCHAR(10), P.VAT_TRAN_DATE, 103) LIKE ?")
                params.append(f"%{vd}%")
        except Exception:
            clauses.append("CONVERT(VARCHAR(10), P.VAT_TRAN_DATE, 103) LIKE ?")
            params.append(f"%{vd}%")

    return " AND ".join(clauses), params


@app.route("/api/debug_purchase")
def debug_purchase():
    """Liệt kê cột thực tế của dbo.PURCHASE_VIEW + sample 3 dòng."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'PURCHASE_VIEW'
            ORDER BY ORDINAL_POSITION
        """)
        cols = [{"name": r[0], "type": r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM dbo.PURCHASE_VIEW WITH (NOLOCK)")
        total = cursor.fetchone()[0]
        sample = []
        try:
            cursor.execute("SELECT TOP 3 * FROM dbo.PURCHASE_VIEW WITH (NOLOCK)")
            sample_cols = [c[0] for c in cursor.description]
            for r in cursor.fetchall():
                sample.append({c: (v.strftime("%d/%m/%Y") if hasattr(v,'strftime') else (float(v) if hasattr(v,'real') and not isinstance(v,bool) else (str(v) if v is not None else None))) for c, v in zip(sample_cols, r)})
        except Exception as se:
            sample = [{"err": str(se)}]
        return jsonify({"total_rows": total, "columns": cols, "sample": sample})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/purchase")
@with_db_lock
def get_purchase():
    """Danh sách chứng từ nhập kho lấy từ dbo.PURCHASE_VIEW."""
    try:
        page      = int(request.args.get("page",     1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")  # JSON string
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

        where_sql, params = _build_purchase_where(request.args)
        order_by_sql = _resolve_order_by(request.args, PURCHASE_SORT_WHITELIST, "P.TRAN_DATE DESC, P.TRAN_NO")
        col_list = ", ".join(f"P.{c}" for c in PURCHASE_BASE_COLUMNS)
        # JOIN bảng dimension để lấy ORGANIZATION_NAME, EXPENSE_NAME
        # (WAREHOUSE_NAME, JOB_NAME đã có sẵn trong PURCHASE_VIEW)
        JOIN_SQL = """
            FROM dbo.PURCHASE_VIEW P WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON P.ORGANIZATION_ID = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_EXPENSE      E WITH (NOLOCK) ON P.EXPENSE_ID      = E.EXPENSE_ID
        """
        SELECT_LIST = f"{col_list}, O.ORGANIZATION_NAME AS ORGANIZATION_NAME, E.EXPENSE_NAME AS EXPENSE_NAME"

        conn   = get_connection()
        cursor = conn.cursor()

        SUM_SQL = """
            SUM(ISNULL(P.QUANTITY,0))        AS S_QUANTITY,
            SUM(ISNULL(P.QUANTITY_WH,0))     AS S_QUANTITY_WH,
            SUM(ISNULL(P.DISCOUNT_AMOUNT,0)) AS S_DISCOUNT,
            SUM(ISNULL(P.VAT_TAX_AMOUNT,0))  AS S_VAT_TAX,
            SUM(ISNULL(P.TOTAL_AMOUNT,0))    AS S_TOTAL
        """

        if export_all:
            sql = f"""
                SELECT {SELECT_LIST}
                {JOIN_SQL}
                WHERE {where_sql}
                ORDER BY {order_by_sql}
            """
            cursor.execute(sql, params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            summary = {"quantity": 0, "quantity_wh": 0, "discount": 0, "vat_tax": 0, "total": 0}
            qi = {c: i for i, c in enumerate(columns)}
            for r in raw_rows:
                summary["quantity"]    += float(r[qi.get("QUANTITY")]        or 0) if "QUANTITY"        in qi else 0
                summary["quantity_wh"] += float(r[qi.get("QUANTITY_WH")]     or 0) if "QUANTITY_WH"     in qi else 0
                summary["discount"]    += float(r[qi.get("DISCOUNT_AMOUNT")] or 0) if "DISCOUNT_AMOUNT" in qi else 0
                summary["vat_tax"]     += float(r[qi.get("VAT_TAX_AMOUNT")]  or 0) if "VAT_TAX_AMOUNT"  in qi else 0
                summary["total"]       += float(r[qi.get("TOTAL_AMOUNT")]    or 0) if "TOTAL_AMOUNT"    in qi else 0
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"quantity":0,"quantity_wh":0,"discount":0,"vat_tax":0,"total":0}
            else:
                cursor.execute(f"SELECT COUNT(*), {SUM_SQL} {JOIN_SQL} WHERE {where_sql}", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {
                    "quantity":    float(row[1] or 0),
                    "quantity_wh": float(row[2] or 0),
                    "discount":    float(row[3] or 0),
                    "vat_tax":     float(row[4] or 0),
                    "total":       float(row[5] or 0),
                }

            offset = (page - 1) * page_size
            sql = f"""
                SELECT * FROM (
                    SELECT {SELECT_LIST},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {JOIN_SQL}
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            cursor.execute(sql, params + [offset, offset + page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        db_name = session.get('db_config', {}).get('database', 'N/A')
        meta = _meta_cache.get(db_name) or {}
        tran_map = { (it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', []) }

        rows = []
        for raw in raw_rows:
            r = dict(zip(columns, raw))
            if 'TRAN_NAME' not in r:
                r['TRAN_NAME'] = tran_map.get((str(r.get('TRAN_ID') or '')).strip(), '')
            for dk in ("TRAN_DATE", "VAT_TRAN_DATE"):
                v = r.get(dk)
                if isinstance(v, (date, datetime)):
                    r[dk] = v.strftime("%d/%m/%Y")
            for nk in ("QUANTITY","QUANTITY_WH","UNIT_PRICE","DISCOUNT_AMOUNT","PURCHASE_COST","VAT_TAX_RATE","VAT_TAX_AMOUNT","TOTAL_AMOUNT"):
                v = r.get(nk)
                if v is not None:
                    try: r[nk] = float(v)
                    except: pass
            rows.append(r)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows":  total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            },
            "summary": summary
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# =============== WAREHOUSE_VIEW (Phiếu nhập/xuất kho) ===============
WAREHOUSE_BASE_COLUMNS = [
    "ISSUE_RECEIVE",
    "ORGANIZATION_ID",
    "TRAN_ID", "TRAN_NO", "TRAN_DATE",
    "WAREHOUSE_ID", "WAREHOUSE_NAME",
    "WAREHOUSE_ID_ISSUE",
    "ITEM_ID", "ITEM_NAME",
    "UNIT_ID_WH", "QUANTITY",
    "UNIT_ID_EXTRA", "QUANTITY_EXTRA",
    "UNIT_PRICE", "AMOUNT",
    "ACCOUNT_ID", "ACCOUNT_ID_CONTRA",
    "PR_DETAIL_ID", "PR_DETAIL_NAME",
    "EXPENSE_ID", "EXPENSE_NAME",
    "JOB_ID", "JOB_NAME",
]

def _build_warehouse_where(request_args):
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    clauses = ["W.TRAN_DATE >= ?", "W.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    for field, arg in [
        ("W.TRAN_ID",        "tran_ids"),
        ("W.ORGANIZATION_ID", "org_ids"),
        ("W.JOB_ID",         "job_ids"),
        ("W.ITEM_ID",        "item_ids"),
        ("W.EXPENSE_ID",     "expense_ids"),
        ("W.PR_DETAIL_ID",   "pr_detail_ids"),
        ("W.WAREHOUSE_ID",   "wh_ids"),
        ("W.PRODUCT_ID",     "product_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    ir = request_args.get("issue_receive", "").strip()
    if ir in ("N", "X"):
        clauses.append("W.ISSUE_RECEIVE = ?")
        params.append(ir)

    for field, arg in [
        ("W.TRAN_NO",           "tran_no"),
        ("W.TRAN_ID",           "s_tran_id"),
        ("W.ORGANIZATION_ID",   "s_org_id"),
        ("W.WAREHOUSE_ID",      "s_wh_id"),
        ("W.WAREHOUSE_ID_ISSUE", "s_wh_id_issue"),
        ("W.ITEM_ID",           "s_item_id"),
        ("W.PR_DETAIL_ID",      "s_pr_id"),
        ("W.EXPENSE_ID",        "s_exp_id"),
        ("W.JOB_ID",            "s_job_id"),
        ("W.ACCOUNT_ID",        "s_acc_id"),
        ("W.ACCOUNT_ID_CONTRA", "s_acc_contra"),
        ("W.UNIT_ID_WH",        "s_unit_id_wh"),
        ("W.UNIT_ID_EXTRA",     "s_unit_id_extra"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    for field, arg in [
        ("W.DESCRIPTION",      "s_desc"),
        ("O.ORGANIZATION_NAME", "s_org_name"),
        ("W.WAREHOUSE_NAME",   "s_wh_name"),
        ("WI.WAREHOUSE_NAME",  "s_wh_name_issue"),
        ("W.ITEM_NAME",        "s_item_name"),
        ("W.EXPENSE_NAME",     "s_exp_name"),
        ("W.JOB_NAME",         "s_job_name"),
        ("W.PR_DETAIL_NAME",   "s_pr_name"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    return " AND ".join(clauses), params


@app.route("/api/warehouse")
@with_db_lock
def get_warehouse():
    try:
        page      = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

        where_sql, params = _build_warehouse_where(request.args)
        order_by_sql = _resolve_order_by(request.args, WAREHOUSE_SORT_WHITELIST, "W.TRAN_DATE DESC, W.TRAN_NO")

        select_parts = [f"W.{c}" for c in WAREHOUSE_BASE_COLUMNS]
        select_parts.append("O.ORGANIZATION_NAME AS ORGANIZATION_NAME")
        select_parts.append("WI.WAREHOUSE_NAME AS WAREHOUSE_NAME_ISSUE")
        SELECT_LIST = ", ".join(select_parts)

        JOIN_SQL = """
            FROM dbo.WAREHOUSE_VIEW W WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON W.ORGANIZATION_ID    = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_WAREHOUSE    WI WITH (NOLOCK) ON W.WAREHOUSE_ID_ISSUE = WI.WAREHOUSE_ID
        """

        SUM_SQL = """
            SUM(ISNULL(W.QUANTITY,0))       AS S_QUANTITY,
            SUM(ISNULL(W.QUANTITY_EXTRA,0)) AS S_QUANTITY_EXTRA,
            SUM(ISNULL(W.AMOUNT,0))         AS S_AMOUNT
        """

        conn = get_connection()
        cursor = conn.cursor()

        if export_all:
            sql = f"SELECT {SELECT_LIST} {JOIN_SQL} WHERE {where_sql} ORDER BY {order_by_sql}"
            cursor.execute(sql, params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            summary = {"quantity": 0, "quantity_extra": 0, "amount": 0}
            qi = {c: i for i, c in enumerate(columns)}
            for r in raw_rows:
                summary["quantity"]       += float(r[qi.get("QUANTITY")]       or 0) if "QUANTITY"       in qi else 0
                summary["quantity_extra"] += float(r[qi.get("QUANTITY_EXTRA")] or 0) if "QUANTITY_EXTRA" in qi else 0
                summary["amount"]         += float(r[qi.get("AMOUNT")]         or 0) if "AMOUNT"         in qi else 0
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"quantity":0,"quantity_extra":0,"amount":0}
            else:
                cursor.execute(f"SELECT COUNT(*), {SUM_SQL} {JOIN_SQL} WHERE {where_sql}", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {
                    "quantity":       float(row[1] or 0),
                    "quantity_extra": float(row[2] or 0),
                    "amount":         float(row[3] or 0),
                }

            offset = (page - 1) * page_size
            sql = f"""
                SELECT * FROM (
                    SELECT {SELECT_LIST},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {JOIN_SQL}
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            cursor.execute(sql, params + [offset, offset + page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        db_name = session.get('db_config', {}).get('database', 'N/A')
        meta = _meta_cache.get(db_name) or {}
        tran_map = { (it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', []) }

        rows = []
        for raw in raw_rows:
            r = dict(zip(columns, raw))
            if 'TRAN_NAME' not in r:
                r['TRAN_NAME'] = tran_map.get((str(r.get('TRAN_ID') or '')).strip(), '')
            v = r.get("TRAN_DATE")
            if isinstance(v, (date, datetime)):
                r["TRAN_DATE"] = v.strftime("%d/%m/%Y")
            for nk in ("QUANTITY","QUANTITY_EXTRA","UNIT_PRICE","AMOUNT"):
                v = r.get(nk)
                if v is not None:
                    try: r[nk] = float(v)
                    except: pass
            rows.append(r)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows": total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            },
            "summary": summary
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# ============== EXPORT CSV TO DISK (cho dataset lớn) ==============
import uuid

# Folder lưu file export — Downloads\iPOS_Ledger_Studio
def _export_dir():
    home = os.path.expanduser("~")
    # Windows: Downloads. Khác OS: home directory.
    if platform.system() == "Windows":
        base = os.path.join(home, "Downloads", "iPOS_Ledger_Studio")
    else:
        base = os.path.join(home, "iPOS_Ledger_Studio")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = home
    return base


# In-memory map theo dõi tiến trình job export
# { job_id: { status, current, total, file_path, filename, error } }
_export_jobs = {}
_export_jobs_lock = threading.Lock()


def _csv_escape(v):
    """Escape 1 cell cho CSV chuẩn RFC 4180."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in (',', '"', '\n', '\r')):
        return '"' + s.replace('"', '""') + '"'
    return s


def _csv_text_cell(v):
    """Ép Excel giữ NGUYÊN chuỗi mã (không mất số 0 đầu, vd '03' → không thành 3).
    Trả về công thức Excel ="..."; ô rỗng giữ rỗng. Kết quả vẫn phải đi qua _csv_escape."""
    s = "" if v is None else str(v).strip()
    return f'="{s}"' if s else ""


def _finish_part_file(out_path):
    """File ghi ra tên tạm '*.part' → đổi về tên thật TRƯỚC khi báo 'done' (không bao giờ lộ file dở dang)."""
    if out_path.endswith('.part'):
        final = out_path[:-5]
        os.replace(out_path, final)
        return final
    return out_path


def _write_csv_to_disk(job_id, headers, row_iter, filename, total_estimate, out_path=None):
    """Ghi CSV vào disk theo job_id, update progress vào _export_jobs."""
    out_path = out_path or os.path.join(_export_dir(), filename)
    try:
        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(','.join(_csv_escape(h) for h in headers) + '\r\n')
            BATCH = 2000
            count = 0
            buf = []
            for row in row_iter:
                buf.append(','.join(_csv_escape(v) for v in row))
                if len(buf) >= BATCH:
                    f.write('\r\n'.join(buf) + '\r\n')
                    count += len(buf)
                    buf.clear()
                    with _export_jobs_lock:
                        job = _export_jobs.get(job_id)
                        if job is not None:
                            job['current'] = count
                            if job.get('cancelled'):
                                raise RuntimeError("Cancelled by user")
            if buf:
                f.write('\r\n'.join(buf) + '\r\n')
                count += len(buf)

        final_path = _finish_part_file(out_path)
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            if job is not None:
                job['status']    = 'done'
                job['current']   = count
                job['total']     = count
                job['file_path'] = final_path
                job['filename']  = os.path.basename(final_path)
    except Exception as e:
        # Xoá file dở dang
        try: os.remove(out_path)
        except: pass
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            if job is not None:
                job['status'] = 'error'
                job['error']  = str(e)


# Tách sheet danh sách chứng từ khi chạm mốc này (trần Excel 1.048.576 dòng/sheet) — cùng mốc với báo cáo.
LIST_XLSX_SHEET_ROWS = 1000000


def _write_xlsx_to_disk(job_id, headers, row_iter, filename, total_estimate, out_path=None):
    """Ghi dữ liệu lớn ra XLSX (constant_memory), tự sang sheet mới khi chạm LIST_XLSX_SHEET_ROWS dòng.

    ⚠️ pyodbc trả cột tiền/số lượng kiểu Decimal. Bản cũ chỉ nhận int/float là số ⇒ mọi cột Decimal
    (số lượng, đơn giá, thành tiền của phiếu nhập/kho/bán hàng…) bị ghi thành CHỮ: SUM ra 0, ô có tam giác xanh.
    Số nguyên hiện #,##0; số lẻ hiện #,##0.## (không cắt mất phần lẻ như trước)."""
    import xlsxwriter
    from decimal import Decimal as _Dec
    out_path = out_path or os.path.join(_export_dir(), filename)
    try:
        workbook = xlsxwriter.Workbook(out_path, {'constant_memory': True, 'strings_to_numbers': False,
                                                  'strings_to_formulas': False, 'strings_to_urls': False})
        if total_estimate > 300000:
            workbook.use_zip64()   # XML 1 sheet có thể vượt 4 GB khi giải nén → không bật thì close() lỗi
        base = {'font_name': 'Arial', 'font_size': 10}
        header_format = workbook.add_format(dict(base, bold=True, bg_color='#F1F5F9', align='center', valign='vcenter',
                                                 text_wrap=True, border=1, border_color='#CBD5E1'))
        int_format = workbook.add_format(dict(base, num_format='#,##0'))
        dec_format = workbook.add_format(dict(base, num_format='#,##0.##'))
        date_format = workbook.add_format(dict(base, num_format='dd/mm/yyyy', align='center'))
        text_format = workbook.add_format(dict(base, num_format='@'))
        ncols = len(headers)
        widths = [min(40, max(9, len(str(h)) + 3)) for h in headers]
        sheets = []

        def new_sheet(idx):
            ws = workbook.add_worksheet(f"Sheet {idx}")
            ws.freeze_panes(1, 0)
            ws.set_row(0, 30)
            for col_num, header in enumerate(headers):
                ws.write_string(0, col_num, str(header), header_format)
            sheets.append(ws)
            return ws

        worksheet = new_sheet(1)
        row_num = 1
        count = 0
        for row in row_iter:
            if row_num > LIST_XLSX_SHEET_ROWS:
                sheets[-1].autofilter(0, 0, row_num - 1, ncols - 1)
                worksheet = new_sheet(len(sheets) + 1)
                row_num = 1

            for col_num, val in enumerate(row):
                if val is None or val == '':
                    worksheet.write_blank(row_num, col_num, "", text_format)
                elif isinstance(val, (datetime, date)):
                    worksheet.write_datetime(row_num, col_num, val, date_format)
                    if count < 200 and col_num < ncols:
                        widths[col_num] = max(widths[col_num], 12)
                elif isinstance(val, (int, float, _Dec)) and not isinstance(val, bool):
                    num = float(val)
                    worksheet.write_number(row_num, col_num, num, int_format if num.is_integer() else dec_format)
                    if count < 200 and col_num < ncols:
                        widths[col_num] = max(widths[col_num], min(20, len(f"{num:,.0f}") + 3))
                else:
                    s = str(val)
                    worksheet.write_string(row_num, col_num, s, text_format)
                    if count < 200 and col_num < ncols:
                        widths[col_num] = max(widths[col_num], min(50, len(s) + 2))

            row_num += 1
            count += 1
            if count % 2000 == 0:
                with _export_jobs_lock:
                    job = _export_jobs.get(job_id)
                    if job is not None:
                        job['current'] = count
                        if job.get('cancelled'):
                            raise RuntimeError("Cancelled by user")

        sheets[-1].autofilter(0, 0, max(1, row_num - 1), ncols - 1)
        for ws in sheets:
            for col_num, w in enumerate(widths):
                ws.set_column(col_num, col_num, w)
            ws.ignore_errors({'number_stored_as_text': 'A1:XFD1048576'})
        workbook.close()
        final_path = _finish_part_file(out_path)
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            if job is not None:
                job['status'] = 'done'
                job['current'] = count
                job['total'] = count
                job['file_path'] = final_path
                job['filename'] = os.path.basename(final_path)
    except Exception as e:
        try:
            # chưa close() thì xlsxwriter chưa tạo file đích — chỉ còn file tạm từng sheet trong %TEMP%
            for _ws in (workbook.worksheets() if 'workbook' in locals() and not workbook.fileclosed else []):
                if getattr(_ws, 'row_data_fh', None):
                    _ws.row_data_fh.close()
                if getattr(_ws, 'row_data_filename', None) and os.path.exists(_ws.row_data_filename):
                    os.remove(_ws.row_data_filename)
        except Exception:
            pass
        try: os.remove(out_path)
        except: pass
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            if job is not None:
                job['status'] = 'error'
                job['error']  = str(e)


@app.route("/api/export/status")
def get_export_status():
    """Frontend poll để hiển thị progress."""
    job_id = request.args.get("job_id", "")
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
        if not job:
            return jsonify({"status": "not_found"}), 404
        return jsonify({k: v for k, v in job.items() if k != 'cancelled'})


@app.route("/api/export/cancel", methods=["POST"])
def cancel_export():
    job_id = request.json.get("job_id") if request.is_json else request.args.get("job_id", "")
    with _export_jobs_lock:
        job = _export_jobs.get(job_id)
        if job and job.get('status') == 'running':
            job['cancelled'] = True
    return jsonify({"status": "ok"})


@app.route("/api/save_export", methods=["POST"])
def save_export_route():
    """Lưu file xuất (XLS/CSV) vào _export_dir và trả về đường dẫn để mở file/folder."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        filename = data.get("filename", "export.xls")
        content = data.get("content", "")
        filename = os.path.basename(filename)
        out_path = os.path.join(_export_dir(), filename)
        
        with open(out_path, "w", encoding="utf-8-sig", errors="ignore", newline="") as f:
            f.write(content)
            
        return jsonify({
            "status": "ok",
            "path": out_path,
            "filename": filename
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/open_file", methods=["POST"])
def open_file_route():
    """Mở file (CSV/Excel) bằng app mặc định của OS."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        path = data.get("path", "")
        # Validate: chỉ cho mở file trong _export_dir để tránh bị abuse
        norm = os.path.realpath(path)
        if not norm.startswith(os.path.realpath(_export_dir())):
            return jsonify({"status": "error", "message": "Đường dẫn không hợp lệ"}), 400
        if not os.path.exists(norm):
            return jsonify({"status": "error", "message": "File không tồn tại"}), 404
        if platform.system() == "Windows":
            os.startfile(norm)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", norm])
        else:
            subprocess.Popen(["xdg-open", norm])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/open_folder", methods=["POST"])
def open_folder_route():
    """Mở Explorer/Finder vào folder chứa file (highlight file)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        path = data.get("path", "")
        norm = os.path.realpath(path)
        exp_root = os.path.realpath(_export_dir())
        if not norm.startswith(exp_root):
            return jsonify({"status": "error", "message": "Đường dẫn không hợp lệ"}), 400
        if platform.system() == "Windows":
            win_path = os.path.normpath(norm)
            if os.path.exists(win_path):
                subprocess.Popen(f'explorer.exe /select,"{win_path}"')
            else:
                subprocess.Popen(f'explorer.exe "{os.path.normpath(exp_root)}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", norm if os.path.exists(norm) else exp_root])
        else:
            target = os.path.dirname(norm) if os.path.exists(norm) else exp_root
            subprocess.Popen(["xdg-open", target])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _start_export_job(filename, headers, sql, params, transform_row, total_estimate=0):
    """Mở connection mới (cùng db_config session) → chạy query → ghi disk ở thread riêng.

    transform_row(raw_row, sql_cols) → list giá trị theo thứ tự headers.
    Trả về job_id ngay.
    """
    job_id = uuid.uuid4().hex
    # Tên file không trùng file cũ: trước đây xuất lại cùng khoảng ngày là GHI ĐÈ — mà file cũ đang mở trong Excel
    # thì Windows khoá file ⇒ job lỗi "Permission denied". Nay tự thêm (2), (3)… và ghi ra *.part rồi mới đổi tên.
    ext = 'xlsx' if filename.lower().endswith('.xlsx') else 'csv'
    final_path = _rx_reserve_path(filename, ext)
    filename = os.path.basename(final_path)
    with _export_jobs_lock:
        _export_jobs[job_id] = {
            'status': 'running', 'current': 0, 'total': total_estimate,
            'file_path': None, 'filename': filename, 'error': None,
            'cancelled': False,
        }
    db_cfg = session.get('db_config')

    def _runner():
        own_conn = None
        try:
            if not db_cfg:
                raise Exception("Chưa đăng nhập SQL Server")
            # Connection riêng cho thread — không dùng pool chung
            own_conn = _make_conn(db_cfg)
            cursor = own_conn.cursor()
            cursor.execute(sql, params)
            sql_cols = [c[0] for c in cursor.description]

            def row_iter():
                while True:
                    batch = cursor.fetchmany(1000)
                    if not batch: break
                    for raw in batch:
                        yield transform_row(raw, sql_cols)

            if ext == 'xlsx':
                _write_xlsx_to_disk(job_id, headers, row_iter(), filename, total_estimate, out_path=final_path + '.part')
            else:
                _write_csv_to_disk(job_id, headers, row_iter(), filename, total_estimate, out_path=final_path + '.part')
        except Exception as e:
            with _export_jobs_lock:
                job = _export_jobs.get(job_id)
                if job is not None:
                    job['status'] = 'error'
                    job['error']  = str(e)
        finally:
            if own_conn:
                try: own_conn.close()
                except: pass
            with _export_jobs_lock:
                _export_reserved.discard(final_path.lower())

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


# --- LEDGER count + stream csv ---
LEDGER_CSV_COLS = [
    ("TRAN_DATE","Ngày CT"), ("TRAN_NO","Số chứng từ"), ("TRAN_ID","Mã CT"), ("TRAN_NAME","Tên chứng từ"),
    ("ACCOUNT_ID","Tài khoản"), ("ACCOUNT_ID_CONTRA","Đối ứng"),
    ("DESCRIPTION","Diễn giải"),
    ("DEBIT","Nợ"), ("CREDIT","Có"),
    ("PR_DETAIL_ID","Mã ĐT"), ("PR_DETAIL_NAME","Đối tượng"),
    ("PR_DETAIL_ID_CONTRA","Mã ĐT ĐƯ"), ("PR_DETAIL_NAME_CONTRA","Đối tượng ĐƯ"),
    ("EXPENSE_ID","Mã MCP"), ("EXPENSE_NAME","Mục chi phí"),
    ("EXPENSE_ID_CONTRA","Mã MCP ĐƯ"), ("EXPENSE_NAME_CONTRA","Mục chi phí ĐƯ"),
    ("ORGANIZATION_ID","Mã ĐV"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("ITEM_ID","Mã HH"), ("ITEM_NAME","Hàng hóa"),
    ("ITEM_ID_CONTRA","Mã HH ĐƯ"), ("ITEM_NAME_CONTRA","Hàng hóa ĐƯ"),
    ("JOB_ID","Mã CV"), ("JOB_NAME","Công việc"),
    ("JOB_ID_CONTRA","Mã CV ĐƯ"), ("JOB_NAME_CONTRA","Công việc ĐƯ"),
    ("PRODUCT_ID","Mã SP"), ("PRODUCT_NAME","Sản phẩm"),
    ("BANK_ID","Mã NH"), ("BANK_NAME","Ngân hàng"),
    ("BANK_ID_CONTRA","Mã NH ĐƯ"), ("BANK_NAME_CONTRA","NH đối ứng"),
]


@app.route("/api/ledger/count")
@with_db_lock
def get_ledger_count():
    """Chỉ trả số dòng (cho frontend quyết định xuất xlsx hay stream CSV)."""
    try:
        where_sql, params, join_clauses, join_params = _build_where(request.args)
        conn = get_connection()
        cursor = conn.cursor()
        if join_clauses:
            needed = set()
            for c in join_clauses:
                if 'PD.' in c: needed.add('pd')
                if 'E.'  in c: needed.add('e')
                if 'O.'  in c: needed.add('o')
                if 'I.'  in c: needed.add('i')
                if 'P.'  in c: needed.add('p')
                if 'B.'  in c: needed.add('b')
            joins = ["FROM dbo.LEDGER L WITH (NOLOCK)"]
            if 'pd' in needed: joins.append("LEFT JOIN dbo.DM_PR_DETAIL   PD WITH (NOLOCK) ON L.PR_DETAIL_ID    = PD.PR_DETAIL_ID")
            if 'i'  in needed: joins.append("LEFT JOIN dbo.DM_ITEM         I  WITH (NOLOCK) ON L.ITEM_ID         = I.ITEM_ID")
            if 'p'  in needed: joins.append("LEFT JOIN dbo.DM_ITEM         P  WITH (NOLOCK) ON L.PRODUCT_ID      = P.ITEM_ID")
            if 'e'  in needed: joins.append("LEFT JOIN dbo.DM_EXPENSE      E  WITH (NOLOCK) ON L.EXPENSE_ID      = E.EXPENSE_ID")
            if 'o'  in needed: joins.append("LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON L.ORGANIZATION_ID = O.ORGANIZATION_ID")
            if 'b'  in needed: joins.append("LEFT JOIN dbo.DM_BANK         B  WITH (NOLOCK) ON L.BANK_ID         = B.BANK_ID")
            jt = " ".join(joins)
            join_filter = " AND ".join(join_clauses)
            cursor.execute(f"SELECT COUNT(*) {jt} WHERE {where_sql} AND {join_filter}", params + join_params)
        else:
            cursor.execute(f"SELECT COUNT(*) FROM dbo.LEDGER L WITH (NOLOCK) WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/ledger/stream_csv", methods=["POST", "GET"])
def get_ledger_stream_csv():
    """Tạo job ghi CSV vào disk + trả job_id để poll progress."""
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params, join_clauses, join_params = _build_where(args)
        order_by_sql = _resolve_order_by(args, LEDGER_SORT_WHITELIST, "L.TRAN_DATE DESC, L.TRAN_NO")

        BASE_COLS = """
            L.TRAN_DATE, L.TRAN_NO, L.TRAN_ID, T.TRAN_NAME,
            L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA,
            L.DESCRIPTION, L.COMMENTS, L.DEBIT_CREDIT, L.AMOUNT,
            L.PR_DETAIL_ID, PD.PR_DETAIL_NAME,
            L.PR_DETAIL_ID_CONTRA, PD2.PR_DETAIL_NAME AS PR_DETAIL_NAME_CONTRA,
            L.EXPENSE_ID, E.EXPENSE_NAME,
            L.EXPENSE_ID_CONTRA, E2.EXPENSE_NAME AS EXPENSE_NAME_CONTRA,
            L.ORGANIZATION_ID, O.ORGANIZATION_NAME,
            L.ITEM_ID, I.ITEM_NAME,
            L.ITEM_ID_CONTRA, I2.ITEM_NAME AS ITEM_NAME_CONTRA,
            L.JOB_ID, J.JOB_NAME,
            L.JOB_ID_CONTRA, J2.JOB_NAME AS JOB_NAME_CONTRA,
            L.PRODUCT_ID, P.ITEM_NAME AS PRODUCT_NAME,
            L.BANK_ID, B.BANK_NAME,
            L.BANK_ID_CONTRA, B2.BANK_NAME AS BANK_NAME_CONTRA
        """
        joins = [
            "FROM dbo.LEDGER L WITH (NOLOCK)",
            "LEFT JOIN dbo.SYS_TRAN       T   WITH (NOLOCK) ON L.TRAN_ID             = T.TRAN_ID",
            "LEFT JOIN dbo.DM_PR_DETAIL   PD  WITH (NOLOCK) ON L.PR_DETAIL_ID       = PD.PR_DETAIL_ID",
            "LEFT JOIN dbo.DM_PR_DETAIL   PD2 WITH (NOLOCK) ON L.PR_DETAIL_ID_CONTRA= PD2.PR_DETAIL_ID",
            "LEFT JOIN dbo.DM_EXPENSE     E   WITH (NOLOCK) ON L.EXPENSE_ID         = E.EXPENSE_ID",
            "LEFT JOIN dbo.DM_EXPENSE     E2  WITH (NOLOCK) ON L.EXPENSE_ID_CONTRA  = E2.EXPENSE_ID",
            "LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON L.ORGANIZATION_ID    = O.ORGANIZATION_ID",
            "LEFT JOIN dbo.DM_ITEM        I   WITH (NOLOCK) ON L.ITEM_ID            = I.ITEM_ID",
            "LEFT JOIN dbo.DM_ITEM        I2  WITH (NOLOCK) ON L.ITEM_ID_CONTRA     = I2.ITEM_ID",
            "LEFT JOIN dbo.DM_JOB         J   WITH (NOLOCK) ON L.JOB_ID             = J.JOB_ID",
            "LEFT JOIN dbo.DM_JOB         J2  WITH (NOLOCK) ON L.JOB_ID_CONTRA      = J2.JOB_ID",
            "LEFT JOIN dbo.DM_ITEM        P   WITH (NOLOCK) ON L.PRODUCT_ID         = P.ITEM_ID",
            "LEFT JOIN dbo.DM_BANK        B   WITH (NOLOCK) ON L.BANK_ID            = B.BANK_ID",
            "LEFT JOIN dbo.DM_BANK        B2  WITH (NOLOCK) ON L.BANK_ID_CONTRA     = B2.BANK_ID",
        ]
        jt = " ".join(joins)
        join_filter = " AND ".join(join_clauses) if join_clauses else "1=1"
        sql = f"SELECT {BASE_COLS} {jt} WHERE {where_sql} AND {join_filter} ORDER BY {order_by_sql}"

        def transform(raw, _cols):
            (tran_date, tran_no, tran_id, tran_name,
             acc, acc_contra, desc, comments, dc, amount,
             pr_id, pr_name, pr_id_contra, pr_name_contra,
             exp_id, exp_name, exp_id_contra, exp_name_contra,
             org_id, org_name,
             item_id, item_name, item_id_contra, item_name_contra,
             job_id, job_name, job_id_contra, job_name_contra,
             prod_id, prod_name,
             bank_id, bank_name, bank_id_contra, bank_name_contra) = raw
            debit  = float(amount) if dc == 'DEB' and amount is not None else ''
            credit = float(amount) if dc == 'CRD' and amount is not None else ''
            return [
                tran_date, tran_no, tran_id, tran_name or '',
                acc, acc_contra,
                desc or comments or '',
                debit, credit,
                pr_id or '', pr_name or '',
                pr_id_contra or '', pr_name_contra or '',
                exp_id or '', exp_name or '',
                exp_id_contra or '', exp_name_contra or '',
                org_id or '', org_name or '',
                item_id or '', item_name or '',
                item_id_contra or '', item_name_contra or '',
                job_id or '', job_name or '',
                job_id_contra or '', job_name_contra or '',
                prod_id or '', prod_name or '',
                bank_id or '', bank_name or '',
                bank_id_contra or '', bank_name_contra or '',
            ]

        headers = [label for _, label in LEDGER_CSV_COLS]
        fname   = f"ChungTuTongHop_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params + join_params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- PURCHASE count + stream csv ---
PURCHASE_CSV_COLS = [
    ("ORGANIZATION_ID","Mã đơn vị"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("TRAN_ID","Mã chứng từ"), ("TRAN_NO","Số chứng từ"), ("TRAN_DATE","Ngày chứng từ"),
    ("VAT_TRAN_NO","Số hóa đơn"), ("VAT_TRAN_DATE","Ngày hóa đơn"), ("PO_TRAN_NO","Số PO"),
    ("WAREHOUSE_ID","Mã kho"), ("WAREHOUSE_NAME","Tên kho"),
    ("ITEM_ID","Mã hàng hóa"), ("DESCRIPTION","Diễn giải"),
    ("UNIT_ID","Đơn vị tính"), ("QUANTITY","Số lượng"),
    ("UNIT_ID_WH","ĐVT kho"), ("QUANTITY_WH","SL kho"),
    ("UNIT_PRICE","Đơn giá"), ("DISCOUNT_AMOUNT","Giảm giá"), ("PURCHASE_COST","Chi phí"),
    ("VAT_TAX_RATE","Thuế suất"), ("VAT_TAX_AMOUNT","Tiền thuế VAT"), ("TOTAL_AMOUNT","Tổng tiền"),
    ("ACCOUNT_ID_COST","TK kho"),
    ("PR_DETAIL_ID","Mã đối tượng"), ("PR_DETAIL_NAME","Tên đối tượng"),
    ("EXPENSE_ID","Mã MCP"), ("EXPENSE_NAME","Tên MCP"),
    ("JOB_ID","Mã công việc"), ("JOB_NAME","Tên công việc"),
]


@app.route("/api/purchase/count")
@with_db_lock
def get_purchase_count():
    try:
        where_sql, params = _build_purchase_where(request.args)
        JOIN_SQL = """
            FROM dbo.PURCHASE_VIEW P WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON P.ORGANIZATION_ID = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_EXPENSE      E WITH (NOLOCK) ON P.EXPENSE_ID      = E.EXPENSE_ID
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) {JOIN_SQL} WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/purchase/stream_csv", methods=["POST", "GET"])
def get_purchase_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params = _build_purchase_where(args)
        order_by_sql = _resolve_order_by(args, PURCHASE_SORT_WHITELIST, "P.TRAN_DATE DESC, P.TRAN_NO")

        col_list = ", ".join(f"P.{c}" for c in PURCHASE_BASE_COLUMNS)
        JOIN_SQL = """
            FROM dbo.PURCHASE_VIEW P WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON P.ORGANIZATION_ID = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_EXPENSE      E WITH (NOLOCK) ON P.EXPENSE_ID      = E.EXPENSE_ID
        """
        SELECT_LIST = f"{col_list}, O.ORGANIZATION_NAME AS ORGANIZATION_NAME, E.EXPENSE_NAME AS EXPENSE_NAME"
        sql = f"SELECT {SELECT_LIST} {JOIN_SQL} WHERE {where_sql} ORDER BY {order_by_sql}"

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            return [d.get(key) for key, _ in PURCHASE_CSV_COLS]

        headers = [label for _, label in PURCHASE_CSV_COLS]
        fname   = f"PhieuNhapKho_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- WAREHOUSE count + stream csv ---
WAREHOUSE_CSV_COLS = [
    ("ISSUE_RECEIVE","N/X"),
    ("ORGANIZATION_ID","Mã đơn vị"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("TRAN_ID","Mã chứng từ"), ("TRAN_NO","Số chứng từ"), ("TRAN_DATE","Ngày chứng từ"),
    ("WAREHOUSE_ID","Mã kho"), ("WAREHOUSE_NAME","Tên kho"),
    ("WAREHOUSE_ID_ISSUE","Mã kho xuất"), ("WAREHOUSE_NAME_ISSUE","Tên kho xuất"),
    ("ITEM_ID","Mã hàng hóa"), ("ITEM_NAME","Tên hàng hóa"),
    ("UNIT_ID_WH","ĐVT"), ("QUANTITY","Số lượng"),
    ("UNIT_ID_EXTRA","ĐVT quy đổi"), ("QUANTITY_EXTRA","SL quy đổi"),
    ("UNIT_PRICE","Đơn giá"), ("AMOUNT","Thành tiền"),
    ("ACCOUNT_ID","Tài khoản"), ("ACCOUNT_ID_CONTRA","TK đối ứng"),
    ("PR_DETAIL_ID","Mã đối tượng"), ("PR_DETAIL_NAME","Tên đối tượng"),
    ("EXPENSE_ID","Mã MCP"), ("EXPENSE_NAME","Tên MCP"),
    ("JOB_ID","Mã công việc"), ("JOB_NAME","Tên công việc"),
]


@app.route("/api/warehouse/count")
@with_db_lock
def get_warehouse_count():
    try:
        where_sql, params = _build_warehouse_where(request.args)
        JOIN_SQL = """
            FROM dbo.WAREHOUSE_VIEW W WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON W.ORGANIZATION_ID    = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_WAREHOUSE    WI WITH (NOLOCK) ON W.WAREHOUSE_ID_ISSUE = WI.WAREHOUSE_ID
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) {JOIN_SQL} WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/warehouse/stream_csv", methods=["POST", "GET"])
def get_warehouse_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params = _build_warehouse_where(args)
        order_by_sql = _resolve_order_by(args, WAREHOUSE_SORT_WHITELIST, "W.TRAN_DATE DESC, W.TRAN_NO")

        select_parts = [f"W.{c}" for c in WAREHOUSE_BASE_COLUMNS]
        select_parts.append("O.ORGANIZATION_NAME AS ORGANIZATION_NAME")
        select_parts.append("WI.WAREHOUSE_NAME AS WAREHOUSE_NAME_ISSUE")
        SELECT_LIST = ", ".join(select_parts)
        JOIN_SQL = """
            FROM dbo.WAREHOUSE_VIEW W WITH (NOLOCK)
            LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON W.ORGANIZATION_ID    = O.ORGANIZATION_ID
            LEFT JOIN dbo.DM_WAREHOUSE    WI WITH (NOLOCK) ON W.WAREHOUSE_ID_ISSUE = WI.WAREHOUSE_ID
        """
        sql = f"SELECT {SELECT_LIST} {JOIN_SQL} WHERE {where_sql} ORDER BY {order_by_sql}"

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            return [d.get(key) for key, _ in WAREHOUSE_CSV_COLS]

        headers = [label for _, label in WAREHOUSE_CSV_COLS]
        fname   = f"ChungTuKho_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============== WAREHOUSE_BALANCE_ACTUAL (Danh sách tồn kho thực tế) ===============
# Bảng số dư tồn kho theo (Đơn vị x Kho x Mặt hàng) TẠI TỪNG NGÀY (TRAN_DATE = ngày snapshot,
# KHÔNG phải ngày phát sinh giao dịch — không có TRAN_NO/TRAN_ID vì đây không phải chứng từ).
# AMOUNT/UNIT_PRICE/QUANTITY_EXTRA/JOB_ID/PACKAGE/BARCODE/ACCOUNT_ID_ADJUST luôn rỗng/=0 ở DB
# CHULONG nên KHÔNG đưa vào SELECT. QUANTITY_ADJ/UNIT_ID_ADJ = số lượng/đơn vị đóng gói GỐC
# trước quy đổi ra đơn vị theo dõi tồn kho (VD 68 BICH quy đổi = 34000 G) — hiển thị "SL nguyên"/
# "ĐVT nguyên". Không lọc IS_APPROVED — hiển thị nguyên trạng cả 0 và 1.
WAREHOUSE_BALANCE_BASE_COLUMNS = [
    "TRAN_DATE", "ORGANIZATION_ID", "WAREHOUSE_ID", "ITEM_ID",
    "QUANTITY", "QUANTITY_ADJ", "UNIT_ID_ADJ", "USER_ID", "ACCOUNT_ID", "IS_APPROVED",
]

WAREHOUSE_BALANCE_SORT_WHITELIST = {col: f"WBA.{col}" for col in WAREHOUSE_BALANCE_BASE_COLUMNS}
WAREHOUSE_BALANCE_SORT_WHITELIST["ORGANIZATION_NAME"] = "O.ORGANIZATION_NAME"
WAREHOUSE_BALANCE_SORT_WHITELIST["WAREHOUSE_NAME"]    = "WH.WAREHOUSE_NAME"
WAREHOUSE_BALANCE_SORT_WHITELIST["ITEM_NAME"]         = "I.ITEM_NAME"
WAREHOUSE_BALANCE_SORT_WHITELIST["UNIT_ID"]           = "I.UNIT_ID"

WAREHOUSE_BALANCE_CSV_COLS = [
    ("TRAN_DATE", "Ngày"),
    ("ORGANIZATION_ID", "Mã ĐV"), ("ORGANIZATION_NAME", "Tên đơn vị"),
    ("WAREHOUSE_ID", "Mã kho"), ("WAREHOUSE_NAME", "Tên kho"),
    ("ITEM_ID", "Mã hàng"), ("ITEM_NAME", "Tên hàng"), ("UNIT_ID", "ĐVT"),
    ("QUANTITY", "Số lượng"),
    ("QUANTITY_ADJ", "SL nguyên"), ("UNIT_ID_ADJ", "ĐVT nguyên"),
    ("USER_ID", "Người thực hiện"), ("ACCOUNT_ID", "Tài khoản"),
    ("IS_APPROVED", "Đã duyệt"),
]

_WBA_JOIN_SQL = """
    FROM dbo.WAREHOUSE_BALANCE_ACTUAL WBA WITH (NOLOCK)
    LEFT JOIN dbo.DM_ORGANIZATION O  WITH (NOLOCK) ON WBA.ORGANIZATION_ID = O.ORGANIZATION_ID
    LEFT JOIN dbo.DM_WAREHOUSE    WH WITH (NOLOCK) ON WBA.WAREHOUSE_ID    = WH.WAREHOUSE_ID
    LEFT JOIN dbo.DM_ITEM         I  WITH (NOLOCK) ON WBA.ITEM_ID         = I.ITEM_ID
"""


def _warehouse_balance_select_list():
    parts = [f"WBA.{c}" for c in WAREHOUSE_BALANCE_BASE_COLUMNS]
    parts.append("O.ORGANIZATION_NAME AS ORGANIZATION_NAME")
    parts.append("WH.WAREHOUSE_NAME AS WAREHOUSE_NAME")
    parts.append("I.ITEM_NAME AS ITEM_NAME")
    parts.append("I.UNIT_ID AS UNIT_ID")
    return ", ".join(parts)


def _build_warehouse_balance_where(request_args):
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    clauses = ["WBA.TRAN_DATE >= ?", "WBA.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    for field, arg in [
        ("WBA.ORGANIZATION_ID", "org_ids"),
        ("WBA.WAREHOUSE_ID",    "wh_ids"),
        ("WBA.ITEM_ID",         "item_ids"),
        ("WBA.ACCOUNT_ID",      "acc_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    for field, arg in [
        ("WBA.ORGANIZATION_ID", "s_org_id"),
        ("WBA.WAREHOUSE_ID",    "s_wh_id"),
        ("WBA.ITEM_ID",         "s_item_id"),
        ("WBA.USER_ID",         "s_user_id"),
        ("WBA.ACCOUNT_ID",      "s_acc_id"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    for field, arg in [
        ("O.ORGANIZATION_NAME", "s_org_name"),
        ("WH.WAREHOUSE_NAME",   "s_wh_name"),
        ("I.ITEM_NAME",         "s_item_name"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    return " AND ".join(clauses), params


@app.route("/api/warehouse_balance")
@with_db_lock
def get_warehouse_balance():
    try:
        page      = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 100))
        export_all  = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        skip_count  = page > 1 and known_total is not None and not export_all

        where_sql, params = _build_warehouse_balance_where(request.args)
        order_by_sql = _resolve_order_by(
            request.args, WAREHOUSE_BALANCE_SORT_WHITELIST,
            "WBA.TRAN_DATE DESC, WBA.WAREHOUSE_ID, WBA.ITEM_ID"
        )
        SELECT_LIST = _warehouse_balance_select_list()

        conn = get_connection()
        cursor = conn.cursor()

        if export_all:
            sql = f"SELECT {SELECT_LIST} {_WBA_JOIN_SQL} WHERE {where_sql} ORDER BY {order_by_sql}"
            cursor.execute(sql, params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
        else:
            if skip_count:
                total_rows = int(known_total)
            else:
                cursor.execute(f"SELECT COUNT(*) {_WBA_JOIN_SQL} WHERE {where_sql}", params)
                total_rows = cursor.fetchone()[0] or 0

            offset = (page - 1) * page_size
            sql = f"""
                SELECT * FROM (
                    SELECT {SELECT_LIST},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {_WBA_JOIN_SQL}
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            cursor.execute(sql, params + [offset, offset + page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        rows = []
        for raw in raw_rows:
            r = dict(zip(columns, raw))
            v = r.get("TRAN_DATE")
            if isinstance(v, (date, datetime)):
                r["TRAN_DATE"] = v.strftime("%d/%m/%Y")
            for nk in ("QUANTITY", "QUANTITY_ADJ"):
                v = r.get(nk)
                if v is not None:
                    try: r[nk] = float(v)
                    except: pass
            rows.append(r)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows": total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            }
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/warehouse_balance/count")
@with_db_lock
def get_warehouse_balance_count():
    try:
        where_sql, params = _build_warehouse_balance_where(request.args)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) {_WBA_JOIN_SQL} WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/warehouse_balance/stream_csv", methods=["POST", "GET"])
def get_warehouse_balance_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params = _build_warehouse_balance_where(args)
        order_by_sql = _resolve_order_by(
            args, WAREHOUSE_BALANCE_SORT_WHITELIST,
            "WBA.TRAN_DATE DESC, WBA.WAREHOUSE_ID, WBA.ITEM_ID"
        )
        SELECT_LIST = _warehouse_balance_select_list()
        sql = f"SELECT {SELECT_LIST} {_WBA_JOIN_SQL} WHERE {where_sql} ORDER BY {order_by_sql}"

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            return [d.get(key) for key, _ in WAREHOUSE_BALANCE_CSV_COLS]

        headers = [label for _, label in WAREHOUSE_BALANCE_CSV_COLS]
        fname   = f"TonKhoThucTe_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============== SALE_VIEW (Danh sách chứng từ bán hàng) ===============
# Nguồn dbo.SALE_VIEW (152 cột, mức dòng hàng). ITEM_NAME/JOB_NAME/PR_DETAIL_NAME
# đã có sẵn trong view; ORGANIZATION_NAME/EXPENSE_NAME lấy qua JOIN như Purchase.
SALE_BASE_COLUMNS = [
    "ORGANIZATION_ID",
    "TRAN_ID", "TRAN_NO", "TRAN_DATE",
    "VAT_TRAN_NO", "VAT_TRAN_DATE", "VAT_TRAN_SERIE",
    "PR_DETAIL_ID", "PR_DETAIL_NAME",
    "CONTACT_PERSON", "ADDRESS", "TAX_FILE_NUMBER", "PHONE",
    "WAREHOUSE_ID", "EMPLOYEE_ID",
    "ITEM_ID", "ITEM_NAME", "DESCRIPTION", "UNIT_ID",
    "QUANTITY", "UNIT_PRICE", "AMOUNT",
    "DISCOUNT_AMOUNT", "VAT_TAX_RATE", "VAT_TAX_AMOUNT",
    "TOTAL_AMOUNT", "COG_AMOUNT",
    "ACCOUNT_ID", "ACCOUNT_ID_PR", "ACCOUNT_ID_INCOME", "ACCOUNT_ID_VAT", "ACCOUNT_ID_COST",
    "EXPENSE_ID", "JOB_ID", "JOB_NAME", "IS_RETURN", "STATUS",
]

# Cột phụ trên SALE_VIEW — chỉ đưa vào SELECT nếu THỰC SỰ tồn tại (guard qua INFORMATION_SCHEMA,
# tránh bẫy "SELECT cột không có → crash + ngắt pool"). PAYMENT_METHOD_NAME/EXTRA_NAME_2 KHÔNG nằm
# trong SALE_VIEW → map tên ở Python từ DM_PAYMENT_METHOD / DM_EXTRA_2.
SALE_EXTRA_COLUMNS = ["PAYMENT_METHOD_ID", "EXTRA_ID_2", "INCOME_AMOUNT", "VAT_INCOME_AMOUNT", "COMMENTS"]

SALE_SORT_WHITELIST = {col: f"S.{col}" for col in SALE_BASE_COLUMNS}
SALE_SORT_WHITELIST["ORGANIZATION_NAME"] = "O.ORGANIZATION_NAME"
SALE_SORT_WHITELIST["EXPENSE_NAME"]      = "E.EXPENSE_NAME"


def _build_sale_where(request_args):
    """WHERE + params cho dbo.SALE_VIEW. Dùng alias S. Trả (where_sql, params)."""
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    clauses = ["S.TRAN_DATE >= ?", "S.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    for field, arg in [
        ("S.TRAN_ID",        "tran_ids"),
        ("S.ORGANIZATION_ID", "org_ids"),
        ("S.JOB_ID",         "job_ids"),
        ("S.ITEM_ID",        "item_ids"),
        ("S.EXPENSE_ID",     "expense_ids"),
        ("S.PR_DETAIL_ID",   "pr_detail_ids"),
        ("S.WAREHOUSE_ID",   "wh_ids"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    # Lọc hàng bán trả lại (IS_RETURN): '1' chỉ hàng trả, '0' chỉ bán thường
    ret = request_args.get("is_return", "").strip()
    if ret in ("0", "1"):
        clauses.append("ISNULL(S.IS_RETURN,0) = ?")
        params.append(int(ret))

    # ID prefix LIKE (SARGable)
    for field, arg in [
        ("S.TRAN_NO",        "tran_no"),
        ("S.TRAN_ID",        "s_tran_id"),
        ("S.ORGANIZATION_ID", "s_org_id"),
        ("S.WAREHOUSE_ID",   "s_wh_id"),
        ("S.ITEM_ID",        "s_item_id"),
        ("S.VAT_TRAN_NO",    "s_inv_no"),
        ("S.EXPENSE_ID",     "s_exp_id"),
        ("S.JOB_ID",         "s_job_id"),
        ("S.ACCOUNT_ID",     "s_acc_id"),
        ("S.PR_DETAIL_ID",   "s_pr_id"),
        ("S.UNIT_ID",        "s_unit_id"),
        ("S.EMPLOYEE_ID",    "s_emp_id"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    # text contains LIKE
    for field, arg in [
        ("S.DESCRIPTION",      "s_desc"),
        ("S.ITEM_NAME",        "s_item_name"),
        ("O.ORGANIZATION_NAME", "s_org_name"),
        ("E.EXPENSE_NAME",     "s_exp_name"),
        ("S.JOB_NAME",         "s_job_name"),
        ("S.PR_DETAIL_NAME",   "s_pr_name"),
        ("S.CONTACT_PERSON",   "s_contact"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    # Search ngày VAT_TRAN_DATE — dd/mm/yyyy
    vd = request_args.get("s_vat_date", "").strip()
    if vd:
        try:
            parts = [p for p in vd.split('/') if p]
            if len(parts) == 3:
                dd, mm, yy = int(parts[0]), int(parts[1]), int(parts[2])
                if yy < 100: yy += 2000
                clauses.append("S.VAT_TRAN_DATE = ?")
                params.append(f"{yy:04d}{mm:02d}{dd:02d}")
            else:
                clauses.append("CONVERT(VARCHAR(10), S.VAT_TRAN_DATE, 103) LIKE ?")
                params.append(f"%{vd}%")
        except Exception:
            clauses.append("CONVERT(VARCHAR(10), S.VAT_TRAN_DATE, 103) LIKE ?")
            params.append(f"%{vd}%")

    return " AND ".join(clauses), params


SALE_JOIN_SQL = """
    FROM dbo.SALE_VIEW S WITH (NOLOCK)
    LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON S.ORGANIZATION_ID = O.ORGANIZATION_ID
    LEFT JOIN dbo.DM_EXPENSE      E WITH (NOLOCK) ON S.EXPENSE_ID      = E.EXPENSE_ID
"""
SALE_SELECT_LIST = (", ".join(f"S.{c}" for c in SALE_BASE_COLUMNS)
                    + ", O.ORGANIZATION_NAME AS ORGANIZATION_NAME, E.EXPENSE_NAME AS EXPENSE_NAME")
# Fast path: chỉ đọc SALE_VIEW, KHÔNG join DM_ORGANIZATION/DM_EXPENSE (join nặng trên view lớn).
# Tên đơn vị/MCP được map từ _meta_cache ở Python. Chỉ join khi người dùng thực sự
# search/sort theo TÊN đơn vị hoặc TÊN MCP.
SALE_FROM_ONLY   = "FROM dbo.SALE_VIEW S WITH (NOLOCK)"
SALE_BASE_SELECT = ", ".join(f"S.{c}" for c in SALE_BASE_COLUMNS)
SALE_NUM_COLS  = ("QUANTITY", "UNIT_PRICE", "AMOUNT", "DISCOUNT_AMOUNT",
                  "VAT_TAX_RATE", "VAT_TAX_AMOUNT", "TOTAL_AMOUNT", "COG_AMOUNT",
                  "INCOME_AMOUNT", "VAT_INCOME_AMOUNT")
SALE_DATE_COLS = ("TRAN_DATE", "VAT_TRAN_DATE")


def _sale_needs_join(args):
    """Chỉ cần JOIN DM khi WHERE/ORDER tham chiếu cột TÊN đơn vị/MCP."""
    ob = (args.get("order_by", "") or "").strip()
    return bool((args.get("s_org_name", "") or "").strip()
                or (args.get("s_exp_name", "") or "").strip()) or ob in ("ORGANIZATION_NAME", "EXPENSE_NAME")


def _sale_name_maps():
    """Map ID → tên cho đơn vị / MCP / kho / ĐVT, lấy từ _meta_cache (tránh JOIN)."""
    db_name = session.get('db_config', {}).get('database', 'N/A')
    meta = _meta_cache.get(db_name) or {}
    org_map  = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('orgs', [])}
    exp_map  = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('expenses', [])}
    wh_map   = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('warehouses', [])}
    unit_map = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('units', [])}
    return org_map, exp_map, wh_map, unit_map


# Cache theo DB: cột thực có của SALE_VIEW + map tên HTTT / nguồn đơn (extra_2).
_sale_dim_cache = {}


def _sale_dim_info():
    """Trả {'cols': set(tên cột SALE_VIEW in HOA), 'pay': {id:tên HTTT}, 'extra2': {id:tên nguồn}}.
    Introspect 1 lần rồi cache theo DB. Nếu KHÔNG đọc được schema → 'cols' rỗng → KHÔNG thêm cột phụ
    (an toàn: thà thiếu cột còn hơn crash pool). DM_PAYMENT_METHOD/DM_EXTRA_2 bọc try riêng."""
    db = session.get('db_config', {}).get('database', 'N/A')
    info = _sale_dim_cache.get(db)
    if info is not None:
        return info
    cols, pay_map, extra2_map = set(), {}, {}
    try:
        cur = get_connection().cursor()
        try:
            cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SALE_VIEW'")
            cols = {(r[0] or '').upper() for r in cur.fetchall()}
        except Exception:
            cols = set()
        try:
            cur.execute("SELECT CAST(PAYMENT_METHOD_ID AS NVARCHAR(100)), PAYMENT_METHOD_NAME FROM dbo.DM_PAYMENT_METHOD WITH (NOLOCK)")
            pay_map = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
        except Exception:
            pay_map = {}
        try:
            cur.execute("SELECT CAST(EXTRA_ID_2 AS NVARCHAR(100)), EXTRA_NAME_2 FROM dbo.DM_EXTRA_2 WITH (NOLOCK)")
            extra2_map = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
        except Exception:
            extra2_map = {}
    except Exception:
        pass
    info = {"cols": cols, "pay": pay_map, "extra2": extra2_map}
    _sale_dim_cache[db] = info
    return info


def _sale_extra_cols(dim):
    """Danh sách cột phụ THỰC SỰ có trong SALE_VIEW (theo introspect)."""
    return [c for c in SALE_EXTRA_COLUMNS if c.upper() in dim["cols"]]


def _sale_select_list(need_join, extra_cols):
    base = ", ".join(f"S.{c}" for c in (SALE_BASE_COLUMNS + extra_cols))
    if need_join:
        return base + ", O.ORGANIZATION_NAME AS ORGANIZATION_NAME, E.EXPENSE_NAME AS EXPENSE_NAME"
    return base


@app.route("/api/sale")
@with_db_lock
def get_sale():
    """Danh sách chứng từ bán hàng lấy từ dbo.SALE_VIEW (mức dòng hàng)."""
    try:
        page      = int(request.args.get("page",     1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

        where_sql, params = _build_sale_where(request.args)
        order_by_sql = _resolve_order_by(request.args, SALE_SORT_WHITELIST, "S.TRAN_DATE DESC, S.TRAN_NO")

        # Fast path: bỏ JOIN DM nếu không search/sort theo tên (map tên ở Python).
        need_join   = _sale_needs_join(request.args)
        join_sql    = SALE_JOIN_SQL if need_join else SALE_FROM_ONLY
        dim         = _sale_dim_info()
        extra_cols  = _sale_extra_cols(dim)
        select_list = _sale_select_list(need_join, extra_cols)

        conn   = get_connection()
        cursor = conn.cursor()

        SUM_SQL = """
            SUM(ISNULL(S.QUANTITY,0))        AS S_QUANTITY,
            SUM(ISNULL(S.AMOUNT,0))          AS S_AMOUNT,
            SUM(ISNULL(S.DISCOUNT_AMOUNT,0)) AS S_DISCOUNT,
            SUM(ISNULL(S.VAT_TAX_AMOUNT,0))  AS S_VAT_TAX,
            SUM(ISNULL(S.TOTAL_AMOUNT,0))    AS S_TOTAL,
            SUM(ISNULL(S.COG_AMOUNT,0))      AS S_COG
        """

        if export_all:
            sql = f"SELECT {select_list} {join_sql} WHERE {where_sql} ORDER BY {order_by_sql} OPTION (RECOMPILE)"
            cursor.execute(sql, params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            qi = {c: idx for idx, c in enumerate(columns)}
            summary = {"quantity": 0, "amount": 0, "discount": 0, "vat_tax": 0, "total": 0, "cog": 0}
            for r in raw_rows:
                summary["quantity"] += float(r[qi.get("QUANTITY")]        or 0) if "QUANTITY"        in qi else 0
                summary["amount"]   += float(r[qi.get("AMOUNT")]          or 0) if "AMOUNT"          in qi else 0
                summary["discount"] += float(r[qi.get("DISCOUNT_AMOUNT")] or 0) if "DISCOUNT_AMOUNT" in qi else 0
                summary["vat_tax"]  += float(r[qi.get("VAT_TAX_AMOUNT")]  or 0) if "VAT_TAX_AMOUNT"  in qi else 0
                summary["total"]    += float(r[qi.get("TOTAL_AMOUNT")]    or 0) if "TOTAL_AMOUNT"    in qi else 0
                summary["cog"]      += float(r[qi.get("COG_AMOUNT")]      or 0) if "COG_AMOUNT"      in qi else 0
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"quantity":0,"amount":0,"discount":0,"vat_tax":0,"total":0,"cog":0}
            else:
                cursor.execute(f"SELECT COUNT(*), {SUM_SQL} {join_sql} WHERE {where_sql} OPTION (RECOMPILE)", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {
                    "quantity": float(row[1] or 0),
                    "amount":   float(row[2] or 0),
                    "discount": float(row[3] or 0),
                    "vat_tax":  float(row[4] or 0),
                    "total":    float(row[5] or 0),
                    "cog":      float(row[6] or 0),
                }

            offset = (page - 1) * page_size
            sql = f"""
                SELECT * FROM (
                    SELECT {select_list},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {join_sql}
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
                OPTION (RECOMPILE)
            """
            cursor.execute(sql, params + [offset, offset + page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        db_name = session.get('db_config', {}).get('database', 'N/A')
        meta = _meta_cache.get(db_name) or {}
        tran_map = { (it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', []) }
        org_map, exp_map, wh_map, unit_map = _sale_name_maps()

        rows = []
        for raw in raw_rows:
            r = dict(zip(columns, raw))
            if 'TRAN_NAME' not in r:
                r['TRAN_NAME'] = tran_map.get((str(r.get('TRAN_ID') or '')).strip(), '')
            if not need_join:   # tên đơn vị/MCP map từ meta thay cho JOIN
                r['ORGANIZATION_NAME'] = org_map.get((str(r.get('ORGANIZATION_ID') or '')).strip(), '')
                r['EXPENSE_NAME']      = exp_map.get((str(r.get('EXPENSE_ID') or '')).strip(), '')
            # Tên kho + tên ĐVT luôn map từ meta (không có trong SALE_VIEW)
            r['WAREHOUSE_NAME'] = wh_map.get((str(r.get('WAREHOUSE_ID') or '')).strip(), '')
            r['UNIT_NAME']      = unit_map.get((str(r.get('UNIT_ID') or '')).strip(), '')
            # Tên HTTT + tên nguồn đơn (extra_2) map từ DM_PAYMENT_METHOD / DM_EXTRA_2
            r['PAYMENT_METHOD_NAME'] = dim["pay"].get((str(r.get('PAYMENT_METHOD_ID') or '')).strip(), '')
            r['EXTRA_NAME_2']        = dim["extra2"].get((str(r.get('EXTRA_ID_2') or '')).strip(), '')
            for dk in SALE_DATE_COLS:
                v = r.get(dk)
                if isinstance(v, (date, datetime)):
                    r[dk] = v.strftime("%d/%m/%Y")
            for nk in SALE_NUM_COLS:
                v = r.get(nk)
                if v is not None:
                    try: r[nk] = float(v)
                    except: pass
            rows.append(r)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows":  total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            },
            "summary": summary
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


SALE_CSV_COLS = [
    ("ORGANIZATION_ID","Mã đơn vị"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("TRAN_ID","Mã chứng từ"), ("TRAN_NO","Số chứng từ"), ("TRAN_DATE","Ngày chứng từ"),
    ("VAT_TRAN_NO","Số hóa đơn"), ("VAT_TRAN_DATE","Ngày hóa đơn"), ("VAT_TRAN_SERIE","Ký hiệu HĐ"),
    ("PR_DETAIL_ID","Mã đối tượng"), ("PR_DETAIL_NAME","Tên đối tượng"),
    ("CONTACT_PERSON","Người liên hệ"), ("ADDRESS","Địa chỉ"),
    ("TAX_FILE_NUMBER","Mã số thuế"), ("PHONE","Điện thoại"),
    ("WAREHOUSE_ID","Mã kho"), ("WAREHOUSE_NAME","Tên kho"), ("EMPLOYEE_ID","Mã NV"),
    ("ITEM_ID","Mã hàng hóa"), ("ITEM_NAME","Tên hàng hóa"),
    ("DESCRIPTION","Diễn giải"), ("UNIT_ID","ĐVT"), ("UNIT_NAME","Tên đơn vị tính"),
    ("QUANTITY","Số lượng"), ("UNIT_PRICE","Đơn giá"), ("AMOUNT","Thành tiền"),
    ("DISCOUNT_AMOUNT","Giảm giá"), ("VAT_TAX_RATE","Thuế suất"), ("VAT_TAX_AMOUNT","Tiền thuế VAT"),
    ("TOTAL_AMOUNT","Tổng thanh toán"), ("COG_AMOUNT","Giá vốn"),
    ("ACCOUNT_ID","Tài khoản"), ("ACCOUNT_ID_PR","Tài khoản công nợ"), ("ACCOUNT_ID_COST","TK kho"), ("ACCOUNT_ID_INCOME","TK doanh thu"), ("ACCOUNT_ID_VAT","TK thuế"),
    ("EXPENSE_ID","Mã MCP"), ("EXPENSE_NAME","Tên MCP"),
    ("JOB_ID","Mã công việc"), ("JOB_NAME","Tên công việc"),
    ("IS_RETURN","Hàng trả"), ("STATUS","Trạng thái"),
    ("PAYMENT_METHOD_ID","Mã HTTT"), ("PAYMENT_METHOD_NAME","Hình thức thanh toán"),
    ("EXTRA_ID_2","Mã nguồn đơn"), ("EXTRA_NAME_2","Nguồn đơn"),
    ("INCOME_AMOUNT","Doanh thu"), ("VAT_INCOME_AMOUNT","Thuế doanh thu"),
    ("COMMENTS","Ghi chú"),
]


@app.route("/api/sale/count")
@with_db_lock
def get_sale_count():
    try:
        where_sql, params = _build_sale_where(request.args)
        join_sql = SALE_JOIN_SQL if _sale_needs_join(request.args) else SALE_FROM_ONLY
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) {join_sql} WHERE {where_sql} OPTION (RECOMPILE)", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/sale/stream_csv", methods=["POST", "GET"])
def get_sale_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params = _build_sale_where(args)
        order_by_sql = _resolve_order_by(args, SALE_SORT_WHITELIST, "S.TRAN_DATE DESC, S.TRAN_NO")
        need_join = _sale_needs_join(args)
        org_map, exp_map, wh_map, unit_map = _sale_name_maps()
        dim = _sale_dim_info()
        extra_cols = _sale_extra_cols(dim)
        join_from = SALE_JOIN_SQL if need_join else SALE_FROM_ONLY
        sql = f"SELECT {_sale_select_list(need_join, extra_cols)} {join_from} WHERE {where_sql} ORDER BY {order_by_sql} OPTION (RECOMPILE)"

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            if not need_join:
                d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
                d['EXPENSE_NAME']      = exp_map.get((str(d.get('EXPENSE_ID') or '')).strip(), '')
            d['WAREHOUSE_NAME'] = wh_map.get((str(d.get('WAREHOUSE_ID') or '')).strip(), '')
            d['UNIT_NAME']      = unit_map.get((str(d.get('UNIT_ID') or '')).strip(), '')
            d['PAYMENT_METHOD_NAME'] = dim["pay"].get((str(d.get('PAYMENT_METHOD_ID') or '')).strip(), '')
            d['EXTRA_NAME_2']        = dim["extra2"].get((str(d.get('EXTRA_ID_2') or '')).strip(), '')
            return [d.get(key) for key, _ in SALE_CSV_COLS]

        headers = [label for _, label in SALE_CSV_COLS]
        fname   = f"ChungTuBanHang_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# DANH SÁCH CHỨNG TỪ TIỀN — query BẢNG GỐC VOUCHER ⋈ VOUCHER_DETAIL (alias H/D),
# map tên đối tượng + ngân hàng từ DM_PR_DETAIL ở Python.
# (KHÔNG dùng VOUCHER_VIEW: sort qua 2 join DM_PR_DETAIL trên view = ~390s cho 10k dòng;
#  query base + OFFSET/FETCH = ~1.7s.)
# ============================================================
VOUCHER_H_COLS = ["ORGANIZATION_ID", "TRAN_ID", "TRAN_NO", "TRAN_DATE", "CONTACT_PERSON", "ADDRESS", "STATUS"]
VOUCHER_D_COLS = ["ACCOUNT_ID_DEBIT", "ACCOUNT_ID_CREDIT", "DESCRIPTION", "AMOUNT",
                  "PR_DETAIL_ID_DEBIT", "PR_DETAIL_ID_CREDIT", "EXPENSE_ID_DEBIT", "EXPENSE_ID_CREDIT",
                  "JOB_ID_DEBIT", "JOB_ID_CREDIT", "REFERENCE_NO", "EMPLOYEE_ID", "CURRENCY_ID"]
VOUCHER_SELECT = (", ".join(f"H.{c}" for c in VOUCHER_H_COLS) + ", " + ", ".join(f"D.{c}" for c in VOUCHER_D_COLS))
VOUCHER_FROM   = ("FROM dbo.VOUCHER H WITH (NOLOCK) "
                  "INNER JOIN dbo.VOUCHER_DETAIL D WITH (NOLOCK) ON H.PR_KEY = D.FR_KEY")
VOUCHER_SORT_WHITELIST = {
    "ORGANIZATION_ID": "H.ORGANIZATION_ID", "TRAN_ID": "H.TRAN_ID", "TRAN_NO": "H.TRAN_NO",
    "TRAN_DATE": "H.TRAN_DATE", "STATUS": "H.STATUS", "CONTACT_PERSON": "H.CONTACT_PERSON",
    "ACCOUNT_ID_DEBIT": "D.ACCOUNT_ID_DEBIT", "ACCOUNT_ID_CREDIT": "D.ACCOUNT_ID_CREDIT",
    "AMOUNT": "D.AMOUNT", "DESCRIPTION": "D.DESCRIPTION", "EMPLOYEE_ID": "D.EMPLOYEE_ID",
    "REFERENCE_NO": "D.REFERENCE_NO",
}
VOUCHER_NUM_COLS  = ("AMOUNT",)
VOUCHER_DATE_COLS = ("TRAN_DATE",)


def _build_voucher_where(request_args):
    """WHERE + params cho VOUCHER (alias H) ⋈ VOUCHER_DETAIL (alias D)."""
    f_date = request_args.get("from_date", "01/01/2026")
    t_date = request_args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()
    clauses = ["H.TRAN_DATE >= ?", "H.TRAN_DATE <= ?"]
    params  = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]

    for field, arg in [("H.TRAN_ID", "tran_ids"), ("H.ORGANIZATION_ID", "org_ids")]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    for arg, field_debit, field_credit in [
        ("acc_ids", "D.ACCOUNT_ID_DEBIT", "D.ACCOUNT_ID_CREDIT"),
        ("pr_detail_ids", "D.PR_DETAIL_ID_DEBIT", "D.PR_DETAIL_ID_CREDIT"),
        ("expense_ids", "D.EXPENSE_ID_DEBIT", "D.EXPENSE_ID_CREDIT"),
        ("job_ids", "D.JOB_ID_DEBIT", "D.JOB_ID_CREDIT"),
    ]:
        raw = request_args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            if arg == "acc_ids":
                # For acc_ids, we do a LIKE search for each value on both DEBIT and CREDIT
                clauses.append("(" + " OR ".join(f"{field_debit} LIKE ? OR {field_credit} LIKE ?" for _ in vals) + ")")
                for v in vals:
                    params.extend([f"{v}%", f"{v}%"])
            else:
                # For others, we do an IN search on both DEBIT and CREDIT
                qs = ','.join(['?']*len(vals))
                clauses.append(f"({field_debit} IN ({qs}) OR {field_credit} IN ({qs}))")
                params.extend(vals)
                params.extend(vals)

    for field, arg in [
        ("H.TRAN_NO", "tran_no"), ("H.TRAN_ID", "s_tran_id"), ("H.ORGANIZATION_ID", "s_org_id"),
        ("D.ACCOUNT_ID_DEBIT", "s_acc_debit"), ("D.ACCOUNT_ID_CREDIT", "s_acc_credit"),
        ("D.EMPLOYEE_ID", "s_emp_id"), ("D.REFERENCE_NO", "s_ref"),
        ("D.PR_DETAIL_ID_DEBIT", "s_pr_id_debit"), ("D.PR_DETAIL_ID_CREDIT", "s_pr_id_credit"),
        ("D.EXPENSE_ID_DEBIT", "s_exp_debit"), ("D.EXPENSE_ID_CREDIT", "s_exp_credit"),
        ("D.JOB_ID_DEBIT", "s_job_debit"), ("D.JOB_ID_CREDIT", "s_job_credit"),
        ("D.CURRENCY_ID", "s_currency"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?"); params.append(f"{val}%")

    for field, arg in [("D.DESCRIPTION", "s_desc"), ("H.CONTACT_PERSON", "s_contact"), ("H.ADDRESS", "s_address")]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?"); params.append(f"%{val}%")

    return " AND ".join(clauses), params


def _voucher_prdetail_map(cursor):
    """PR_DETAIL_ID -> (TÊN, BANK_NAME, BANK_ACCOUNT) từ DM_PR_DETAIL (~945 dòng, tức thì)."""
    try:
        cursor.execute("SELECT PR_DETAIL_ID, PR_DETAIL_NAME, BANK_NAME, BANK_ACCOUNT FROM dbo.DM_PR_DETAIL WITH (NOLOCK)")
        return {(r[0] or "").strip(): ((r[1] or ""), (r[2] or ""), (r[3] or "")) for r in cursor.fetchall()}
    except Exception:
        return {}


def _voucher_enrich(rows_dicts, cursor):
    """Bổ sung tên đơn vị / tên chứng từ / tên+bank đối tượng Nợ/Có."""
    db_name = session.get('db_config', {}).get('database', 'N/A')
    meta = _meta_cache.get(db_name) or {}
    org_map  = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('orgs', [])}
    tran_map = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', [])}
    pr_map   = _voucher_prdetail_map(cursor)
    for r in rows_dicts:
        r['ORGANIZATION_NAME'] = org_map.get((str(r.get('ORGANIZATION_ID') or '')).strip(), '')
        r['TRAN_NAME']         = tran_map.get((str(r.get('TRAN_ID') or '')).strip(), '')
        pd = pr_map.get((str(r.get('PR_DETAIL_ID_DEBIT') or '')).strip())
        r['PR_DETAIL_NAME_DEBIT'], r['BANK_NAME_DEBIT'], r['BANK_ACCOUNT_DEBIT'] = pd if pd else ('', '', '')
        pc = pr_map.get((str(r.get('PR_DETAIL_ID_CREDIT') or '')).strip())
        r['PR_DETAIL_NAME_CREDIT'], r['BANK_NAME_CREDIT'], r['BANK_ACCOUNT_CREDIT'] = pc if pc else ('', '', '')
        for dk in VOUCHER_DATE_COLS:
            v = r.get(dk)
            if isinstance(v, (date, datetime)): r[dk] = v.strftime("%d/%m/%Y")
        for nk in VOUCHER_NUM_COLS:
            v = r.get(nk)
            if v is not None:
                try: r[nk] = float(v)
                except: pass
    return rows_dicts


# ======================================================================
# DOANH THU CHỜ PHÂN BỔ (INCOME_ALLOCATION) — xem theo mốc "as-of" cuối kỳ
# ----------------------------------------------------------------------
# INCOME_ALLOCATION        : mỗi dòng = 1 khoản doanh thu trả trước cần phân bổ
# INCOME_ALLOCATION_DETAIL : lịch phân bổ theo kỳ (FR_KEY -> INCOME_ALLOCATION.PR_KEY)
#   • Dthu kỳ này = SUM(AMOUNT) các kỳ chi tiết GIAO với [from_date, to_date]
#   • Lũy kế      = SUM(AMOUNT) các kỳ chi tiết có DAY_END <= to_date (cộng dồn tới hết kỳ)
#   • Còn lại     = INCOME_AMOUNT - Lũy kế
# Không dùng bảng _TAM (chỉ là bảng tạm nghiệp vụ).
# ======================================================================

INCOME_ALLOC_COLUMNS = [
    "PR_KEY", "TRAN_ID", "TRAN_DATE", "TRAN_NO", "DESCRIPTION", "ITEM_ID", "QUANTITY",
    "INCOME_AMOUNT", "ALLOCATION_METHOD", "ALLOCATION_RATE", "ACCOUNT_ID", "ACCOUNT_ID_CONTRA",
    "ACCOUNT_ID_DES", "PR_DETAIL_ID", "EXPENSE_ID", "JOB_ID", "ORGANIZATION_ID", "ACTIVE",
    "COMMENTS", "USE_DATE", "RECEIVE_DATE",
]
INCOME_ALLOC_SORT_WHITELIST = {c: f"A.{c}" for c in INCOME_ALLOC_COLUMNS}
INCOME_ALLOC_SORT_WHITELIST.update({
    "PERIOD_AMT": "ISNULL(D.PERIOD_AMT,0)",
    "CUM_AMT":    "ISNULL(D.CUM_AMT,0)",
    "CON_LAI":    "(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0))",
})
INCOME_ALLOC_NUM_COLS  = ("QUANTITY", "INCOME_AMOUNT", "ALLOCATION_RATE", "PERIOD_AMT", "CUM_AMT", "CON_LAI")
INCOME_ALLOC_DATE_COLS = ("TRAN_DATE", "USE_DATE", "RECEIVE_DATE")
ALLOC_METHOD_MAP = {"0": "Tháng", "1": "Ngày", "2": "Quý", "3": "Năm", "4": "Tuần"}

_income_alloc_cols_cache = {}


def _income_alloc_cols():
    """Cột THỰC CÓ của `dbo.INCOME_ALLOCATION` trên DB đang kết nối.

    ⚠️ Studio chạy trên DB của nhiều khách, mỗi nơi một cấu trúc. `IACC_CHULONG` KHÔNG có cột
    `RECEIVE_DATE` (bảng chỉ 24 cột, chỉ có `USE_DATE`) → SELECT thẳng là crash 500 + ngắt
    connection pool, tab chết hoàn toàn. Dò `INFORMATION_SCHEMA` rồi chỉ lấy cột thực có.
    Dò không được thì giữ nguyên danh sách cũ để không đổi hành vi trên DB đang chạy tốt.
    """
    db = (session.get('db_config') or {}).get('database', '')
    if db in _income_alloc_cols_cache:
        return _income_alloc_cols_cache[db]
    try:
        cur = get_connection().cursor()
        cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = 'INCOME_ALLOCATION'")
        have = {(r[0] or '').strip().upper() for r in cur.fetchall()}
        cols = [c for c in INCOME_ALLOC_COLUMNS if c.upper() in have] or list(INCOME_ALLOC_COLUMNS)
        thieu = [c for c in INCOME_ALLOC_COLUMNS if c.upper() not in have]
        if thieu:
            logger.warning("INCOME_ALLOCATION thieu cot %s tren DB %s — da bo khoi SELECT.", thieu, db)
    except Exception:
        cols = list(INCOME_ALLOC_COLUMNS)
    _income_alloc_cols_cache[db] = cols
    return cols


def _income_alloc_select_list():
    """SELECT list dựng theo đúng cột thực có (xem `_income_alloc_cols`)."""
    return (", ".join(f"A.{c}" for c in _income_alloc_cols()) + """,
    ISNULL(D.PERIOD_AMT,0) AS PERIOD_AMT,
    ISNULL(D.CUM_AMT,0)    AS CUM_AMT,
    (A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0)) AS CON_LAI""")


def _income_alloc_sort_whitelist():
    """Whitelist sắp xếp — cũng phải bỏ cột không tồn tại, nếu không người dùng bấm sort
    lên đúng cột đó là `ORDER BY A.RECEIVE_DATE` → crash 500 dù SELECT đã tránh được."""
    have = set(_income_alloc_cols())
    wl = {c: f"A.{c}" for c in INCOME_ALLOC_COLUMNS if c in have}
    wl.update({
        "PERIOD_AMT": "ISNULL(D.PERIOD_AMT,0)",
        "CUM_AMT":    "ISNULL(D.CUM_AMT,0)",
        "CON_LAI":    "(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0))",
    })
    return wl


INCOME_ALLOC_FROM = "FROM dbo.INCOME_ALLOCATION A WITH (NOLOCK) LEFT JOIN D ON D.FR_KEY = A.PR_KEY"


def _income_alloc_cte(from_dt, to_dt):
    """CTE D tổng hợp chi tiết phân bổ + 3 tham số ngày (thứ tự khớp SQL text)."""
    d_sql = """
        WITH D AS (
            SELECT FR_KEY,
                   SUM(CASE WHEN DAY_START <= ? AND DAY_END >= ? THEN AMOUNT ELSE 0 END) AS PERIOD_AMT,
                   SUM(CASE WHEN DAY_END <= ? THEN AMOUNT ELSE 0 END) AS CUM_AMT
            FROM dbo.INCOME_ALLOCATION_DETAIL WITH (NOLOCK)
            GROUP BY FR_KEY
        )
    """
    d_params = [to_dt.strftime("%Y%m%d"), from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]
    return d_sql, d_params


def _build_income_alloc_where(args):
    """WHERE + params cho INCOME_ALLOCATION (alias A, có ref D.CUM_AMT). Trả (where_sql, params, from_dt, to_dt)."""
    f_date = args.get("from_date", "01/01/2026")
    t_date = args.get("to_date",  "31/12/2026")
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

    # Chỉ lấy chứng từ phát sinh tới hết ngày cuối kỳ (as-of)
    clauses = ["A.TRAN_DATE <= ?"]
    params  = [to_dt.strftime("%Y%m%d")]

    # Trạng thái ACTIVE: '1' đang hiệu lực, '0' ngừng, '' = tất cả
    active = args.get("active", "").strip()
    if active in ("0", "1"):
        clauses.append("A.ACTIVE = ?")
        params.append(int(active))

    # Trạng thái phân bổ: 'remaining' (còn giá trị) | 'done' (đã hết) | '' (tất cả). Mặc định 'remaining'.
    alloc_status = args.get("alloc_status", "remaining").strip()
    if alloc_status == "remaining":
        clauses.append("(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0)) > 0")
    elif alloc_status == "done":
        clauses.append("(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0)) <= 0")

    for field, arg in [
        ("A.TRAN_ID",         "tran_ids"),
        ("A.ORGANIZATION_ID", "org_ids"),
        ("A.JOB_ID",          "job_ids"),
        ("A.ITEM_ID",         "item_ids"),
        ("A.EXPENSE_ID",      "expense_ids"),
        ("A.PR_DETAIL_ID",    "pr_detail_ids"),
        ("A.ACCOUNT_ID_DES",  "acc_des_ids"),
    ]:
        raw = args.get(arg, "")
        vals = [v for v in raw.split(",") if v]
        if vals:
            clauses.append(f"{field} IN ({','.join(['?']*len(vals))})")
            params.extend(vals)

    # ID prefix LIKE (SARGable)
    for field, arg in [
        ("A.TRAN_NO",         "tran_no"),
        ("A.TRAN_NO",         "s_tran_no"),
        ("A.TRAN_ID",         "s_tran_id"),
        ("A.ORGANIZATION_ID", "s_org_id"),
        ("A.ITEM_ID",         "s_item_id"),
        ("A.ACCOUNT_ID",      "s_acc_id"),
        ("A.ACCOUNT_ID_DES",  "s_acc_des"),
        ("A.ACCOUNT_ID_CONTRA", "s_acc_contra"),
        ("A.PR_DETAIL_ID",    "s_pr_id"),
        ("A.JOB_ID",          "s_job_id"),
        ("A.EXPENSE_ID",      "s_exp_id"),
    ]:
        val = args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    # text contains LIKE
    for field, arg in [
        ("A.DESCRIPTION", "s_desc"),
        ("A.COMMENTS",    "s_comment"),
    ]:
        val = args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    return " AND ".join(clauses), params, from_dt, to_dt


def _income_alloc_name_maps():
    """Map ID → tên cho đơn vị / hàng hóa / công việc / đối tượng / mục chi phí / chứng từ (từ _meta_cache)."""
    db_name = session.get('db_config', {}).get('database', 'N/A')
    meta = _meta_cache.get(db_name) or {}
    def mp(key):
        return {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get(key, [])}
    return mp('orgs'), mp('items'), mp('jobs'), mp('pr_details'), mp('expenses'), mp('tran_ids')


def _income_alloc_enrich(rows, columns_present=True):
    """Bổ sung tên + format ngày/số cho danh sách dict INCOME_ALLOCATION."""
    org_map, item_map, job_map, pr_map, exp_map, tran_map = _income_alloc_name_maps()
    out = []
    for r in rows:
        r['ORGANIZATION_NAME'] = org_map.get((str(r.get('ORGANIZATION_ID') or '')).strip(), '')
        r['ITEM_NAME']         = item_map.get((str(r.get('ITEM_ID') or '')).strip(), '')
        r['JOB_NAME']          = job_map.get((str(r.get('JOB_ID') or '')).strip(), '')
        r['PR_DETAIL_NAME']    = pr_map.get((str(r.get('PR_DETAIL_ID') or '')).strip(), '')
        r['EXPENSE_NAME']      = exp_map.get((str(r.get('EXPENSE_ID') or '')).strip(), '')
        r['TRAN_NAME']         = tran_map.get((str(r.get('TRAN_ID') or '')).strip(), '')
        r['ALLOCATION_METHOD_NAME'] = ALLOC_METHOD_MAP.get(str(r.get('ALLOCATION_METHOD') or '').strip(),
                                                           str(r.get('ALLOCATION_METHOD') or ''))
        for dk in INCOME_ALLOC_DATE_COLS:
            v = r.get(dk)
            if isinstance(v, (date, datetime)):
                r[dk] = v.strftime("%d/%m/%Y")
        for nk in INCOME_ALLOC_NUM_COLS:
            v = r.get(nk)
            if v is not None:
                try: r[nk] = float(v)
                except: pass
        r.pop('RowNum', None)
        out.append(r)
    return out


@app.route("/api/income_alloc")
@with_db_lock
def get_income_alloc():
    """Danh sách doanh thu chờ phân bổ — INCOME_ALLOCATION as-of cuối kỳ (Dthu kỳ này / Lũy kế / Còn lại)."""
    try:
        page      = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

        where_sql, w_params, from_dt, to_dt = _build_income_alloc_where(request.args)
        d_sql, d_params = _income_alloc_cte(from_dt, to_dt)
        order_by_sql = _resolve_order_by(request.args, _income_alloc_sort_whitelist(), "A.TRAN_DATE DESC, A.TRAN_NO")

        conn = get_connection()
        cursor = conn.cursor()
        empty_sum = {"income_amount": 0, "period_amt": 0, "cum_amt": 0, "con_lai": 0, "quantity": 0}

        if export_all:
            sql = f"{d_sql} SELECT {_income_alloc_select_list()} {INCOME_ALLOC_FROM} WHERE {where_sql} ORDER BY {order_by_sql}"
            cursor.execute(sql, d_params + w_params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            qi = {c: i for i, c in enumerate(columns)}
            summary = dict(empty_sum)
            for r in raw_rows:
                summary["income_amount"] += float(r[qi["INCOME_AMOUNT"]] or 0)
                summary["period_amt"]    += float(r[qi["PERIOD_AMT"]]    or 0)
                summary["cum_amt"]       += float(r[qi["CUM_AMT"]]       or 0)
                summary["con_lai"]       += float(r[qi["CON_LAI"]]       or 0)
                summary["quantity"]      += float(r[qi["QUANTITY"]]      or 0)
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = dict(empty_sum)
            else:
                cnt_sql = f"""{d_sql}
                    SELECT COUNT(*),
                           SUM(A.INCOME_AMOUNT),
                           SUM(ISNULL(D.PERIOD_AMT,0)),
                           SUM(ISNULL(D.CUM_AMT,0)),
                           SUM(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0)),
                           SUM(A.QUANTITY)
                    {INCOME_ALLOC_FROM} WHERE {where_sql}"""
                cursor.execute(cnt_sql, d_params + w_params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {
                    "income_amount": float(row[1] or 0),
                    "period_amt":    float(row[2] or 0),
                    "cum_amt":       float(row[3] or 0),
                    "con_lai":       float(row[4] or 0),
                    "quantity":      float(row[5] or 0),
                }

            offset = (page - 1) * page_size
            sql = f"""{d_sql}
                SELECT * FROM (
                    SELECT {_income_alloc_select_list()},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {INCOME_ALLOC_FROM}
                    WHERE {where_sql}
                ) AS T
                WHERE RowNum > ? AND RowNum <= ?"""
            cursor.execute(sql, d_params + w_params + [offset, offset + page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        rows = _income_alloc_enrich([dict(zip(columns, raw)) for raw in raw_rows])

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows":  total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            },
            "summary": summary
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/income_alloc/count")
@with_db_lock
def get_income_alloc_count():
    try:
        where_sql, w_params, from_dt, to_dt = _build_income_alloc_where(request.args)
        d_sql, d_params = _income_alloc_cte(from_dt, to_dt)
        conn = get_connection()
        cursor = conn.cursor()
        sql = f"{d_sql} SELECT COUNT(*) {INCOME_ALLOC_FROM} WHERE {where_sql}"
        cursor.execute(sql, d_params + w_params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# Cột xuất CSV — thứ tự/nhãn khớp INCOME_ALLOC_EXPORT_COLS ở index.html (mode "mỗi đơn vị 1 sheet")
INCOME_ALLOC_CSV_COLS = [
    ("ORGANIZATION_ID","Đơn vị"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("TRAN_ID","Mã CT"), ("TRAN_NAME","Tên chứng từ"), ("TRAN_NO","Số CT"), ("TRAN_DATE","Ngày CT"),
    ("USE_DATE","Ngày phân bổ"), ("RECEIVE_DATE","Ngày nhận"),
    ("DESCRIPTION","Diễn giải"), ("ITEM_ID","Hàng hóa"), ("ITEM_NAME","Tên hàng hóa"), ("QUANTITY","Số lượng"),
    ("ALLOCATION_RATE","Tỷ lệ pb"), ("ALLOCATION_METHOD_NAME","Tiêu thức pb"),
    ("INCOME_AMOUNT","Doanh thu"), ("PERIOD_AMT","Dthu kỳ này"), ("CUM_AMT","Lũy kế"), ("CON_LAI","Còn lại"),
    ("ACCOUNT_ID_DES","Tk đích"), ("ACCOUNT_ID","TK"), ("ACCOUNT_ID_CONTRA","Tk đối ứng"),
    ("PR_DETAIL_ID","Mã đối tượng"), ("PR_DETAIL_NAME","Tên đối tượng"),
    ("JOB_ID","Công việc"), ("EXPENSE_ID","Mục chi phí"),
    ("ACTIVE","Active"), ("COMMENTS","Ghi chú"),
]


@app.route("/api/income_alloc/stream_csv", methods=["POST", "GET"])
def get_income_alloc_stream_csv():
    """Tạo job ghi CSV vào disk + trả job_id để poll progress (giống 5 danh sách còn lại)."""
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, w_params, from_dt, to_dt = _build_income_alloc_where(args)
        d_sql, d_params = _income_alloc_cte(from_dt, to_dt)
        order_by_sql = _resolve_order_by(args, _income_alloc_sort_whitelist(), "A.TRAN_DATE DESC, A.TRAN_NO")
        sql = f"{d_sql} SELECT {_income_alloc_select_list()} {INCOME_ALLOC_FROM} WHERE {where_sql} ORDER BY {order_by_sql}"

        # Map tên chuẩn bị sẵn (1 lần) — transform chạy ở thread nền nên KHÔNG được đụng session/DB
        org_map, item_map, job_map, pr_map, exp_map, tran_map = _income_alloc_name_maps()

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
            d['ITEM_NAME']         = item_map.get((str(d.get('ITEM_ID') or '')).strip(), '')
            d['PR_DETAIL_NAME']    = pr_map.get((str(d.get('PR_DETAIL_ID') or '')).strip(), '')
            d['TRAN_NAME']         = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            d['ALLOCATION_METHOD_NAME'] = ALLOC_METHOD_MAP.get(str(d.get('ALLOCATION_METHOD') or '').strip(),
                                                               str(d.get('ALLOCATION_METHOD') or ''))
            return [d.get(key) for key, _ in INCOME_ALLOC_CSV_COLS]

        headers = [label for _, label in INCOME_ALLOC_CSV_COLS]
        fname   = f"DoanhThuChoPhanBo_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, d_params + w_params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/voucher")
@with_db_lock
def get_voucher():
    """Danh sách chứng từ tiền/kế toán (phiếu thu/chi, báo nợ/có...) từ VOUCHER ⋈ VOUCHER_DETAIL."""
    try:
        page      = int(request.args.get("page",     1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

        where_sql, params = _build_voucher_where(request.args)
        order_by_sql = _resolve_order_by(request.args, VOUCHER_SORT_WHITELIST, "H.TRAN_DATE DESC, H.TRAN_NO")

        cursor = get_connection().cursor()

        if export_all:
            cursor.execute(f"SELECT {VOUCHER_SELECT} {VOUCHER_FROM} WHERE {where_sql} ORDER BY {order_by_sql}", params)
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            qi = {c: idx for idx, c in enumerate(columns)}
            summary = {"amount": sum(float(r[qi["AMOUNT"]] or 0) for r in raw_rows) if "AMOUNT" in qi else 0}
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"amount": 0}
            else:
                cursor.execute(f"SELECT COUNT(*), SUM(ISNULL(D.AMOUNT,0)) {VOUCHER_FROM} WHERE {where_sql}", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {"amount": float(row[1] or 0)}

            offset = (page - 1) * page_size
            cursor.execute(
                f"SELECT {VOUCHER_SELECT} {VOUCHER_FROM} WHERE {where_sql} ORDER BY {order_by_sql} "
                f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", params + [offset, page_size])
            columns  = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        rows = _voucher_enrich([dict(zip(columns, raw)) for raw in raw_rows], cursor)

        return jsonify({
            "status": "ok",
            "data": rows,
            "pagination": {
                "total_rows":  total_rows,
                "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                "page": page if not export_all else 1
            },
            "summary": summary
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


VOUCHER_CSV_COLS = [
    ("ORGANIZATION_ID","Mã đơn vị"), ("ORGANIZATION_NAME","Tên đơn vị"),
    ("TRAN_ID","Mã chứng từ"), ("TRAN_NAME","Tên chứng từ"), ("TRAN_NO","Số chứng từ"), ("TRAN_DATE","Ngày chứng từ"),
    ("ACCOUNT_ID_DEBIT","Tài khoản"), ("ACCOUNT_ID_CREDIT","Tài khoản đối ứng"),
    ("DESCRIPTION","Diễn giải"), ("AMOUNT","Số tiền"),
    ("PR_DETAIL_ID_DEBIT","Mã Đối tượng"), ("PR_DETAIL_NAME_DEBIT","Đối tượng"),
    ("PR_DETAIL_ID_CREDIT","Mã ĐT đối ứng"), ("PR_DETAIL_NAME_CREDIT","Đối tượng đối ứng"),
    ("EXPENSE_ID_DEBIT","Mục chi phí"), ("EXPENSE_ID_CREDIT","MCP đối ứng"),
    ("JOB_ID_DEBIT","Công việc"), ("JOB_ID_CREDIT","CV đối ứng"),
    ("BANK_NAME_DEBIT","Ngân hàng"), ("BANK_ACCOUNT_DEBIT","TK Ngân hàng"),
    ("BANK_NAME_CREDIT","Ngân hàng đối ứng"), ("BANK_ACCOUNT_CREDIT","TKNH đối ứng"),
    ("CONTACT_PERSON","Người nộp/nhận"), ("ADDRESS","Địa chỉ"), ("REFERENCE_NO","Số tham chiếu"),
    ("EMPLOYEE_ID","Mã NV"), ("CURRENCY_ID","Tiền tệ"), ("STATUS","Trạng thái"),
]


@app.route("/api/voucher/count")
@with_db_lock
def get_voucher_count():
    try:
        where_sql, params = _build_voucher_where(request.args)
        cursor = get_connection().cursor()
        cursor.execute(f"SELECT COUNT(*) {VOUCHER_FROM} WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/voucher/stream_csv", methods=["POST", "GET"])
def get_voucher_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        where_sql, params = _build_voucher_where(args)
        order_by_sql = _resolve_order_by(args, VOUCHER_SORT_WHITELIST, "H.TRAN_DATE DESC, H.TRAN_NO")
        sql = f"SELECT {VOUCHER_SELECT} {VOUCHER_FROM} WHERE {where_sql} ORDER BY {order_by_sql}"

        # Map tên/bank chuẩn bị sẵn (chạy 1 lần) để transform per-row khỏi query DB
        db_name = session.get('db_config', {}).get('database', 'N/A')
        meta = _meta_cache.get(db_name) or {}
        org_map  = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('orgs', [])}
        tran_map = {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', [])}
        pr_map   = _voucher_prdetail_map(get_connection().cursor())

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
            d['TRAN_NAME']         = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            pd = pr_map.get((str(d.get('PR_DETAIL_ID_DEBIT') or '')).strip()) or ('', '', '')
            d['PR_DETAIL_NAME_DEBIT'], d['BANK_NAME_DEBIT'], d['BANK_ACCOUNT_DEBIT'] = pd
            pc = pr_map.get((str(d.get('PR_DETAIL_ID_CREDIT') or '')).strip()) or ('', '', '')
            d['PR_DETAIL_NAME_CREDIT'], d['BANK_NAME_CREDIT'], d['BANK_ACCOUNT_CREDIT'] = pc
            return [d.get(key) for key, _ in VOUCHER_CSV_COLS]

        headers = [label for _, label in VOUCHER_CSV_COLS]
        fname   = f"ChungTuTien_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ledger/export")
@with_db_lock
def get_ledger_export():
    """Trả toàn bộ ledger (không phân trang) cho xuất Excel — phải JOIN dimension."""
    try:
        where_sql, params, join_clauses, join_params = _build_where(request.args)

        BASE_COLS = """
            L.TRAN_DATE, L.TRAN_NO, L.TRAN_ID, L.DEBIT_CREDIT,
            L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA,
            L.PR_DETAIL_ID, L.DESCRIPTION, L.COMMENTS,
            L.AMOUNT, L.JOB_ID,
            L.ITEM_ID, L.PRODUCT_ID,
            L.EXPENSE_ID, L.ORGANIZATION_ID, L.BANK_ID, L.BANK_ID_CONTRA,
            L.EXPENSE_ID_CONTRA, L.PR_DETAIL_ID_CONTRA, L.JOB_ID_CONTRA, L.ITEM_ID_CONTRA,
            PD.PR_DETAIL_NAME, PD2.PR_DETAIL_NAME AS PR_DETAIL_NAME_CONTRA,
            E.EXPENSE_NAME, E2.EXPENSE_NAME AS EXPENSE_NAME_CONTRA,
            J.JOB_NAME, J2.JOB_NAME AS JOB_NAME_CONTRA,
            O.ORGANIZATION_NAME,
            I.ITEM_NAME, I2.ITEM_NAME AS ITEM_NAME_CONTRA,
            P.ITEM_NAME AS PRODUCT_NAME, B.BANK_NAME, B2.BANK_NAME AS BANK_NAME_CONTRA
        """
        joins = [
            "FROM dbo.LEDGER L WITH (NOLOCK)",
            "LEFT JOIN dbo.DM_PR_DETAIL   PD  WITH (NOLOCK) ON L.PR_DETAIL_ID       = PD.PR_DETAIL_ID",
            "LEFT JOIN dbo.DM_PR_DETAIL   PD2 WITH (NOLOCK) ON L.PR_DETAIL_ID_CONTRA= PD2.PR_DETAIL_ID",
            "LEFT JOIN dbo.DM_ITEM        I WITH (NOLOCK)   ON L.ITEM_ID            = I.ITEM_ID",
            "LEFT JOIN dbo.DM_ITEM        I2 WITH (NOLOCK)  ON L.ITEM_ID_CONTRA     = I2.ITEM_ID",
            "LEFT JOIN dbo.DM_ITEM        P WITH (NOLOCK)   ON L.PRODUCT_ID         = P.ITEM_ID",
            "LEFT JOIN dbo.DM_EXPENSE     E WITH (NOLOCK)   ON L.EXPENSE_ID         = E.EXPENSE_ID",
            "LEFT JOIN dbo.DM_EXPENSE     E2 WITH (NOLOCK)  ON L.EXPENSE_ID_CONTRA  = E2.EXPENSE_ID",
            "LEFT JOIN dbo.DM_JOB         J WITH (NOLOCK)   ON L.JOB_ID             = J.JOB_ID",
            "LEFT JOIN dbo.DM_JOB         J2 WITH (NOLOCK)  ON L.JOB_ID_CONTRA      = J2.JOB_ID",
            "LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK)  ON L.ORGANIZATION_ID    = O.ORGANIZATION_ID",
            "LEFT JOIN dbo.DM_BANK        B WITH (NOLOCK)   ON L.BANK_ID            = B.BANK_ID",
            "LEFT JOIN dbo.DM_BANK        B2 WITH (NOLOCK)  ON L.BANK_ID_CONTRA     = B2.BANK_ID",
        ]
        JOIN_TABLES = " ".join(joins)
        join_filter = " AND ".join(join_clauses) if join_clauses else "1=1"

        sql = f"""
            SELECT {BASE_COLS}
            {JOIN_TABLES}
            WHERE {where_sql} AND {join_filter}
            ORDER BY L.TRAN_DATE DESC, L.TRAN_NO
        """

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params + join_params)
        columns = [c[0] for c in cursor.description]
        rows = []
        for raw in cursor.fetchall():
            r = dict(zip(columns, raw))
            if isinstance(r.get('TRAN_DATE'), (date, datetime)):
                r['TRAN_DATE'] = r['TRAN_DATE'].strftime("%d/%m/%Y")
            if r.get('AMOUNT') is not None:
                try: r['AMOUNT'] = float(r['AMOUNT'])
                except: pass
            rows.append(r)

        return jsonify({"status": "ok", "data": rows, "total_rows": len(rows)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# ===== BC005 — BẢNG CÂN ĐỐI KẾ TOÁN (TT200, mẫu B01-DN) =====
def _map_account_to_cdkt(acc, bal):
    """Trả về list (code, value) — mã chỉ tiêu CDKT và giá trị đóng góp.
    bal = SUM(DEB) - SUM(CRD) của ACCOUNT_ID.
    Các tài khoản có thể đảo dấu (131, 331, 138, 334, 338...) sẽ vào chỉ tiêu Tài sản
    nếu dư Nợ, vào chỉ tiêu Nguồn vốn nếu dư Có.
    """
    a = (acc or "").strip()
    if not a or bal == 0:
        return []
    a4 = a[:4]
    a3 = a[:3]
    out = []
    # Tiền — TK mẹ 111, 112, 113 (gồm tất cả TK con: 1111, 1121, 1131...)
    if a.startswith('11'):
        out.append(('111', bal))
    elif a4 == '1281':
        out.append(('112', bal))
    elif a4 in ('1282', '1288'):
        out.append(('123', bal))
    elif a3 == '121':
        out.append(('121', bal))
    elif a4 == '2291':
        out.append(('122', bal))  # âm (dư Có → bal âm)
    elif a.startswith('1311'):
        if bal >= 0: out.append(('131', bal))
        else:        out.append(('312', -bal))
    elif a.startswith('1312'):
        if bal >= 0: out.append(('211', bal))
        else:        out.append(('312', -bal))
    elif a3 == '331':
        if bal >= 0: out.append(('132', bal))
        else:        out.append(('311', -bal))
    elif a3 == '136':
        out.append(('133', bal))
    elif a4 == '1283':
        if bal >= 0: out.append(('135', bal))
        else:        out.append(('338', -bal))
    elif a.startswith('1385') or a.startswith('1388') or a.startswith('3388'):
        if bal >= 0: out.append(('136', bal))
        else:        out.append(('319', -bal))
    elif a.startswith('141') or a.startswith('2441'):
        out.append(('136', bal))
    elif a3 == '138':
        if bal >= 0: out.append(('139', bal)) # Thường 1381 vào 139
        else:        out.append(('319', -bal))
    elif a3 == '334':
        out.append(('314', -bal))
    elif a3 == '338':
        # Các khoản 338 khác ngoài 3388 (ví dụ BHXH)
        if bal >= 0: out.append(('136', bal)) 
        else:        out.append(('319', -bal))
    elif a4 == '2293':
        out.append(('137', bal))
    elif a3 in ('151', '152', '153', '154', '155', '156', '157', '158'):
        out.append(('141', bal))
    elif a4 == '2294':
        out.append(('149', bal))
    elif a3 == '242':
        out.append(('151', bal))
    elif a3 == '133':
        out.append(('152', bal))
    elif a3 == '333':
        if bal >= 0: out.append(('153', bal))
        else:        out.append(('313', -bal))
    elif a3 == '171':
        if bal >= 0: out.append(('154', bal))
        else:        out.append(('324', -bal))
    # TSCĐ
    elif a3 == '211':
        out.append(('222', bal))
    elif a4 == '2141':
        out.append(('223', bal))  # bal âm
    elif a3 == '213':
        out.append(('228', bal))   # Nguyên giá TSCĐ vô hình (228), KHÔNG phải 227 (227 là nhóm = 228+229)
    elif a4 == '2143':
        out.append(('229', bal))   # Hao mòn TSCĐ vô hình (229)
    elif a3 == '244':
        out.append(('216', bal))   # Cầm cố, ký quỹ ký cược dài hạn → Phải thu dài hạn khác
    elif a3 == '217':
        out.append(('230', bal))
    elif a4 == '2147':
        out.append(('232', bal))
    elif a3 == '241':
        out.append(('242', bal))
    elif a3 == '221':
        out.append(('251', bal))
    elif a3 == '222':
        out.append(('252', bal))
    elif a4 == '2292':
        out.append(('254', bal))
    elif a3 == '228':
        out.append(('255', bal))
    # Nợ phải trả
    elif a.startswith('3362') or a.startswith('3363') or a.startswith('3368'):
        out.append(('316', -bal))
    elif a3 == '335':
        out.append(('315', -bal))
    elif a3 == '352':
        out.append(('321', -bal))
    elif a3 in ('353',):
        out.append(('322', -bal))
    elif a3 == '344':
        out.append(('323', -bal))
    elif a3 == '343':
        out.append(('336', -bal))
    elif a3 == '341':
        # Vay & nợ thuê tài chính — gộp dài hạn
        out.append(('338', -bal))
    elif a3 == '347':
        out.append(('341', -bal))
    elif a3 == '356':
        out.append(('343', -bal))
    # Vốn chủ sở hữu
    elif a4 == '4111':
        out.append(('411A', -bal))
        out.append(('411', -bal))
    elif a4 == '4112':
        out.append(('412', -bal))
    elif a4 == '4113':
        out.append(('411B', -bal))
        out.append(('411', -bal))
    elif a3 == '412':
        out.append(('416', -bal))
    elif a3 == '413':
        out.append(('417', -bal))
    elif a3 == '414':
        out.append(('418', -bal))
    elif a3 == '417':
        out.append(('419', -bal))
    elif a3 == '418':
        out.append(('420', -bal))
    elif a3 == '419':
        out.append(('415', bal))   # cổ phiếu quỹ ghi Nợ
    elif a.startswith('421'):
        out.append(('421', -bal))
        out.append(('421A', -bal))
    elif a3 == '441':
        out.append(('422', -bal))
    elif a3 == '461':
        out.append(('431', -bal))
    elif a3 == '466':
        out.append(('432', -bal))
    return out


def _calc_cdkt_balances(rows):
    """rows: list (account_id, balance). Trả dict {code: value}."""
    result = {}
    for acc, bal in rows:
        for code, val in _map_account_to_cdkt(acc, bal):
            result[code] = result.get(code, 0.0) + float(val)

    # Tổng hợp các chỉ tiêu nhóm
    def s(*codes):
        return sum(result.get(c, 0.0) for c in codes)

    # Tài sản ngắn hạn
    result['110'] = s('111', '112')
    result['120'] = s('121', '122', '123')
    result['130'] = s('131', '132', '133', '134', '135', '136', '137', '139')
    result['140'] = s('141', '149')
    result['150'] = s('151', '152', '153', '154', '155')
    result['100'] = s('110', '120', '130', '140', '150')
    # Tài sản dài hạn
    result['210'] = s('211', '212', '213', '214', '215', '216', '217')
    result['221'] = s('222', '223')
    result['224'] = s('225', '226')
    result['227'] = s('228', '229')
    result['220'] = s('221', '224', '227')
    result['230'] = s('231', '232')  # 231 thường rỗng, dùng raw 230 thay thế
    if not result.get('230'):
        result['230'] = result.get('230', 0.0)
    result['240'] = s('241', '242')
    result['250'] = s('251', '252', '253', '254', '255')
    result['260'] = s('261', '262', '263', '268')
    result['200'] = s('210', '220', '230', '240', '250', '260')
    # Tổng tài sản
    result['270'] = s('100', '200')
    # Nợ ngắn hạn
    result['310'] = s('311', '312', '313', '314', '315', '316', '317', '318', '319', '320', '321', '322', '323', '324')
    # Nợ dài hạn
    result['330'] = s('331', '332', '333', '334', '335', '336', '337', '338', '339', '340', '341', '342', '343')
    result['300'] = s('310', '330')
    # Vốn CSH
    if not result.get('411'):
        result['411'] = s('411A', '411B')
    result['410'] = s('411', '412', '413', '414', '415', '416', '417', '418', '419', '420', '421', '422')
    result['430'] = s('431', '432')
    result['400'] = s('410', '430')
    result['440'] = s('300', '400')
    return result


@app.route("/api/balance_sheet")
@with_db_lock
def get_balance_sheet():
    """BC005 - Bảng Cân đối Kế toán (TT200, mẫu B01-DN).

    Số dư mỗi TK (BAL = SUM(DEB) - SUM(CRD)) tính theo công thức:
      Kỳ này  = (số dư đầu năm từ BALANCE_VIEW)
                + (phát sinh từ LEDGER_VIEW với TRAN_DATE <= to_date)
      Kỳ trước = (số dư đầu năm từ BALANCE_VIEW)
                + (phát sinh từ LEDGER_VIEW với TRAN_DATE < from_date)
    """
    try:
        f_date  = request.args.get("from_date")
        t_date  = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        # Trước đây để rỗng ⇒ báo cáo GỘP CẢ đơn vị ngoài cây → không tie được với nhau
        # và làm Bảng cân đối kế toán không cân (đã trả giá ở LedgerReport 15/08/2026).
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        cur = get_connection().cursor()

        # Thêm biến ngày đầu năm để tránh bị cộng dồn cả phát sinh các năm cũ
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        # 1) Số dư đầu năm từ BALANCE_VIEW (toàn bộ dòng đều là số dư đầu kỳ)
        # 1) Số dư đầu năm từ BALANCE_VIEW (toàn bộ dòng đều là số dư đầu kỳ)
        try:
            cur.execute("SELECT TOP 1 ORGANIZATION_ID FROM dbo.BALANCE_VIEW WITH (NOLOCK)")
            has_org_in_balance = True
        except Exception:
            has_org_in_balance = False

        if has_org_in_balance:
            q_open = f"""
                SELECT ACCOUNT_ID, ISNULL(PR_DETAIL_ID, ''), ISNULL(ORGANIZATION_ID, ''),
                       SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END) AS BAL
                FROM dbo.BALANCE_VIEW WITH (NOLOCK)
                WHERE TRAN_DATE = ? {org_where}
                GROUP BY ACCOUNT_ID, ISNULL(PR_DETAIL_ID, ''), ISNULL(ORGANIZATION_ID, '')
            """
            # PHẢI là org_params (khớp số dấu ? trong org_where), KHÔNG phải org_ids —
            # khi không chọn đơn vị thì org_ids rỗng nhưng org_where vẫn có NOT IN (?).
            org_params_open = [first_day_of_year] + list(org_params)
        else:
            q_open = f"""
                SELECT ACCOUNT_ID, ISNULL(PR_DETAIL_ID, ''), '' AS ORGANIZATION_ID,
                       SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END) AS BAL
                FROM dbo.BALANCE_VIEW WITH (NOLOCK)
                WHERE TRAN_DATE = ?
                GROUP BY ACCOUNT_ID, ISNULL(PR_DETAIL_ID, '')
            """
            org_params_open = [first_day_of_year]

        cur.execute(q_open, org_params_open)
        opening_year = { ((r[0] or '').strip(), (r[1] or '').strip(), (r[2] or '').strip()): float(r[3] or 0) for r in cur.fetchall() }

        # 2) Phát sinh lũy kế đến từng mốc (cuối kỳ này / trước đầu kỳ này) từ LEDGER_VIEW
        def run_ledger(end_date_inclusive=None, end_date_exclusive=None):
            where = ["L.TRAN_DATE >= ?"]
            params = [first_day_of_year]
            if end_date_inclusive is not None:
                where.append("L.TRAN_DATE <= ?")
                params.append(end_date_inclusive.strftime("%Y%m%d"))
            if end_date_exclusive is not None:
                where.append("L.TRAN_DATE < ?")
                params.append(end_date_exclusive.strftime("%Y%m%d"))
            # Truy van sinh ra so du that cua BC005 — phai loai don vi ngoai cay y nhu org_where.
            _lc, _lp = _org_filter_sql(org_ids, "L.ORGANIZATION_ID")
            if _lc:
                where.append(_lc)
                params.extend(_lp)
            q = f"""
                SELECT L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, ''), ISNULL(L.ORGANIZATION_ID, ''),
                       SUM(CASE WHEN L.DEBIT_CREDIT='DEB' THEN L.AMOUNT WHEN L.DEBIT_CREDIT='CRD' THEN -L.AMOUNT ELSE 0 END) AS BAL
                FROM dbo.LEDGER L WITH (NOLOCK)
                WHERE {' AND '.join(where)}
                GROUP BY L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, ''), ISNULL(L.ORGANIZATION_ID, '')
            """
            cur.execute(q, params)
            return { ((r[0] or '').strip(), (r[1] or '').strip(), (r[2] or '').strip()): float(r[3] or 0) for r in cur.fetchall() }

        ledger_to_end   = run_ledger(end_date_inclusive=to_dt)
        ledger_to_start = run_ledger(end_date_exclusive=from_dt)

        # 3) Cộng dồn: số dư = đầu năm + phát sinh lũy kế
        all_keys = set(opening_year) | set(ledger_to_end) | set(ledger_to_start)
        this_rows_full = [(k[0], k[1], k[2], opening_year.get(k, 0.0) + ledger_to_end.get(k, 0.0)) for k in all_keys]
        prev_rows_full = [(k[0], k[1], k[2], opening_year.get(k, 0.0) + ledger_to_start.get(k, 0.0)) for k in all_keys]

        # Roll up to (ACCOUNT_ID, PR_DETAIL_ID) for standard CDKT
        this_acc_pr = {}
        for acc, pr, org, bal in this_rows_full:
            this_acc_pr[(acc, pr)] = this_acc_pr.get((acc, pr), 0.0) + bal
        prev_acc_pr = {}
        for acc, pr, org, bal in prev_rows_full:
            prev_acc_pr[(acc, pr)] = prev_acc_pr.get((acc, pr), 0.0) + bal

        this_rows = [(acc, bal) for (acc, pr), bal in this_acc_pr.items()]
        prev_rows = [(acc, bal) for (acc, pr), bal in prev_acc_pr.items()]

        closing = _calc_cdkt_balances(this_rows)   # Kỳ này
        opening = _calc_cdkt_balances(prev_rows)   # Kỳ trước

        # Tính toán 1311 và 1312
        target_orgs = {'42', '51', '36', '65', '18', '31'}
        def calc_sub_131(rows_full, acc_pr_bals):
            # Precompute (acc,pr) -> tổng bal của các đơn vị target → O(N) thay vì O(N^2)
            # (vòng lặp cũ quét toàn bộ rows_full cho MỖI nhóm 1311 → 200s+ trên DB lớn)
            org_bal_idx = {}
            for a, p, o, bal in rows_full:
                if o in target_orgs:
                    k = (a, p)
                    org_bal_idx[k] = org_bal_idx.get(k, 0.0) + bal
            val_1311 = 0.0
            for (acc, pr), total_bal in acc_pr_bals.items():
                if acc.startswith('1311') and total_bal >= 0:
                    val_1311 += org_bal_idx.get((acc, pr), 0.0)
            return val_1311

        closing['1311'] = calc_sub_131(this_rows_full, this_acc_pr)
        closing['1312'] = closing.get('131', 0.0) - closing['1311']
        
        opening['1311'] = calc_sub_131(prev_rows_full, prev_acc_pr)
        opening['1312'] = opening.get('131', 0.0) - opening['1311']

        # --- XỬ LÝ ĐẶC BIỆT DÒNG 421A, 421B ---
        from datetime import timedelta
        closing['421A'] = opening.get('421A', 0.0)

        def get_movement_421(d_end, d_start):
            end_val = sum(v for (a, pr, org), v in d_end.items() if a.startswith('421'))
            start_val = sum(v for (a, pr, org), v in d_start.items() if a.startswith('421'))
            return -(end_val - start_val)

        closing['421B'] = get_movement_421(ledger_to_end, ledger_to_start)

        try:
            prev_m_end = from_dt.replace(day=1) - timedelta(days=1)
            prev_m_start = prev_m_end.replace(day=1)
            l_prev_m_end = run_ledger(end_date_inclusive=prev_m_end)
            l_prev_m_start = run_ledger(end_date_exclusive=prev_m_start)
            opening['421B'] = get_movement_421(l_prev_m_end, l_prev_m_start)
        except Exception:
            opening['421B'] = 0.0

        return jsonify({
            "status": "ok",
            "data": {"opening": opening, "closing": closing}
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# ===== BC006 — BẢNG CÂN ĐỐI PHÁT SINH =====
@app.route("/api/trial_balance")
@with_db_lock
def get_trial_balance():
    try:
        f_date  = request.args.get("from_date")
        t_date  = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        # Trước đây để rỗng ⇒ báo cáo GỘP CẢ đơn vị ngoài cây → không tie được với nhau
        # và làm Bảng cân đối kế toán không cân (đã trả giá ở LedgerReport 15/08/2026).
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        cur = get_connection().cursor()
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        # 1. Lấy danh mục DM_ACCOUNT
        cur.execute("SELECT ACCOUNT_ID, ACCOUNT_NAME, IS_PARENT, ACCOUNT_TYPE_ID, PARENT_ACCOUNT_ID FROM dbo.DM_ACCOUNT WITH (NOLOCK)")
        accounts = {}
        for r in cur.fetchall():
            acc_id = (r[0] or "").strip()
            db_type = (r[3] or "").strip().lower()
            
            # Ép chuẩn loại tài khoản theo Kế toán Việt Nam (nếu DB rác/thiếu)
            if acc_id.startswith(('3', '4', '5', '7', '214', '229')):
                db_type = 'crd'
            elif acc_id.startswith(('1', '2', '6', '8', '9')):
                db_type = 'deb'
            else:
                db_type = 'deb'
                
            accounts[acc_id] = {
                "name": (r[1] or "").strip(),
                "is_parent": bool(r[2]),
                "type": db_type,
                "parent_id": (r[4] or "").strip()
            }
            
        # 1.1 Kế thừa thuộc tính lưỡng tính (debcrd) từ tài khoản cha hoặc tiền tố chuẩn
        sorted_accs = sorted(accounts.keys(), key=lambda x: len(x))
        for acc_id in sorted_accs:
            # Ép kiểu cho các tài khoản lưỡng tính kinh điển nếu DB config sai
            if acc_id.startswith('131') or acc_id.startswith('331') or acc_id.startswith('1388') or acc_id.startswith('3388'):
                accounts[acc_id]["type"] = 'debcrd'
            
            parent_id = accounts[acc_id]["parent_id"]
            if not parent_id:
                for i in range(len(acc_id)-1, 0, -1):
                    prefix = acc_id[:i]
                    if prefix in accounts and accounts[prefix]["is_parent"]:
                        parent_id = prefix
                        break
            if parent_id and parent_id in accounts:
                if accounts[parent_id]["type"] == 'debcrd':
                    accounts[acc_id]["type"] = 'debcrd'

        # 2. Lấy Dư đầu kỳ (từ BALANCE_VIEW đầu năm)
        q_open = f"""
            SELECT ACCOUNT_ID, ISNULL(PR_DETAIL_ID, ''),
                   SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END) AS BAL
            FROM dbo.BALANCE_VIEW WITH (NOLOCK)
            WHERE TRAN_DATE = ? {org_where}
            GROUP BY ACCOUNT_ID, ISNULL(PR_DETAIL_ID, '')
        """
        # PHẢI là org_params (khớp số dấu ? trong org_where), KHÔNG phải org_ids —
        # khi không chọn đơn vị thì org_ids rỗng nhưng org_where vẫn có NOT IN (?).
        org_params_open = [first_day_of_year] + list(org_params)
        cur.execute(q_open, org_params_open)
        opening_year = { ((r[0] or '').strip(), (r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall() }

        # Lũy kế từ đầu năm tới trước from_dt (nếu có)
        ledger_to_start = {}
        if from_dt > date(from_dt.year, 1, 1):
            where_start = ["L.TRAN_DATE >= ?", "L.TRAN_DATE < ?"]
            params_start = [first_day_of_year, from_dt.strftime("%Y%m%d")]
            _lc, _lp = _org_filter_sql(org_ids, "L.ORGANIZATION_ID")
            if _lc:
                where_start.append(_lc)
                params_start.extend(_lp)
            q_ledger_start = f"""
                SELECT L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, ''),
                       SUM(CASE WHEN L.DEBIT_CREDIT='DEB' THEN L.AMOUNT WHEN L.DEBIT_CREDIT='CRD' THEN -L.AMOUNT ELSE 0 END) AS BAL
                FROM dbo.LEDGER L WITH (NOLOCK)
                WHERE {' AND '.join(where_start)}
                GROUP BY L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, '')
            """
            cur.execute(q_ledger_start, params_start)
            ledger_to_start = { ((r[0] or '').strip(), (r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall() }

        # 3. Lấy Phát sinh trong kỳ
        where_period = ["L.TRAN_DATE >= ?", "L.TRAN_DATE <= ?"]
        params_period = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")]
        _lc2, _lp2 = _org_filter_sql(org_ids, "L.ORGANIZATION_ID")
        if _lc2:
            where_period.append(_lc2)
            params_period.extend(_lp2)
        q_period = f"""
            SELECT L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, ''),
                   SUM(CASE WHEN L.DEBIT_CREDIT='DEB' THEN L.AMOUNT ELSE 0 END) AS DEB,
                   SUM(CASE WHEN L.DEBIT_CREDIT='CRD' THEN L.AMOUNT ELSE 0 END) AS CRD
            FROM dbo.LEDGER L WITH (NOLOCK)
            WHERE {' AND '.join(where_period)}
            GROUP BY L.ACCOUNT_ID, ISNULL(L.PR_DETAIL_ID, '')
        """
        cur.execute(q_period, params_period)
        period_data = { ((r[0] or '').strip(), (r[1] or '').strip()): {"deb": float(r[2] or 0), "crd": float(r[3] or 0)} for r in cur.fetchall() }

        # 4. Tính toán Dư Nợ/Có theo Object
        all_keys = set(opening_year.keys()) | set(ledger_to_start.keys()) | set(period_data.keys())
        raw_result = {}
        for acc_id, pr_id in all_keys:
            if acc_id not in raw_result:
                raw_result[acc_id] = {"open_deb": 0, "open_crd": 0, "period_deb": 0, "period_crd": 0, "close_deb": 0, "close_crd": 0}
            
            open_bal = opening_year.get((acc_id, pr_id), 0.0) + ledger_to_start.get((acc_id, pr_id), 0.0)
            p_data = period_data.get((acc_id, pr_id), {"deb": 0, "crd": 0})
            p_deb = p_data["deb"]
            p_crd = p_data["crd"]
            close_bal = open_bal + p_deb - p_crd
            
            acc_type = accounts.get(acc_id, {"type": "deb"})["type"]
            node = raw_result[acc_id]
            node["period_deb"] += p_deb
            node["period_crd"] += p_crd
            
            if acc_type == 'debcrd':
                if open_bal > 0: node["open_deb"] += open_bal
                elif open_bal < 0: node["open_crd"] += -open_bal
                
                if close_bal > 0: node["close_deb"] += close_bal
                elif close_bal < 0: node["close_crd"] += -close_bal
            else:
                node["open_deb"] += open_bal
                node["close_deb"] += close_bal
                
        # 5. Bù trừ tài khoản thường ở cấp Account
        for acc_id, node in raw_result.items():
            acc_type = accounts.get(acc_id, {"type": "deb"})["type"]
            if acc_type == 'deb':
                net_open = node["open_deb"] - node["open_crd"]
                node["open_deb"] = net_open
                node["open_crd"] = 0
                
                net_close = node["close_deb"] - node["close_crd"]
                node["close_deb"] = net_close
                node["close_crd"] = 0
            elif acc_type == 'crd':
                net_open = node["open_crd"] - node["open_deb"]
                node["open_crd"] = net_open
                node["open_deb"] = 0
                
                net_close = node["close_crd"] - node["close_deb"]
                node["close_crd"] = net_close
                node["close_deb"] = 0

        # 6. Chuẩn bị Final Result
        final_result = {acc: {"open_deb": 0, "open_crd": 0, "period_deb": 0, "period_crd": 0, "close_deb": 0, "close_crd": 0} for acc in accounts}
        for acc in raw_result:
            if acc not in final_result:
                final_result[acc] = {"open_deb": 0, "open_crd": 0, "period_deb": 0, "period_crd": 0, "close_deb": 0, "close_crd": 0}
        
        for acc_id, node in raw_result.items():
            for k in final_result[acc_id]:
                final_result[acc_id][k] += node[k]

        # 7. Cuộn dữ liệu lên Tài khoản Cha (từ mã dài tới mã ngắn)
        sorted_accs = sorted(final_result.keys(), key=lambda x: len(x), reverse=True)
        for acc_id in sorted_accs:
            parent_id = accounts.get(acc_id, {}).get("parent_id")
            if not parent_id:
                for i in range(len(acc_id)-1, 0, -1):
                    prefix = acc_id[:i]
                    if prefix in final_result and accounts.get(prefix, {}).get("is_parent"):
                        parent_id = prefix
                        break
                        
            if parent_id and parent_id in final_result:
                for k in final_result[acc_id]:
                    final_result[parent_id][k] += final_result[acc_id][k]
                    
        # 8. Filter những tài khoản có số liệu (chỉ trả về những tài khoản != 0)
        output = []
        for acc_id, node in final_result.items():
            if any(round(v, 2) != 0 for v in node.values()):
                output.append({
                    "id": acc_id,
                    "name": accounts.get(acc_id, {}).get("name", ""),
                    "is_parent": accounts.get(acc_id, {}).get("is_parent", False),
                    **node
                })
                
        output.sort(key=lambda x: x["id"])
        
        # 9. Tính Tổng cộng (Grand Total)
        # Bằng cách lấy tổng của tất cả các LEAF nodes (tài khoản không phải parent)
        total = {"open_deb": 0, "open_crd": 0, "period_deb": 0, "period_crd": 0, "close_deb": 0, "close_crd": 0}
        for acc_id, node in raw_result.items():
            for k in total:
                total[k] += node[k]

        return jsonify({
            "status": "ok",
            "data": output,
            "total": total
        })
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/debt_summary")
@with_db_lock
def get_debt_summary():
    """BC011 — Bảng tổng hợp phát sinh công nợ: gộp theo ĐỐI TƯỢNG cho (các) tài khoản đã chọn.
    Dư đầu/cuối tính net theo TỪNG đối tượng (lưỡng tính: >0 ghi Nợ, <0 ghi Có).
    Nguồn: BALANCE_VIEW (dư đầu năm) + LEDGER (lũy kế & phát sinh) — giống trial_balance."""
    try:
        f_date  = request.args.get("from_date")
        t_date  = request.args.get("to_date")
        acc_ids = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()]
        pr_ids  = [v for v in request.args.get("pr_detail_ids", "").split(",") if v]
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

        if not acc_ids:
            return jsonify({"status": "error", "message": "Vui lòng chọn Tài khoản để xem báo cáo công nợ."}), 400

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        # Tài khoản: khớp cả tài khoản con (LIKE 'acc%')
        acc_clause = "(" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids)) + ")"
        acc_params = [a + "%" for a in acc_ids]

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_clause = (" AND " + _oc) if _oc else ""

        pr_clause, pr_params = "", []
        if pr_ids:
            pr_clause = f" AND ISNULL(PR_DETAIL_ID,'') IN ({','.join(['?']*len(pr_ids))})"
            pr_params = list(pr_ids)

        cur = get_connection().cursor()

        # Gộp theo (ĐỐI TƯỢNG, TÀI KHOẢN công nợ) — thêm cột TK vào báo cáo.
        # 1. Dư đầu năm (BALANCE_VIEW) theo đối tượng + tài khoản
        q_open = f"""
            SELECT ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,''),
                   SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END)
            FROM dbo.BALANCE_VIEW WITH (NOLOCK)
            WHERE {acc_clause} AND TRAN_DATE = ? {org_clause} {pr_clause}
            GROUP BY ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,'')
        """
        cur.execute(q_open, acc_params + [first_day_of_year] + org_params + pr_params)
        opening = {((r[0] or '').strip(), (r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall()}

        # 2. Lũy kế từ đầu năm → trước from_dt (LEDGER)
        ledger_start = {}
        if from_dt > date(from_dt.year, 1, 1):
            q_start = f"""
                SELECT ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,''),
                       SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END)
                FROM dbo.LEDGER WITH (NOLOCK)
                WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_clause} {pr_clause}
                GROUP BY ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,'')
            """
            cur.execute(q_start, acc_params + [first_day_of_year, from_dt.strftime("%Y%m%d")] + org_params + pr_params)
            ledger_start = {((r[0] or '').strip(), (r[1] or '').strip()): float(r[2] or 0) for r in cur.fetchall()}

        # 3. Phát sinh trong kỳ (LEDGER)
        q_period = f"""
            SELECT ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,''),
                   SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM dbo.LEDGER WITH (NOLOCK)
            WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_clause} {pr_clause}
            GROUP BY ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,'')
        """
        cur.execute(q_period, acc_params + [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params + pr_params)
        period = {((r[0] or '').strip(), (r[1] or '').strip()): {"deb": float(r[2] or 0), "crd": float(r[3] or 0)} for r in cur.fetchall()}

        # 4. Tên đối tượng
        pr_name = {}
        try:
            cur.execute("SELECT PR_DETAIL_ID, PR_DETAIL_NAME FROM dbo.DM_PR_DETAIL WITH (NOLOCK)")
            pr_name = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
        except Exception:
            pass

        # 5. Tổng hợp theo (đối tượng, tài khoản) — net lưỡng tính từng dòng
        keys = set(opening) | set(ledger_start) | set(period)
        rows = []
        total = {"open_deb": 0, "open_crd": 0, "period_deb": 0, "period_crd": 0, "close_deb": 0, "close_crd": 0}
        for key in keys:
            pid, acc = key
            open_bal = opening.get(key, 0.0) + ledger_start.get(key, 0.0)
            pd = period.get(key, {"deb": 0, "crd": 0})
            p_deb, p_crd = pd["deb"], pd["crd"]
            close_bal = open_bal + p_deb - p_crd
            node = {
                "open_deb":  open_bal if open_bal > 0 else 0,
                "open_crd": -open_bal if open_bal < 0 else 0,
                "period_deb": p_deb,
                "period_crd": p_crd,
                "close_deb":  close_bal if close_bal > 0 else 0,
                "close_crd": -close_bal if close_bal < 0 else 0,
            }
            if all(round(v, 2) == 0 for v in node.values()):
                continue
            for k in total:
                total[k] += node[k]
            rows.append({"id": pid, "name": pr_name.get(pid, ''), "acc": acc, "is_parent": False, **node})

        # Sắp xếp theo Tài khoản công nợ rồi tới đối tượng (giống mẫu Excel)
        rows.sort(key=lambda x: (x["acc"], x["name"], x["id"]))

        return jsonify({"status": "ok", "data": rows, "total": total})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


# ===== BC007 — SỔ NHẬT KÝ CHUNG =====

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
        
        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        # Trước đây để rỗng ⇒ báo cáo GỘP CẢ đơn vị ngoài cây → không tie được với nhau
        # và làm Bảng cân đối kế toán không cân (đã trả giá ở LedgerReport 15/08/2026).
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        cur = get_connection().cursor()
        
        if report_type == "BC007":
            title = "SỔ NHẬT KÝ CHUNG"
            sql = f"""
                SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                ORDER BY TRAN_DATE, TRAN_NO
            """
            params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
            headers = ["Ngày HT", "Số CT", "Diễn giải", "TK Nợ", "TK Có", "Phát sinh Nợ", "Phát sinh Có"]
        elif report_type == "BC008":
            title = "SỔ CHI TIẾT TÀI KHOẢN"
            sql = f"""
                SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                ORDER BY TRAN_DATE, TRAN_NO
            """
            params = [account_id, from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
            headers = ["Ngày HT", "Số CT", "Diễn giải", "TK Đối ứng", "Phát sinh Nợ", "Phát sinh Có", "Dư Nợ", "Dư Có"]
            
            open_bal_deb = 0
            open_bal_crd = 0
            first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")
            sql_open = f"""
                SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                       SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                FROM dbo.BALANCE_VIEW WITH (NOLOCK)
                WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE = ? {org_where}
            """
            cur.execute(sql_open, [account_id, first_day_of_year] + org_params)
            r_open = cur.fetchone()
            if r_open:
                open_bal_deb += float(r_open[0] or 0)
                open_bal_crd += float(r_open[1] or 0)
                
            if from_dt > date(from_dt.year, 1, 1):
                sql_lk = f"""
                    SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                           SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                    FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                    WHERE ACCOUNT_ID LIKE ? + '%' AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}
                """
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
            # Auto-fit column widths
            if report_type == 'BC007':
                ws.set_column(0, 0, 12)
                ws.set_column(1, 1, 15)
                ws.set_column(2, 2, 45)
                ws.set_column(3, 3, 12)
                ws.set_column(4, 4, 12)
                ws.set_column(5, 6, 18)
            else:
                ws.set_column(0, 0, 12)
                ws.set_column(1, 1, 15)
                ws.set_column(2, 2, 45)
                ws.set_column(3, 3, 12)
                ws.set_column(4, 5, 18)
                ws.set_column(6, 7, 18)
# Lấy tên đơn vị
            org_name = "Tất cả đơn vị"
            if org_ids:
                try:
                    org_cur = get_connection().cursor()
                    org_cur.execute("SELECT ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WHERE ORGANIZATION_ID = ?", [org_ids[0]])
                    r_org = org_cur.fetchone()
                    if r_org:
                        org_name = f"{org_ids[0]} - {r_org[0]}"
                except Exception as e:
                    org_name = f"Đơn vị: {','.join(org_ids)}"

            mso_pattern = "Mẫu S03a - DN" if report_type == "BC007" else "Mẫu S38 - DN"
            last_col = 6 if report_type == "BC007" else 7

            company_format = workbook.add_format({'bold': True, 'font_size': 11})
            pattern_format = workbook.add_format({'bold': True, 'italic': True, 'font_size': 10, 'align': 'right'})
            org_format = workbook.add_format({'bold': True, 'font_size': 9, 'font_color': '#475569'})
            title_format = workbook.add_format({'bold': True, 'font_size': 15, 'align': 'center'})
            period_format = workbook.add_format({'bold': True, 'font_size': 11, 'font_color': '#4f46e5', 'align': 'center'})

            # Lấy thông tin công ty phục vụ in ấn/báo cáo
            company_name = "CÔNG TY TNHH DUONG THANH LONG"
            try:
                company_cur = get_connection().cursor()
                company_cur.execute("""
                    SELECT VAR_NAME, VAR_VALUE FROM dbo.SYS_SYSTEMVAR WITH (NOLOCK) 
                    WHERE VAR_NAME IN ('COMPANY_NAME','PARENT_COMPANY')
                """)
                sv_comp = {r[0]: (r[1] or '').strip() for r in company_cur.fetchall()}
                val = sv_comp.get('COMPANY_NAME') or sv_comp.get('PARENT_COMPANY')
                if val:
                    company_name = val
                else:
                    # Fallback sang organization '00'
                    company_cur.execute("SELECT ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WHERE ORGANIZATION_ID = '00'")
                    r_org = company_cur.fetchone()
                    if r_org and r_org[0]:
                        company_name = r_org[0].strip()
            except Exception:
                pass

            ws.write(0, 0, company_name, company_format)
            ws.write(0, last_col, mso_pattern, pattern_format)
            ws.write(1, 0, f"Đơn vị: {org_name}", org_format)
            
            ws.merge_range(3, 0, 3, last_col, title, title_format)
            ws.merge_range(4, 0, 4, last_col, f"Từ ngày {f_date} đến {t_date}", period_format)

            start_row = 6
            if report_type == "BC008":
                ws.write(5, 0, f"Tài khoản: {account_id}", workbook.add_format({'bold': True, 'font_size': 10}))
                start_row = 7

            for col_num, col_name in enumerate(headers):
                ws.write(start_row, col_num, col_name, header_format)

            current_row = start_row + 1

            if report_type == "BC008":
                if sheet_name == list(sheets_data.keys())[0]:
                    ws.write(current_row, 2, "Số dư đầu kỳ", cell_format)
                    ws.write(current_row, 6, open_bal_deb if open_bal_deb > open_bal_crd else 0, num_format)
                    ws.write(current_row, 7, open_bal_crd if open_bal_crd > open_bal_deb else 0, num_format)
                    current_row += 1
                running_deb = open_bal_deb
                running_crd = open_bal_crd

            for r in s_rows:
                ws.write(current_row, 0, r[0], date_format)
                ws.write(current_row, 1, r[1] or "", text_format)
                ws.write(current_row, 2, r[2] or "", cell_format)
                
                if report_type == "BC007":
                    ws.write(current_row, 3, r[3] or "", text_format)
                    ws.write(current_row, 4, r[4] or "", text_format)
                    amt = float(r[6] or 0)
                    is_deb = (r[5] == 'DEB')
                    ws.write(current_row, 5, amt if is_deb else 0, num_format)
                    ws.write(current_row, 6, amt if not is_deb else 0, num_format)
                else:
                    ws.write(current_row, 3, r[3] or "", text_format)
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

            # Ghi Footer chữ ký ở cuối sheet
            current_row += 1
            from datetime import datetime as dt_class
            today = dt_class.now()
            date_str = f"TP. HCM, Ngày {today.day} Tháng {today.month} Năm {today.year}"
            
            sig_date_format = workbook.add_format({'italic': True, 'font_size': 10, 'align': 'center'})
            sig_title_format = workbook.add_format({'bold': True, 'font_size': 11, 'align': 'center'})
            sig_help_format = workbook.add_format({'italic': True, 'font_size': 9, 'font_color': '#94a3b8', 'align': 'center'})

            ws.merge_range(current_row, last_col - 2, current_row, last_col, date_str, sig_date_format)
            current_row += 1
            
            ws.merge_range(current_row, 0, current_row, 1, "NGƯỜI LẬP BIỂU", sig_title_format)
            ws.merge_range(current_row, 2, current_row, last_col - 3, "KẾ TOÁN TRƯỞNG", sig_title_format)
            ws.merge_range(current_row, last_col - 2, current_row, last_col, "GIÁM ĐỐC", sig_title_format)
            current_row += 1
            
            ws.merge_range(current_row, 0, current_row, 1, "(Ký, họ tên)", sig_help_format)
            ws.merge_range(current_row, 2, current_row, last_col - 3, "(Ký, họ tên)", sig_help_format)
            ws.merge_range(current_row, last_col - 2, current_row, last_col, "(Ký, họ tên)", sig_help_format)
            current_row += 4 # Khoảng trống ký tên
            
            ws.freeze_panes(start_row + 1, 0)
            
        workbook.close()
        output.seek(0)
        
        return send_file(output, as_attachment=True, download_name=f"{report_type}_Export.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        msg = str(e)
        logger.error(f"Error in export_excel_backend: {msg}")
        return jsonify({"status": "error", "message": msg}), 500


@app.route("/api/report_export_csv")
def report_export_csv():
    """Xuất CSV STREAMING (không giới hạn dòng) cho báo cáo nhiều dòng: BC007 (Nhật ký chung), BC008 (Sổ chi tiết).
    Dùng connection riêng + stream trực tiếp tới trình duyệt → KHÔNG giữ pool, KHÔNG nạp RAM,
    KHÔNG dính giới hạn 1.048.576 dòng của Excel (xls/xlsx). Excel/Sheets mở CSV này bình thường."""
    from flask import Response, stream_with_context
    try:
        report_type = request.args.get("report_type", "")
        mode = request.args.get("mode", "summary")   # BC007: 'summary' (như web) | 'detail' (nhật ký chung chi tiết)
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        # BC008: giữ NGUYÊN chuỗi đa chọn ('111,112') — tách/lọc bằng _acc_like_sql, KHÔNG cắt lấy mã đầu
        account_id = request.args.get("account_id", "").strip()
        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()
        db_cfg = session.get('db_config')
        if not db_cfg:
            return jsonify({"status": "error", "message": "Chưa đăng nhập SQL Server"}), 401

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        d_from = from_dt.strftime("%Y%m%d")
        d_to   = to_dt.strftime("%Y%m%d")
        first_day = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        # org filter với alias L. (LEDGER) và LV. (LEDGER_VIEW) — tránh nhập nhằng khi JOIN DM_ORGANIZATION.
        # PHẢI đi qua _org_filter_sql y như org_where ở trên: ba biến này dùng CHUNG một mảng
        # org_params, nên nếu chỗ này còn dựng theo org_ids (rỗng khi không chọn đơn vị) thì số dấu ?
        # không khớp số params → "SQL contains 2 parameter markers, but 3 parameters were supplied".
        # (Đã trả giá đúng lỗi này ở LedgerReport 15/08/2026 — xuất CSV Sổ nhật ký chung chết.)
        _lc, _lp   = _org_filter_sql(org_ids, "L.ORGANIZATION_ID")
        _lvc, _lvp = _org_filter_sql(org_ids, "LV.ORGANIZATION_ID")
        org_where_l  = (" AND " + _lc)  if _lc  else ""
        org_where_lv = (" AND " + _lvc) if _lvc else ""

        if report_type == "BC007" and mode == "detail":
            # NHẬT KÝ CHUNG CHI TIẾT — theo mẫu SQL người dùng cung cấp (bổ sung Tên đơn vị)
            headers = ["Bảng", "Mã đơn vị", "Tên đơn vị", "Công việc", "Mã chứng từ", "Ngày chứng từ",
                       "Số chứng từ", "Diễn giải", "Tài khoản", "Tài khoản đối ứng", "Mã đối tượng",
                       "Tên đối tượng", "Số tiền nợ", "Số tiền có", "Ghi chú"]
            sql = f"""SELECT 'NKC', LV.ORGANIZATION_ID, O.ORGANIZATION_NAME, LV.JOB_NAME, LV.TRAN_ID,
                             LV.TRAN_DATE, LV.TRAN_NO, LV.DESCRIPTION, LV.ACCOUNT_ID, LV.ACCOUNT_ID_CONTRA,
                             LV.PR_DETAIL_ID, LV.PR_DETAIL_NAME, LV.DEBIT_CREDIT, LV.AMOUNT, LV.COMMENTS
                      FROM dbo.LEDGER_VIEW LV WITH (NOLOCK)
                      LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON LV.ORGANIZATION_ID = O.ORGANIZATION_ID
                      WHERE LV.TRAN_DATE >= ? AND LV.TRAN_DATE <= ? {org_where_lv}
                      ORDER BY LV.TRAN_DATE, LV.TRAN_NO"""
            params = [d_from, d_to] + org_params
            fname = f"BC007_Nhat_Ky_Chung_ChiTiet_{from_dt.strftime('%d%m%Y')}-{to_dt.strftime('%d%m%Y')}.csv"
        elif report_type == "BC007":
            # TỔNG HỢP (như web đang xem) — thêm Đơn vị / Tên đơn vị / Mã chứng từ
            journal_view_mode = request.args.get("journal_view_mode", "detail")
            if journal_view_mode == "summary":
                headers = ["Mã chứng từ", "Số CT", "Diễn giải",
                           "TK Nợ", "TK Có", "Phát sinh Nợ", "Phát sinh Có"]
            else:
                headers = ["Đơn vị", "Tên đơn vị", "Ngày HT", "Mã chứng từ", "Số CT", "Diễn giải",
                           "TK Nợ", "TK Có", "Phát sinh Nợ", "Phát sinh Có"]
            sql = f"""SELECT L.ORGANIZATION_ID, O.ORGANIZATION_NAME, L.TRAN_DATE, L.TRAN_ID, L.TRAN_NO,
                             L.DESCRIPTION, L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA, L.DEBIT_CREDIT, L.AMOUNT
                      FROM dbo.LEDGER L WITH (NOLOCK)
                      LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON L.ORGANIZATION_ID = O.ORGANIZATION_ID
                      WHERE L.TRAN_DATE >= ? AND L.TRAN_DATE <= ? {org_where_l}
                      ORDER BY L.TRAN_DATE, L.TRAN_NO"""
            params = [d_from, d_to] + org_params
            fname = f"BC007_So_Nhat_Ky_Chung_{from_dt.strftime('%d%m%Y')}-{to_dt.strftime('%d%m%Y')}.csv"
        elif report_type == "BC008":
            if not account_id:
                return jsonify({"status": "error", "message": "Vui lòng chọn Tài khoản."}), 400
            headers = ["Ngày HT", "Số CT", "Diễn giải", "TK Đối ứng", "Phát sinh Nợ", "Phát sinh Có", "Dư Nợ", "Dư Có"]
            # Tài khoản là bộ lọc ĐA CHỌN — dùng chung helper với bản trên màn hình, nếu không 2 bên lệch nhau
            acc_clause, acc_params = _acc_like_sql(account_id)
            sql = f"""SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                      FROM dbo.LEDGER WITH (NOLOCK) WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                      ORDER BY TRAN_DATE, TRAN_NO"""
            params = acc_params + [d_from, d_to] + org_params
            fname = (f"BC008_So_Chi_Tiet_{account_id.replace(',', '-')}"
                     f"_{from_dt.strftime('%d%m%Y')}-{to_dt.strftime('%d%m%Y')}.csv")
        elif report_type == "BC013":
            # BẢNG KÊ HÓA ĐƠN BÁN RA (6.2) — cột y hệt bảng trên web, xuất TOÀN BỘ (không phân trang).
            # Bộ lọc phải khớp /api/vat_sales_report: đơn vị dùng _org_filter_sql (không chọn ⇒ loại đơn vị
            # ngoài cây '00'), tài khoản LIKE prefix đa chọn — nếu dùng org_where thường sẽ lệch số so màn hình.
            acc_ids_13 = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()]
            _oc, _op = _org_filter_sql(org_ids, "ORGANIZATION_ID")
            vat_org_where = (" AND " + _oc) if _oc else ""
            vat_acc_where, vat_acc_params = "", []
            if acc_ids_13:
                vat_acc_where = " AND (" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids_13)) + ")"
                vat_acc_params = [a + "%" for a in acc_ids_13]
            headers = ["TT", "Ký hiệu hóa đơn", "Số hóa đơn", "Ngày phát hành", "Tên người bán",
                       "Mã số thuế người mua", "Mặt hàng", "Doanh số bán chưa có thuế",
                       "Thuế suất (%)", "Thuế GTGT", "Ghi chú"]
            if mode == "summary":
                # Gộp mỗi số hóa đơn 1 dòng — GROUP BY y hệt nhánh summary của /api/vat_sales_report
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE,
                                 ISNULL(PR_DETAIL_NAME,''), ISNULL(TAX_FILE_NUMBER,''),
                                 N'Bán hàng hóa, dịch vụ', ISNULL(SUM(AMOUNT_ITEM),0),
                                 ISNULL(MAX(VAT_TAX_RATE),0), ISNULL(SUM(AMOUNT),0), N''
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                          WHERE DEBIT_CREDIT = 'CRD'
                            AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{vat_org_where}{vat_acc_where}
                          GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID
                          ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO"""
            else:
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE,
                                 ISNULL(PR_DETAIL_NAME,''), ISNULL(TAX_FILE_NUMBER,''), ISNULL(ITEM_NAME,''),
                                 ISNULL(AMOUNT_ITEM,0), ISNULL(VAT_TAX_RATE,0), ISNULL(AMOUNT,0), ISNULL(COMMENTS,'')
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                          WHERE DEBIT_CREDIT = 'CRD'
                            AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{vat_org_where}{vat_acc_where}
                          ORDER BY VAT_TAX_RATE, VAT_TRAN_DATE, VAT_TRAN_NO"""
            params = [d_from, d_to] + list(_op) + vat_acc_params
            fname = (f"BC013_Bang_Ke_Ban_Ra_{'TongHop' if mode == 'summary' else 'ChiTiet'}"
                     f"_{from_dt.strftime('%d%m%Y')}-{to_dt.strftime('%d%m%Y')}.csv")
        else:
            return jsonify({"status": "error", "message": "Report type không hỗ trợ xuất CSV."}), 400

        def _amt(a):
            a = float(a or 0)
            return int(a) if a.is_integer() else a

        def generate():
            own = _make_conn(db_cfg)
            try:
                cur = own.cursor()
                yield '﻿' + ','.join(_csv_escape(h) for h in headers) + '\r\n'   # BOM để Excel nhận UTF-8

                if report_type == "BC008":
                    odeb = ocrd = 0.0
                    c2 = own.cursor()
                    c2.execute(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                          SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                                   FROM dbo.BALANCE_VIEW WITH (NOLOCK) WHERE {acc_clause} AND TRAN_DATE = ? {org_where}""",
                               acc_params + [first_day] + org_params)
                    ro = c2.fetchone()
                    if ro: odeb += float(ro[0] or 0); ocrd += float(ro[1] or 0)
                    if from_dt > date(from_dt.year, 1, 1):
                        c2.execute(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                              SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                                       FROM dbo.LEDGER WITH (NOLOCK) WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}""",
                                   acc_params + [first_day, d_from] + org_params)
                        rl = c2.fetchone()
                        if rl: odeb += float(rl[0] or 0); ocrd += float(rl[1] or 0)
                    run = odeb - ocrd
                    yield ','.join(_csv_escape(x) for x in ['', '', 'Số dư đầu kỳ', '', '', '',
                                                            _amt(run if run > 0 else 0), _amt(-run if run < 0 else 0)]) + '\r\n'
                    cur.execute(sql, params)
                    while True:
                        batch = cur.fetchmany(2000)
                        if not batch: break
                        lines = []
                        for r in batch:
                            amt = float(r[5] or 0); is_deb = (r[4] == 'DEB')
                            run += amt if is_deb else -amt
                            lines.append(','.join(_csv_escape(x) for x in [
                                r[0], r[1] or '', r[2] or '', r[3] or '',
                                _amt(amt if is_deb else 0), _amt(amt if not is_deb else 0),
                                _amt(run if run > 0 else 0), _amt(-run if run < 0 else 0)]))
                        yield '\r\n'.join(lines) + '\r\n'
                elif report_type == "BC013":  # BẢNG KÊ BÁN RA — TT tự đánh, mã giữ dạng text, chốt Tổng cộng
                    cur.execute(sql, params)
                    stt = 0
                    sum_amt = sum_vat = 0.0
                    while True:
                        batch = cur.fetchmany(2000)
                        if not batch: break
                        lines = []
                        for r in batch:
                            stt += 1
                            amt = float(r[6] or 0); vat = float(r[8] or 0)
                            sum_amt += amt; sum_vat += vat
                            lines.append(','.join(_csv_escape(x) for x in [
                                stt, _csv_text_cell(r[0]), _csv_text_cell(r[1]), r[2],
                                r[3] or '', _csv_text_cell(r[4]), r[5] or '',
                                _amt(amt), _amt(float(r[7] or 0)), _amt(vat), r[9] or '']))
                        yield '\r\n'.join(lines) + '\r\n'
                    yield ','.join(_csv_escape(x) for x in [
                        '', '', '', '', '', '', 'Tổng cộng', _amt(sum_amt), '', _amt(sum_vat), '']) + '\r\n'
                elif report_type == "BC007" and mode == "detail":  # NHẬT KÝ CHUNG CHI TIẾT
                    cur.execute(sql, params)
                    while True:
                        batch = cur.fetchmany(2000)
                        if not batch: break
                        lines = []
                        for r in batch:
                            amt = float(r[13] or 0); is_deb = (r[12] == 'DEB')
                            lines.append(','.join(_csv_escape(x) for x in [
                                r[0] or '', _csv_text_cell(r[1]), r[2] or '', r[3] or '', r[4] or '', r[5],
                                r[6] or '', r[7] or '', r[8] or '', r[9] or '', _csv_text_cell(r[10]), r[11] or '',
                                _amt(amt if is_deb else 0), _amt(amt if not is_deb else 0), r[14] or '']))
                        yield '\r\n'.join(lines) + '\r\n'
                else:  # BC007 TỔNG HỢP (như web)
                    cur.execute(sql, params)
                    journal_view_mode = request.args.get("journal_view_mode", "detail")
                    while True:
                        batch = cur.fetchmany(2000)
                        if not batch: break
                        lines = []
                        for r in batch:
                            amt = float(r[9] or 0); is_deb = (r[8] == 'DEB')
                            if journal_view_mode == "summary":
                                row_data = [
                                    r[3] or '', r[4] or '', r[5] or '',
                                    r[6] or '', r[7] or '',
                                    _amt(amt if is_deb else 0), _amt(amt if not is_deb else 0)
                                ]
                            else:
                                row_data = [
                                    _csv_text_cell(r[0]), r[1] or '', r[2], r[3] or '', r[4] or '', r[5] or '',
                                    r[6] or '', r[7] or '',
                                    _amt(amt if is_deb else 0), _amt(amt if not is_deb else 0)
                                ]
                            lines.append(','.join(_csv_escape(x) for x in row_data))
                        yield '\r\n'.join(lines) + '\r\n'
            finally:
                try: own.close()
                except: pass

        resp = Response(stream_with_context(generate()), mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================================
# BC009 / BC010 — LƯU CHUYỂN TIỀN TỆ (trực tiếp + gián tiếp), chuẩn TT200/B03-DN
# Logic port nguyên từ LedgerReport (đã validated DB IACC_CHULONG T1-6/2026).
# ============================================================================

def _get_external_org_ids():
    """Danh sách ORGANIZATION_ID KHÔNG thuộc cây đơn vị '00' (vd: đơn vị ngoài như '66').
    Mặc định các báo cáo loại trừ những đơn vị này; người dùng muốn xem thì tự chọn ở bộ lọc."""
    db_config = session.get('db_config') or {}
    db_name = db_config.get('database', '')
    if db_name in _external_orgs_cache:
        return _external_orgs_cache[db_name]
    ext = []
    try:
        cur = get_connection().cursor()
        cur.execute("SELECT ORGANIZATION_ID, ISNULL(PARENT_ORGANIZATION_ID,'') FROM dbo.DM_ORGANIZATION WITH (NOLOCK)")
        par = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
        def reaches_root(o):
            seen = set(); c = o
            while c and c not in seen:
                if c == '00':
                    return True
                seen.add(c); c = par.get(c, '')
            return False
        if '00' not in par:
            # ⛔ CHỐT AN TOÀN — QUAN TRỌNG HƠN Ở STUDIO vì Studio chạy trên DB của nhiều khách,
            # mỗi khách đánh mã đơn vị một kiểu. DB không có đơn vị gốc '00' thì reaches_root()
            # trả False cho MỌI đơn vị ⇒ ext = toàn bộ danh sách ⇒ NOT IN (tất cả) ⇒ mọi báo cáo
            # và mọi danh sách trả 0 dòng mà KHÔNG báo lỗi gì. Kiểu hỏng câm, rất khó truy.
            # Không có gốc '00' thì coi như DB đó không có khái niệm "ngoài cây" → không lọc.
            logger.warning("DM_ORGANIZATION khong co don vi goc '00' — bo qua loc don vi ngoai cay.")
            ext = []
        else:
            ext = [o for o in par if o != '00' and not reaches_root(o)]
    except Exception:
        ext = []
    _external_orgs_cache[db_name] = ext
    return ext


def _acc_like_sql(account_id, col="ACCOUNT_ID"):
    """Bộ lọc tài khoản cha→con cho BC008. `account_id` có thể chứa NHIỀU mã ngăn bởi dấu phẩy ('111,112').
    Trả (clause, params) = "(col LIKE ? OR col LIKE ?)", ['111%','112%'].

    ⚠️ Code cũ ghép thẳng chuỗi vào `col LIKE ? + '%'` → thành `LIKE '111,112%'` → KHÔNG khớp dòng nào →
    chọn 2 tài khoản là báo cáo/file xuất RỖNG mà không báo lỗi (bộ lọc Tài khoản là đa chọn nên rất dễ dính).
    Dùng chung 1 helper cho cả bản trên màn hình lẫn nút xuất để 2 bên không lệch nhau.
    (Port từ LedgerReport — xem mục 9.6; Studio dính lỗi này tới 27/07/2026.)
    """
    accs = [a.strip() for a in (account_id or "").split(",") if a.strip()]
    if not accs:
        return "", []
    clause = "(" + " OR ".join([f"{col} LIKE ?"] * len(accs)) + ")"
    return clause, [a + "%" for a in accs]


def _org_filter_sql(org_ids, col="ORGANIZATION_ID"):
    """Trả (clause, params) cho bộ lọc đơn vị.
    - Có chọn đơn vị  -> col IN (...)  (tôn trọng đúng lựa chọn, kể cả đơn vị ngoài)
    - Không chọn      -> mặc định loại đơn vị ngoài cây 00 (col NOT IN externals)
    """
    if org_ids:
        return f"{col} IN ({','.join(['?'] * len(org_ids))})", list(org_ids)
    ext = _get_external_org_ids()
    if ext:
        return f"{col} NOT IN ({','.join(['?'] * len(ext))})", list(ext)
    return "", []


def _cf_is_cash(acc):
    a = (acc or "").strip()
    return a[:3] in ("111", "112", "113") or a[:4] == "1281"


def _cf_classify_direct(contra, dc):
    """Trả mã chỉ tiêu B03-DN (trực tiếp) cho 1 nghiệp vụ tiền.
    dc='DEB' → tiền THU (+) ; dc='CRD' → tiền CHI (−)."""
    c = (contra or "").strip()
    p3, p4 = c[:3], c[:4]
    if dc == "DEB":   # ----- TIỀN THU -----
        if p3 in ("511", "512", "131") or p4 == "3331": return "01"   # bán hàng, thu nợ KH, VAT đầu ra
        if p3 == "411":                                  return "31"   # nhận vốn góp CSH
        if p4 == "3411" or p3 in ("341", "343", "171"):  return "33"   # thu từ đi vay
        if p3 == "515" or p4 in ("1281", "1288", "1283", "121"): return "27"  # thu lãi, cổ tức
        if p3 == "128":                                  return "24"   # thu hồi cho vay
        if p3 in ("221", "222") or p4 == "2281":         return "26"   # thu hồi góp vốn
        if p3 == "711":                                  return "22"   # thanh lý TSCĐ
        return "06"                                                    # thu khác HĐKD
    else:             # ----- TIỀN CHI -----
        if p3 == "131":                                  return "01"   # đảo/hoàn thu bán hàng → net Mã 01
        if p3 == "334":                                  return "03"   # trả người lao động
        if p4 == "3334":                                 return "05"   # thuế TNDN đã nộp
        if p3 == "635":                                  return "04"   # lãi vay đã trả
        if p3 in ("151", "152", "153", "154", "155", "156", "157", "158", "159",
                  "331", "611", "621", "627", "641", "642", "133", "242", "142"): return "02"  # chi NCC/HHDV
        if p3 in ("211", "213", "217", "241"):           return "21"   # chi mua TSCĐ
        if p3 == "128":                                  return "23"   # chi cho vay
        if p3 in ("221", "222") or p4 == "2281":         return "25"   # chi góp vốn
        if p4 == "3412":                                 return "35"   # trả nợ gốc thuê tài chính
        if p4 == "3411" or p3 in ("341", "343", "171"):  return "34"   # trả nợ gốc vay
        if p3 == "419":                                  return "32"   # mua lại cổ phiếu
        if p3 == "421":                                  return "36"   # cổ tức, LN đã trả CSH
        return "07"                                                    # chi khác HĐKD


def _calc_results(data, thtt_expense_list, expense_classes):
    """Engine KQKD (BC001). Với LCTT gián tiếp chỉ cần r['13'] (LN trước thuế)
    và r['07'] (chi phí lãi vay) — 2 chỉ tiêu này chỉ phụ thuộc tổng TK 5/6/7/8
    nên item_class/expense có thể rỗng."""
    sum_map = {}
    excl_map = {}
    for d in data:
        acc = d['acc']; contra = d['contra']; dc = d['dc']
        ic = d['item_class']; val = d['val']
        k1 = (acc, dc, ic);             sum_map[k1]  = sum_map.get(k1, 0) + val
        k2 = (acc, contra[:3], dc, ic); excl_map[k2] = excl_map.get(k2, 0) + val

    def s(acc_prefix, dc, item_classes=None):
        if isinstance(item_classes, str): item_classes = [item_classes]
        total = 0
        for (acc, d_c, ic), val in sum_map.items():
            if d_c == dc and acc.startswith(acc_prefix):
                if item_classes is None or ic in item_classes:
                    total += val
        return total

    def s_excl(acc_prefix, dc, excl_contras, item_classes=None):
        if isinstance(item_classes, str): item_classes = [item_classes]
        total = 0
        for (acc, contra, d_c, ic), val in excl_map.items():
            if d_c == dc and acc.startswith(acc_prefix):
                if item_classes is None or ic in item_classes:
                    if not any(contra.startswith(c) for c in excl_contras):
                        total += val
        return total

    def s_multi(acc_prefixes, dc, item_classes=None):
        if isinstance(item_classes, str): item_classes = [item_classes]
        if isinstance(acc_prefixes, str): acc_prefixes = [acc_prefixes]
        total = 0
        for (acc, d_c, ic), val in sum_map.items():
            if d_c == dc and any(acc.startswith(p) for p in acc_prefixes):
                if item_classes is None or ic in item_classes:
                    total += val
        return total

    def s_multi_excl(acc_prefixes, dc, excl_contras, item_classes=None):
        if isinstance(item_classes, str): item_classes = [item_classes]
        if isinstance(acc_prefixes, str): acc_prefixes = [acc_prefixes]
        total = 0
        for (acc, contra, d_c, ic), val in excl_map.items():
            if d_c == dc and any(acc.startswith(p) for p in acc_prefixes):
                if item_classes is None or ic in item_classes:
                    if not any(contra.startswith(c) for c in excl_contras):
                        total += val
        return total

    r = {}
    r['01'] = s('511', 'CRD') - s_excl('511', 'DEB', ['911', '521'])
    r['02'] = s('521', 'DEB') - s_excl('521', 'CRD', ['511'])
    r['03'] = r['01'] - r['02']
    r['04'] = s('632', 'DEB') - s_excl('632', 'CRD', ['911'])
    r['05'] = r['03'] - r['04']
    r['06'] = s('515', 'CRD') - s_excl('515', 'DEB', ['911'])
    r['07'] = s('635', 'DEB') - s_excl('635', 'CRD', ['911'])
    r['08'] = s_multi(['641', '642'], 'DEB') - s_multi_excl(['641', '642'], 'CRD', ['911'])
    r['09'] = r['05'] + r['06'] - r['07'] - r['08']
    r['10'] = s('711', 'CRD') - s_excl('711', 'DEB', ['911'])
    r['11'] = s('811', 'DEB') - s_excl('811', 'CRD', ['911'])
    r['12'] = r['10'] - r['11']
    r['13'] = r['09'] + r['12']
    r['14'] = s('8211', 'DEB') - s_excl('8211', 'CRD', ['911'])
    r['15'] = s('8212', 'DEB') - s_excl('8212', 'CRD', ['911'])
    r['16'] = r['13'] - r['14'] - r['15']
    return r


@app.route("/api/cash_flow")
@with_db_lock
def get_cash_flow():
    """BC009 (trực tiếp) + BC010 (gián tiếp). Trả {'direct':{...}, 'indirect':{...}}.
    Cả 2 dùng chung dữ liệu kỳ; Mã 20 gián tiếp được chốt khớp Mã 20 trực tiếp."""
    try:
        f_date  = request.args.get("from_date")
        t_date  = request.args.get("to_date")
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")
        f_str = from_dt.strftime("%Y%m%d")
        t_str = to_dt.strftime("%Y%m%d")

        cur = get_connection().cursor()
        _rc, _rp = _org_filter_sql(org_ids, "L.ORGANIZATION_ID")
        org_and = (" AND " + _rc) if _rc else ""

        cash_like = ("(L.ACCOUNT_ID LIKE '111%' OR L.ACCOUNT_ID LIKE '112%' "
                     "OR L.ACCOUNT_ID LIKE '113%' OR L.ACCOUNT_ID LIKE '1281%')")

        # ---------- 1) PHƯƠNG PHÁP TRỰC TIẾP ----------
        q_cash = f"""
            SELECT L.ACCOUNT_ID_CONTRA, L.DEBIT_CREDIT, SUM(L.AMOUNT)
            FROM dbo.LEDGER L WITH (NOLOCK)
            WHERE {cash_like} AND L.TRAN_DATE >= ? AND L.TRAN_DATE <= ?{org_and}
            GROUP BY L.ACCOUNT_ID_CONTRA, L.DEBIT_CREDIT
        """
        cur.execute(q_cash, [f_str, t_str] + list(_rp))
        d = {}
        for contra, dc, total in cur.fetchall():
            if _cf_is_cash(contra):           # loại chuyển tiền nội bộ
                continue
            code = _cf_classify_direct(contra, dc)
            sign = 1.0 if (dc or "").strip() == "DEB" else -1.0
            d[code] = d.get(code, 0.0) + sign * float(total or 0)

        def g(*cs): return sum(d.get(c, 0.0) for c in cs)
        d["20"] = g("01", "02", "03", "04", "05", "06", "07")
        d["30"] = g("21", "22", "23", "24", "25", "26", "27")
        d["40"] = g("31", "32", "33", "34", "35", "36")
        d["50"] = g("20", "30", "40")

        # ---------- 2) TIỀN & TƯƠNG ĐƯƠNG TIỀN ĐẦU/CUỐI KỲ (Mã 60/70) ----------
        try:
            cur.execute("SELECT TOP 1 ORGANIZATION_ID FROM dbo.BALANCE_VIEW WITH (NOLOCK)")
            _bs_clause, _bs_p = _org_filter_sql(org_ids, "ORGANIZATION_ID")
            _bs_and = (" AND " + _bs_clause) if _bs_clause else ""
            has_org_bal = True
        except Exception:
            _bs_and, _bs_p, has_org_bal = "", [], False
        cash_like_bv = ("(ACCOUNT_ID LIKE '111%' OR ACCOUNT_ID LIKE '112%' "
                        "OR ACCOUNT_ID LIKE '113%' OR ACCOUNT_ID LIKE '1281%')")
        q_open = f"""
            SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT WHEN DEBIT_CREDIT='CRD' THEN -AMOUNT ELSE 0 END)
            FROM dbo.BALANCE_VIEW WITH (NOLOCK)
            WHERE TRAN_DATE = ? AND {cash_like_bv}{_bs_and if has_org_bal else ''}
        """
        cur.execute(q_open, [first_day_of_year] + (list(_bs_p) if has_org_bal else []))
        cash_open_year = float((cur.fetchone() or [0])[0] or 0)

        def cash_mov(end_inclusive=None, end_exclusive=None):
            where = [cash_like, "L.TRAN_DATE >= ?"]
            params = [first_day_of_year]
            if end_inclusive:
                where.append("L.TRAN_DATE <= ?"); params.append(end_inclusive)
            if end_exclusive:
                where.append("L.TRAN_DATE < ?");  params.append(end_exclusive)
            if _rc:
                where.append(_rc); params.extend(_rp)
            cur.execute(f"""SELECT SUM(CASE WHEN L.DEBIT_CREDIT='DEB' THEN L.AMOUNT ELSE -L.AMOUNT END)
                            FROM dbo.LEDGER L WITH (NOLOCK) WHERE {' AND '.join(where)}""", params)
            return float((cur.fetchone() or [0])[0] or 0)

        d["60"] = cash_open_year + cash_mov(end_exclusive=f_str)   # tiền đầu kỳ
        d["61"] = 0.0                                              # ảnh hưởng tỷ giá (chưa tách)
        d["70"] = cash_open_year + cash_mov(end_inclusive=t_str)   # tiền cuối kỳ

        # ---------- 3) PHƯƠNG PHÁP GIÁN TIẾP ----------
        cur.execute(f"""
            SELECT L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA, L.DEBIT_CREDIT, SUM(L.AMOUNT)
            FROM dbo.LEDGER L WITH (NOLOCK)
            WHERE L.TRAN_DATE >= ? AND L.TRAN_DATE <= ?{org_and}
            GROUP BY L.ACCOUNT_ID, L.ACCOUNT_ID_CONTRA, L.DEBIT_CREDIT
        """, [f_str, t_str] + list(_rp))
        pl = cur.fetchall()

        def s(pfx, dc, excl=()):
            return sum(float(r[3] or 0) for r in pl
                       if (r[0] or "").strip().startswith(pfx) and r[2] == dc
                       and not any((r[1] or "").strip().startswith(e) for e in excl))
        def net(pfx):  # biến động số dư trong kỳ (DEB-CRD), loại bút toán kết chuyển 911
            return s(pfx, "DEB", ["911"]) - s(pfx, "CRD", ["911"])

        cf_data = [{"acc": (r[0] or "").strip(), "contra": (r[1] or "").strip(),
                    "dc": r[2], "val": float(r[3] or 0), "item_class": ""} for r in pl]
        kq = _calc_results(cf_data, {}, {})

        i = {}
        i["01"] = kq.get("13", 0.0)                                             # LN trước thuế (= BC001)
        i["02"] = s("214", "CRD", ["911"]) - s("214", "DEB", ["911"])           # khấu hao
        i["03"] = sum((s(p_, "CRD", ["911"]) - s(p_, "DEB", ["911"])) for p_ in ("229", "352", "159"))  # dự phòng
        i["04"] = 0.0
        i["05"] = 0.0
        i["06"] = kq.get("07", 0.0)                                             # chi phí lãi vay (= BC001 r07)
        i["09"] = -sum(net(p_) for p_ in ["131", "133", "136", "138", "141", "244"])  # phải thu
        i["10"] = -sum(net(p_) for p_ in ["151", "152", "153", "154", "155", "156", "157", "158"])  # tồn kho
        i["11"] = -sum(net(p_) for p_ in ["331", "333", "334", "335", "336", "337", "338"])  # phải trả
        i["12"] = -net("242")                                                   # chi phí trả trước
        i["13"] = -net("121")                                                   # chứng khoán KD
        i["14"] = d.get("04", 0.0)                                              # lãi vay đã trả (từ trực tiếp)
        i["15"] = d.get("05", 0.0)                                              # thuế TNDN đã nộp (từ trực tiếp)
        i["16"] = 0.0
        i["17"] = 0.0
        sum_wc  = sum(i[k] for k in ("09", "10", "11", "12", "13", "14", "15", "16", "17"))
        base    = i["01"] + i["02"] + i["03"] + i["04"] + i["05"] + i["06"]
        i["07"] = d["20"] - (base + sum_wc)   # điều chỉnh khác (chốt khớp Mã 20 trực tiếp)
        i["08"] = base + i["07"]
        i["20"] = i["08"] + sum_wc
        for k in ("21", "22", "23", "24", "25", "26", "27", "30",
                  "31", "32", "33", "34", "35", "36", "40", "50", "60", "61", "70"):
            i[k] = d.get(k, 0.0)

        return jsonify({"status": "ok", "data": {"direct": d, "indirect": i}})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


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

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        # Trước đây để rỗng ⇒ báo cáo GỘP CẢ đơn vị ngoài cây → không tie được với nhau
        # và làm Bảng cân đối kế toán không cân (đã trả giá ở LedgerReport 15/08/2026).
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        cur = get_connection().cursor()
        
        count_sql = f"""
            SELECT COUNT(*),
                   SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM dbo.LEDGER_VIEW WITH (NOLOCK)
            WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
        """
        base_params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
        cur.execute(count_sql, base_params)
        c_row = cur.fetchone()
        total_rows = c_row[0] or 0
        total_deb = float(c_row[1] or 0)
        total_crd = float(c_row[2] or 0)
        
        # Map ORGANIZATION_ID -> ORGANIZATION_NAME (LEDGER_VIEW không có sẵn tên đơn vị)
        org_map = {}
        try:
            cur.execute("SELECT CAST(ORGANIZATION_ID AS NVARCHAR(100)), ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WITH (NOLOCK)")
            org_map = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
        except Exception:
            pass

        offset = (page - 1) * page_size
        paged_sql = f"""
            WITH CTE AS (
                SELECT
                    TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                    ORGANIZATION_ID, TRAN_ID,
                    ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT * FROM CTE WHERE RowNum > ? AND RowNum <= ?
        """
        cur.execute(paged_sql, base_params + [offset, offset + page_size])

        rows = []
        for r in cur.fetchall():
            org_id = (str(r[7]) if r[7] is not None else "").strip()
            rows.append({
                "tran_date": r[0].strftime("%d/%m/%Y") if r[0] else "",
                "tran_no": r[1] or "",
                "description": r[2] or "",
                "account_id": r[3] or "",
                "contra_account_id": r[4] or "",
                "debit_credit": r[5] or "",
                "amount": float(r[6] or 0),
                "org_id": org_id,
                "org_name": org_map.get(org_id, ""),
                "tran_id": (str(r[8]) if r[8] is not None else "").strip()
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
        # page_size = 0 ⇒ LẤY TOÀN BỘ (phục vụ xuất .xls giữ form: DOM phải có đủ mọi trang)
        export_all = page_size <= 0
        if export_all:
            page = 1

        if not account_id:
            return jsonify({"status": "error", "message": "Vui lòng chọn tài khoản!"}), 400

        from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
        to_dt = datetime.strptime(t_date, "%d/%m/%Y").date()
        first_day_of_year = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        # Không chọn đơn vị ⇒ LOẠI đơn vị ngoài cây '00' — thống nhất với BC009/BC010/BC012/BC013.
        # Trước đây để rỗng ⇒ báo cáo GỘP CẢ đơn vị ngoài cây → không tie được với nhau
        # và làm Bảng cân đối kế toán không cân (đã trả giá ở LedgerReport 15/08/2026).
        _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        cur = get_connection().cursor()

        # Bộ lọc Tài khoản là ĐA CHỌN → phải dùng _acc_like_sql, không ghép chuỗi vào LIKE ? + '%'
        acc_clause, acc_params = _acc_like_sql(account_id)

        open_bal_deb = 0
        open_bal_crd = 0
        sql_open = f"""
            SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM dbo.BALANCE_VIEW WITH (NOLOCK)
            WHERE {acc_clause} AND TRAN_DATE = ? {org_where}
        """
        cur.execute(sql_open, acc_params + [first_day_of_year] + org_params)
        r_open = cur.fetchone()
        if r_open:
            open_bal_deb += float(r_open[0] or 0)
            open_bal_crd += float(r_open[1] or 0)

        if from_dt > date(from_dt.year, 1, 1):
            sql_lk = f"""
                SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                       SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}
            """
            cur.execute(sql_lk, acc_params + [first_day_of_year, from_dt.strftime("%Y%m%d")] + org_params)
            r_lk = cur.fetchone()
            if r_lk:
                open_bal_deb += float(r_lk[0] or 0)
                open_bal_crd += float(r_lk[1] or 0)

        base_params = acc_params + [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + org_params
        
        offset = (page - 1) * page_size
        
        stats_sql = f"""
            WITH CTE AS (
                SELECT DEBIT_CREDIT, AMOUNT,
                       ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT 
                COUNT(*),
                SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN RowNum <= ? AND DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                SUM(CASE WHEN RowNum <= ? AND DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
            FROM CTE
        """
        cur.execute(stats_sql, base_params + [offset, offset])
        s_row = cur.fetchone()
        
        total_rows = s_row[0] or 0
        total_deb = float(s_row[1] or 0)
        total_crd = float(s_row[2] or 0)
        offset_deb = float(s_row[3] or 0)
        offset_crd = float(s_row[4] or 0)

        paged_sql = f"""
            WITH CTE AS (
                SELECT 
                    TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                    ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO) as RowNum
                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
            )
            SELECT * FROM CTE WHERE RowNum > ? AND RowNum <= ?
        """
        # export_all: cận trên = total_rows (đã đếm ở stats_sql) → lấy hết, không phân trang
        cur.execute(paged_sql, base_params + [offset, total_rows if export_all else offset + page_size])

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
                "total_pages": 1 if export_all else max(1, (total_rows + page_size - 1) // page_size),
                "page": page
            }
        })
    except Exception as e:
        msg = str(e)
        logger.error(f"Error in BC008 get_account_details: {msg}")
        return jsonify({"status": "error", "message": msg}), 500


# ============================================================
# BC012 — SỔ TIỀN MẶT VÀ TIỀN NGÂN HÀNG (nguồn: VOUCHER_VIEW)
#   - Mỗi tài khoản tiền (mặc định 111,112,113) là 1 "sổ" riêng:
#     Dư đầu kỳ (net phát sinh trước from_date) -> phát sinh Nợ/Có -> Dư cuối kỳ.
#   - VOUCHER_VIEW là view định khoản kép: mỗi dòng có ACCOUNT_ID_DEBIT + ACCOUNT_ID_CREDIT + AMOUNT,
#     nên TK đối ứng có sẵn. Phía Nợ thuộc TK tiền -> ghi Nợ (thu); phía Có -> ghi Có (chi);
#     dòng chuyển nội bộ giữa 2 TK tiền sinh 2 bút toán.
# ============================================================
# Cache 1 kết quả flat mới nhất để PHÂN TRANG (10000 dòng/trang) không phải dựng lại mỗi lần đổi trang.
_cashbook_cache = {}  # {cache_key: flat_list}


def _cashbook_key(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids):
    db_name = session.get('db_config', {}).get('database', 'N/A')
    return hashlib.md5("|".join([
        db_name, f_date, t_date, ",".join(acc_ids), ",".join(contra_ids), tran_no, ",".join(org_ids)
    ]).encode()).hexdigest()


def _build_cashbook_flat(from_dt, to_dt, acc_ids, contra_ids, tran_no, org_ids, cur=None, org_filter=None):
    """Dựng danh sách dòng hiển thị PHẲNG (head/row/cong/du/grand) + số dư luỹ kế cho sổ quỹ BC012.
    cur/org_filter: job xuất Excel chạy ở THREAD RIÊNG (không có session/pool) → truyền sẵn cursor của connection
    riêng và bộ lọc đơn vị đã tính trong request. Bỏ trống = dùng pool như màn hình."""
    _oc, org_params = org_filter if org_filter is not None else _org_filter_sql(org_ids, "ORGANIZATION_ID")
    org_where = (" AND " + _oc) if _oc else ""
    if cur is None:
        cur = get_connection().cursor()

    acc_name = {}
    try:
        cur.execute("SELECT ACCOUNT_ID, ACCOUNT_NAME FROM dbo.DM_ACCOUNT WITH (NOLOCK)")
        acc_name = {(r[0] or '').strip(): (r[1] or '').strip() for r in cur.fetchall()}
    except Exception:
        pass

    opening = {a: 0.0 for a in acc_ids}
    open_sel = ", ".join(
        "SUM(CASE WHEN ACCOUNT_ID_DEBIT LIKE ? THEN AMOUNT ELSE 0 END) - SUM(CASE WHEN ACCOUNT_ID_CREDIT LIKE ? THEN AMOUNT ELSE 0 END)"
        for _ in acc_ids)
    open_acc_clause = " OR ".join(["ACCOUNT_ID_DEBIT LIKE ?"] * len(acc_ids) + ["ACCOUNT_ID_CREDIT LIKE ?"] * len(acc_ids))
    open_params = []
    for a in acc_ids:
        open_params += [a + "%", a + "%"]
    open_params += [from_dt.strftime("%Y%m%d")]
    open_params += [a + "%" for a in acc_ids] * 2
    open_params += org_params
    cur.execute(f"""
        SELECT {open_sel}
        FROM dbo.VOUCHER_VIEW WITH (NOLOCK)
        WHERE TRAN_DATE < ? AND ({open_acc_clause}){org_where}
    """, open_params)
    orow = cur.fetchone()
    if orow:
        for i, a in enumerate(acc_ids):
            opening[a] = float(orow[i] or 0)

    acc_like_clause = " OR ".join(["ACCOUNT_ID_DEBIT LIKE ?"] * len(acc_ids) +
                                  ["ACCOUNT_ID_CREDIT LIKE ?"] * len(acc_ids))
    params = [from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")] + [a + "%" for a in acc_ids] * 2 + org_params
    contra_where = ""
    if contra_ids:
        contra_where = " AND (" + " OR ".join(["ACCOUNT_ID_DEBIT LIKE ?", "ACCOUNT_ID_CREDIT LIKE ?"] * len(contra_ids)) + ")"
        for c in contra_ids:
            params += [c + "%", c + "%"]
    tran_where = ""
    if tran_no:
        tran_where = " AND TRAN_NO LIKE ?"
        params.append("%" + tran_no + "%")

    cur.execute(f"""
        SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_DEBIT, ACCOUNT_ID_CREDIT, AMOUNT
        FROM dbo.VOUCHER_VIEW WITH (NOLOCK)
        WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? AND ({acc_like_clause}){org_where}{contra_where}{tran_where}
        ORDER BY TRAN_DATE, TRAN_NO, PR_KEY_CTU
    """, params)

    buckets = {acc: [] for acc in acc_ids}
    for row in cur.fetchall():
        tdate = row[0].strftime("%d/%m/%Y") if row[0] else ""
        tno   = row[1] or ""
        desc  = row[2] or ""
        deb_acc = (row[3] or "").strip()
        crd_acc = (row[4] or "").strip()
        amt   = float(row[5] or 0)
        for acc in acc_ids:
            if deb_acc.startswith(acc):
                contra = crd_acc
                if (not contra_ids) or any(contra.startswith(c) for c in contra_ids):
                    buckets[acc].append((tdate, tno, desc, contra, amt, 0.0))
            if crd_acc.startswith(acc):
                contra = deb_acc
                if (not contra_ids) or any(contra.startswith(c) for c in contra_ids):
                    buckets[acc].append((tdate, tno, desc, contra, 0.0, amt))

    flat = []
    ngroups = len(acc_ids)
    g_pd = g_pc = g_close = 0.0
    for acc in acc_ids:
        rows = buckets[acc]
        open_net = opening.get(acc, 0.0)
        flat.append({"t": "head", "account_id": acc, "account_name": acc_name.get(acc, ""), "opening": open_net})
        running = open_net
        sum_deb = sum_crd = 0.0
        for i, (tdate, tno, desc, contra, deb, crd) in enumerate(rows):
            running += deb - crd
            sum_deb += deb; sum_crd += crd
            flat.append({"t": "row", "account_id": acc, "stt": i + 1, "tran_date": tdate, "tran_no": tno,
                         "description": desc, "contra_account_id": contra, "debit": deb, "credit": crd, "balance": running})
        close_net = open_net + sum_deb - sum_crd
        flat.append({"t": "cong", "account_id": acc, "sum_deb": sum_deb, "sum_crd": sum_crd})
        flat.append({"t": "du", "account_id": acc, "close": close_net})
        g_pd += sum_deb; g_pc += sum_crd; g_close += close_net
    if ngroups > 1:
        flat.append({"t": "grand", "period_deb": g_pd, "period_crd": g_pc, "close": g_close})
    return flat


def _cashbook_flat_cached(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids):
    from_dt = datetime.strptime(f_date, "%d/%m/%Y").date()
    to_dt   = datetime.strptime(t_date, "%d/%m/%Y").date()
    key = _cashbook_key(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids)
    flat = _cashbook_cache.get(key)
    if flat is None:
        flat = _build_cashbook_flat(from_dt, to_dt, acc_ids, contra_ids, tran_no, org_ids)
        _cashbook_cache.clear()
        _cashbook_cache[key] = flat
    return flat


@app.route("/api/cash_book")
@with_db_lock
def get_cash_book():
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        acc_ids = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()] or ["111", "112", "113"]
        contra_ids = [v.strip() for v in request.args.get("contra_acc_ids", "").split(",") if v.strip()]
        tran_no = request.args.get("tran_no", "").strip()
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 10000))

        flat = _cashbook_flat_cached(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids)
        total = len(flat)
        # page_size = 0 ⇒ LẤY TOÀN BỘ (phục vụ xuất .xls giữ form: DOM phải có đủ mọi trang)
        if page_size <= 0:
            return jsonify({"status": "ok", "rows": flat,
                            "pagination": {"total_rows": total, "total_pages": 1, "page": 1}})
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * page_size
        return jsonify({"status": "ok", "rows": flat[offset:offset + page_size],
                        "pagination": {"total_rows": total, "total_pages": total_pages, "page": page}})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        logger.error(f"Error in BC012 get_cash_book: {msg}")
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/cash_book/export_csv")
@with_db_lock
def get_cash_book_export_csv():
    """Xuất TOÀN BỘ sổ quỹ BC012 ra CSV (UTF-8 BOM) — chịu được số dòng rất lớn, không phụ thuộc DOM/phân trang."""
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        acc_ids = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()] or ["111", "112", "113"]
        contra_ids = [v.strip() for v in request.args.get("contra_acc_ids", "").split(",") if v.strip()]
        tran_no = request.args.get("tran_no", "").strip()
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        flat = _cashbook_flat_cached(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids)
        body = _cashbook_csv_stream(flat)
        fname = f"BC012_So_Tien_Mat_Va_Tien_Ngan_Hang_{f_date.replace('/','')}-{t_date.replace('/','')}.csv"
        from flask import Response
        return Response(body, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={fname}"})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/vat_sales_report")
@with_db_lock
def get_vat_sales_report():
    """Báo cáo 6.2 - BẢNG KÊ HÓA ĐƠN, CHỨNG TỪ HÀNG HÓA, DỊCH VỤ BÁN RA (Tổng hợp & Chi tiết)."""
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        mode = request.args.get("mode", "detail")  # 'detail' | 'summary'
        org_ids = [v for v in request.args.get("org_ids", "").split(",") if v]
        acc_ids = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()]
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 1000))
        # page_size = 0 ⇒ LẤY TOÀN BỘ (phục vụ xuất .xls giữ form: DOM phải có đủ mọi trang)
        export_all = page_size <= 0
        if not export_all and page_size > 1000: page_size = 1000

        if not f_date or not t_date:
            return jsonify({"status": "error", "message": "Thiếu từ ngày / đến ngày"}), 400

        f_dt = datetime.strptime(f_date, "%d/%m/%Y").strftime("%Y%m%d")
        t_dt = datetime.strptime(t_date, "%d/%m/%Y").strftime("%Y%m%d")

        _oc, _op = _org_filter_sql(org_ids, "ORGANIZATION_ID")
        org_where = (" AND " + _oc) if _oc else ""

        acc_where = ""
        acc_params = []
        if acc_ids:
            acc_where = " AND (" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids)) + ")"
            acc_params = [a + "%" for a in acc_ids]

        params = [f_dt, t_dt] + list(_op) + list(acc_params)
        cur = get_connection().cursor()

        # 1. Tính tổng số tiền (luôn giống nhau cho cả Tổng hợp & Chi tiết)
        totals_sql = f"""
            SELECT 
                ISNULL(SUM(AMOUNT_ITEM), 0),
                ISNULL(SUM(CASE WHEN VAT_TAX_RATE > 0 THEN AMOUNT_ITEM ELSE 0 END), 0),
                ISNULL(SUM(AMOUNT), 0)
            FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
            WHERE DEBIT_CREDIT = 'CRD'
              AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
        """
        cur.execute(totals_sql, params)
        tot_row = cur.fetchone()
        total_amount_item = float(tot_row[0] or 0) if tot_row else 0.0
        taxable_amount_item = float(tot_row[1] or 0) if tot_row else 0.0
        total_vat_amount = float(tot_row[2] or 0) if tot_row else 0.0

        # 2. Đếm số dòng (Tổng hợp đếm theo Số HĐ, Chi tiết đếm từng mặt hàng)
        if mode == "summary":
            count_sql = f"""
                SELECT COUNT(*) FROM (
                    SELECT VAT_TRAN_SERIE, VAT_TRAN_NO
                    FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                    WHERE DEBIT_CREDIT = 'CRD'
                      AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
                    GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID
                ) AS Grp
            """
        else:
            count_sql = f"""
                SELECT COUNT(*)
                FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                WHERE DEBIT_CREDIT = 'CRD'
                  AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
            """
        cur.execute(count_sql, params)
        c_row = cur.fetchone()
        total_rows = c_row[0] if c_row else 0

        if export_all:
            total_pages, page = 1, 1
            start_row, end_row = 0, total_rows
        else:
            total_pages = max(1, (total_rows + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))
            start_row = (page - 1) * page_size
            end_row = page * page_size

        # 3. Phân trang SQL Server
        if mode == "summary":
            page_sql = f"""
                SELECT * FROM (
                    SELECT 
                        ISNULL(VAT_TRAN_SERIE, '') AS serie,
                        ISNULL(VAT_TRAN_NO, '') AS no,
                        VAT_TRAN_DATE AS date_raw,
                        ISNULL(PR_DETAIL_NAME, '') AS seller,
                        ISNULL(TAX_FILE_NUMBER, '') AS tax_code,
                        N'Bán hàng hóa, dịch vụ' AS item,
                        ISNULL(SUM(AMOUNT_ITEM), 0) AS amount_item,
                        ISNULL(MAX(VAT_TAX_RATE), 0) AS tax_rate,
                        ISNULL(SUM(AMOUNT), 0) AS vat_amount,
                        N'' AS comments,
                        ISNULL(ACCOUNT_ID, '') AS account_id,
                        ROW_NUMBER() OVER (ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO) AS RowNum
                    FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                    WHERE DEBIT_CREDIT = 'CRD'
                      AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
                    GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID
                ) AS Paged
                WHERE RowNum > ? AND RowNum <= ?
                ORDER BY RowNum
            """
        else:
            page_sql = f"""
                SELECT * FROM (
                    SELECT 
                        ISNULL(VAT_TRAN_SERIE, '') AS serie,
                        ISNULL(VAT_TRAN_NO, '') AS no,
                        VAT_TRAN_DATE AS date_raw,
                        ISNULL(PR_DETAIL_NAME, '') AS seller,
                        ISNULL(TAX_FILE_NUMBER, '') AS tax_code,
                        ISNULL(ITEM_NAME, '') AS item,
                        ISNULL(AMOUNT_ITEM, 0) AS amount_item,
                        ISNULL(VAT_TAX_RATE, 0) AS tax_rate,
                        ISNULL(AMOUNT, 0) AS vat_amount,
                        ISNULL(COMMENTS, '') AS comments,
                        ISNULL(ACCOUNT_ID, '') AS account_id,
                        ROW_NUMBER() OVER (ORDER BY VAT_TAX_RATE, VAT_TRAN_DATE, VAT_TRAN_NO) AS RowNum
                    FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                    WHERE DEBIT_CREDIT = 'CRD'
                      AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
                ) AS Paged
                WHERE RowNum > ? AND RowNum <= ?
                ORDER BY RowNum
            """

        cur.execute(page_sql, params + [start_row, end_row])
        rows = []
        for r in cur.fetchall():
            rows.append({
                "serie": (r[0] or '').strip(),
                "no": (r[1] or '').strip(),
                "date": r[2].strftime("%d/%m/%Y") if r[2] else "",
                "seller": (r[3] or '').strip(),
                "tax_code": (r[4] or '').strip(),
                "item": (r[5] or '').strip(),
                "amount_item": float(r[6] or 0),
                "tax_rate": float(r[7] or 0),
                "tax_amount": float(r[8] or 0),
                "comments": (r[9] or '').strip(),
                "account_id": (r[10] or '').strip()
            })

        totals = {
            "total_amount_item": total_amount_item,
            "taxable_amount_item": taxable_amount_item,
            "total_vat_amount": total_vat_amount
        }
        pagination = {
            "total_rows": total_rows,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size
        }

        return jsonify({"status": "ok", "data": rows, "totals": totals, "pagination": pagination})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        logger.error(f"Error in BC013 get_vat_sales_report: {msg}")
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


def _cashbook_csv_stream(flat):
    """Generator sinh từng dòng CSV từ danh sách flat (tiết kiệm RAM khi nhiều dòng)."""
    def esc(s):
        s = "" if s is None else str(s)
        if any(ch in s for ch in [',', '"', '\n', '\r']):
            return '"' + s.replace('"', '""') + '"'
        return s
    def n(v):
        v = float(v or 0)
        return "" if v == 0 else str(int(round(v)))
    yield "﻿" + ",".join(["STT", "Ngày ghi sổ", "Số CT Nợ", "Số CT Có", "Diễn giải", "Tk đối ứng", "Nợ", "Có", "Dư"]) + "\r\n"
    for r in flat:
        t = r["t"]
        if t == "head":
            label = f"Tài khoản {r['account_id']}" + (f" - {r['account_name']}" if r.get("account_name") else "")
            yield ",".join(["", "", "", "", esc(label), "", "", "", "Số dư đầu kỳ: " + n(r["opening"])]) + "\r\n"
        elif t == "cong":
            yield ",".join(["", "", "", "", esc(f"Cộng phát sinh — TK {r['account_id']}"), "", n(r["sum_deb"]), n(r["sum_crd"]), ""]) + "\r\n"
        elif t == "du":
            yield ",".join(["", "", "", "", esc(f"Số dư cuối kỳ — TK {r['account_id']}"), "", "", "", n(r["close"])]) + "\r\n"
        elif t == "grand":
            yield ",".join(["", "", "", "", "Tổng cộng tất cả tài khoản", "", n(r["period_deb"]), n(r["period_crd"]), n(r["close"])]) + "\r\n"
        else:
            deb = r["debit"]; crd = r["credit"]
            yield ",".join([str(r["stt"]), esc(r["tran_date"]),
                            esc(r["tran_no"]) if deb > 0 else "", esc(r["tran_no"]) if crd > 0 else "",
                            esc(r["description"]), esc(r["contra_account_id"]),
                            n(deb), n(crd), n(r["balance"])]) + "\r\n"


# ============================================================================
# XUẤT BÁO CÁO BC005–BC013 RA .XLSX CHUẨN FORM (hoặc CSV thô) — JOB NỀN, TIẾN TRÌNH THẬT  (09/2026)
#
# Thay cho 3 đường cũ ở ReportTab: .xls HTML-mso dựng từ DOM (báo cáo phân trang phải nạp hết dòng vào DOM,
# vài chục nghìn dòng là treo), CSV tải về trình duyệt rồi ĐỌC LẠI TOÀN BỘ thành text POST ngược lên
# /api/save_export (file vài trăm MB là phình RAM cả 2 phía), và thanh tiến trình giả chạy bằng setTimeout.
#
# - Báo cáo gộp (BC005/006/009/010/011): app gửi đúng các dòng ĐANG HIỂN THỊ → file khớp màn hình 100%,
#   không chạy lại truy vấn nặng.
# - Báo cáo nhiều dòng (BC007/008/012/013): server tự truy vấn CÙNG nguồn + CÙNG thứ tự với màn hình
#   (LEDGER_VIEW / VOUCHER_VIEW / VAT_TRANSACTION_VIEW), connection riêng, stream thẳng vào writer.
# - Dựng khối tiêu đề/bảng/chữ ký ở xlsx_report.py. Ghi ra Downloads\iPOS_Ledger_Studio rồi app hỏi Mở file/Mở thư mục.
# ============================================================================
import re as _re
from decimal import Decimal
# (xlsx_report as XR đã import ở đầu file)

_REPORT_EXPORT_CODES =('BC005', 'BC006', 'BC007', 'BC008', 'BC009', 'BC010', 'BC011', 'BC012', 'BC013')
# Đường dẫn các job đang ghi (file đích chưa xuất hiện trên đĩa) — để 2 lần bấm liên tiếp không chọn trùng tên
_export_reserved = set()


@app.route("/api/export/dir")
def get_export_dir():
    return jsonify({"status": "ok", "dir": _export_dir()})


def _rx_list(v):
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').split(',') if x.strip()]


def _rx_reserve_path(filename, ext):
    """Tên file sạch + không đè file đã có (file cũ có thể đang mở trong Excel → ghi đè sẽ lỗi quyền)."""
    base = os.path.basename(str(filename or '')).strip()
    if base.lower().endswith('.' + ext):
        base = base[:-(len(ext) + 1)]
    base = _re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', base).strip(' ._')[:150] or 'BaoCao'
    folder = _export_dir()
    # Dọn *.part mồ côi (EXE bị tắt ngang lúc đang ghi) — chỉ file cũ hơn 6 giờ, không đụng job đang chạy
    try:
        now = time.time()
        for fn in os.listdir(folder):
            fp = os.path.join(folder, fn)
            if fn.endswith('.part') and now - os.path.getmtime(fp) > 6 * 3600:
                os.remove(fp)
    except Exception:
        pass
    with _export_jobs_lock:
        i = 1
        while True:
            name = f"{base}.{ext}" if i == 1 else f"{base} ({i}).{ext}"
            path = os.path.join(folder, name)
            if (path.lower() not in _export_reserved and not os.path.exists(path)
                    and not os.path.exists(path + '.part')):
                _export_reserved.add(path.lower())
                return path
            i += 1


def _rx_header(h):
    """Khối tiêu đề app gửi lên (đúng chữ đang hiện trên tờ báo cáo) — chỉ làm sạch, không tự chế nội dung."""
    h = h if isinstance(h, dict) else {}

    def s(k, n=300):
        return str(h.get(k) or '').strip()[:n]
    return {
        'company_name': s('company_name'), 'company_line': s('company_line'), 'unit_line': s('unit_line'),
        'form_code': s('form_code', 60), 'title': s('title'), 'period_text': s('period_text'),
        'uom_text': s('uom_text', 60), 'sign_place': s('sign_place', 60),
        'sub_lines': [str(x).strip()[:600] for x in (h.get('sub_lines') or []) if str(x).strip()][:6],
    }


def _rx_dec(v):
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


def _rx_plan(rpt, variant, info, p, payload):
    """Kế hoạch xuất 1 báo cáo. GỌI TRONG REQUEST (cần session cho bộ lọc đơn vị / cache sổ quỹ).
    Trả dict {layout, total, rows(cur, ctx), prepare(cur, ctx)?, after(ctx)?, needs_db} hoặc chuỗi lỗi."""
    payload = payload if isinstance(payload, dict) else {}

    # ---- Báo cáo gộp: dữ liệu = đúng các dòng app đang hiển thị ----
    if rpt == 'BC005':
        n = len(payload.get('rows') or [])
        return dict(layout=XR.layout_bc005(info), total=n, rows=lambda cur, ctx: XR.rows_bc005(payload))
    if rpt in ('BC006', 'BC011'):
        is11 = rpt == 'BC011'
        n = len(payload.get('rows') or []) + (1 if payload.get('total') else 0)
        return dict(layout=XR.layout_bc006(info, is11), total=n, rows=lambda cur, ctx: XR.rows_bc006(payload, is11))
    if rpt in ('BC009', 'BC010'):
        n = len(payload.get('rows') or [])
        return dict(layout=XR.layout_cash_flow(info, rpt == 'BC009'), total=n,
                    rows=lambda cur, ctx: XR.rows_cash_flow(payload))

    # ---- Báo cáo nhiều dòng: server truy vấn lại, CÙNG nguồn & thứ tự với màn hình ----
    try:
        from_dt = datetime.strptime(str(p.get('from_date') or ''), "%d/%m/%Y").date()
        to_dt = datetime.strptime(str(p.get('to_date') or ''), "%d/%m/%Y").date()
    except ValueError:
        return "Khoảng ngày không hợp lệ."
    d_from, d_to = from_dt.strftime("%Y%m%d"), to_dt.strftime("%Y%m%d")
    org_ids = _rx_list(p.get('org_ids'))
    _oc, org_params = _org_filter_sql(org_ids, "ORGANIZATION_ID")
    org_where = (" AND " + _oc) if _oc else ""

    def fetch_rows(cur, sql, params, size=5000):
        cur.execute(sql, params)
        while True:
            batch = cur.fetchmany(size)
            if not batch:
                break
            for r in batch:
                yield r

    if rpt == 'BC007' and variant == 'full':
        # "Nhật ký chung đầy đủ cột" — mẫu SQL người dùng đưa (trước đây chỉ có ở CSV mode=detail)
        _lvc, _lvp = _org_filter_sql(org_ids, "LV.ORGANIZATION_ID")
        org_where_lv = (" AND " + _lvc) if _lvc else ""
        sql = f"""SELECT LV.ORGANIZATION_ID, O.ORGANIZATION_NAME, LV.JOB_NAME, LV.TRAN_ID, LV.TRAN_DATE, LV.TRAN_NO,
                         LV.DESCRIPTION, LV.ACCOUNT_ID, LV.ACCOUNT_ID_CONTRA, LV.PR_DETAIL_ID, LV.PR_DETAIL_NAME,
                         LV.DEBIT_CREDIT, LV.AMOUNT, LV.COMMENTS
                  FROM dbo.LEDGER_VIEW LV WITH (NOLOCK)
                  LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON LV.ORGANIZATION_ID = O.ORGANIZATION_ID
                  WHERE LV.TRAN_DATE >= ? AND LV.TRAN_DATE <= ? {org_where_lv}
                  ORDER BY LV.TRAN_DATE, LV.TRAN_NO"""

        def prepare(cur, ctx):
            cur.execute(f"""SELECT COUNT(*), SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                            FROM dbo.LEDGER_VIEW WITH (NOLOCK) WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}""",
                        [d_from, d_to] + list(org_params))
            r = cur.fetchone()
            ctx['deb'], ctx['crd'] = r[1] or 0, r[2] or 0
            return (r[0] or 0) + 1

        def rows(cur, ctx):
            for r in fetch_rows(cur, sql, [d_from, d_to] + list(_lvp)):
                amt = r[12] if r[12] is not None else 0
                yield [
                    'NKC', str(r[0] or '').strip(), r[1] or '', r[2] or '', str(r[3] or '').strip(), r[4], r[5] or '',
                    r[6] or '', r[7] or '', r[8] or '', str(r[9] or '').strip(), r[10] or '',
                    amt if r[11] == 'DEB' else None, amt if r[11] == 'CRD' else None, r[13] or '',
                ], 'data'
            yield [XR.Span('Cộng lũy kế', 12, 'right'), ctx['deb'], ctx['crd'], None], 'total'
        return dict(layout=XR.layout_bc007_full(info), total=0, prepare=prepare, rows=rows, needs_db=True)

    if rpt == 'BC007':
        view_mode = 'summary' if variant == 'summary' else 'detail'

        def prepare(cur, ctx):
            # đúng câu đếm + tổng của /api/journal → dòng "Cộng lũy kế" khớp màn hình
            cur.execute(f"""SELECT COUNT(*), SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                            FROM dbo.LEDGER_VIEW WITH (NOLOCK) WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}""",
                        [d_from, d_to] + list(org_params))
            r = cur.fetchone()
            ctx['deb'], ctx['crd'] = r[1] or 0, r[2] or 0
            return (r[0] or 0) + 1

        def rows(cur, ctx):
            org_map = {}
            if view_mode == 'detail':
                try:
                    cur.execute("SELECT CAST(ORGANIZATION_ID AS NVARCHAR(100)), ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WITH (NOLOCK)")
                    org_map = {(x[0] or '').strip(): (x[1] or '').strip() for x in cur.fetchall()}
                except Exception:
                    pass
            sql = f"""SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                             ORGANIZATION_ID, TRAN_ID
                      FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                      WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                      ORDER BY TRAN_DATE, TRAN_NO"""
            for r in fetch_rows(cur, sql, [d_from, d_to] + list(org_params)):
                amt = r[6] if r[6] is not None else 0
                tail = [str(r[8] if r[8] is not None else '').strip(), r[1] or '', r[0], r[2] or '', r[3] or '',
                        r[4] or '', amt if r[5] == 'DEB' else None, amt if r[5] == 'CRD' else None]
                if view_mode == 'detail':
                    org = str(r[7] if r[7] is not None else '').strip()
                    yield [org, org_map.get(org, ''), r[0]] + tail, 'data'
                else:
                    yield tail, 'data'
            yield [XR.Span('Cộng lũy kế', 9 if view_mode == 'detail' else 6, 'right'), ctx['deb'], ctx['crd']], 'total'
        return dict(layout=XR.layout_bc007(info, view_mode), total=0, prepare=prepare, rows=rows, needs_db=True)

    if rpt == 'BC008':
        account_id = ','.join(_rx_list(p.get('acc_ids')))
        if not account_id:
            return "Vui lòng chọn Tài khoản để xuất Sổ chi tiết tài khoản."
        acc_clause, acc_params = _acc_like_sql(account_id)
        first_day = date(from_dt.year, 1, 1).strftime("%Y%m%d")

        def prepare(cur, ctx):
            # y hệt get_account_details: dư đầu = BALANCE_VIEW đầu năm + LEDGER_VIEW từ đầu năm tới trước kỳ
            cur.execute(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                            FROM dbo.BALANCE_VIEW WITH (NOLOCK) WHERE {acc_clause} AND TRAN_DATE = ? {org_where}""",
                        acc_params + [first_day] + list(org_params))
            r = cur.fetchone()
            odeb, ocrd = _rx_dec(r[0] if r else 0), _rx_dec(r[1] if r else 0)
            if from_dt > date(from_dt.year, 1, 1):
                cur.execute(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                       SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                                FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                                WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}""",
                            acc_params + [first_day, d_from] + list(org_params))
                r = cur.fetchone()
                if r:
                    odeb += _rx_dec(r[0])
                    ocrd += _rx_dec(r[1])
            cur.execute(f"""SELECT COUNT(*), SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                   SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                            FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                            WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}""",
                        acc_params + [d_from, d_to] + list(org_params))
            r = cur.fetchone()
            ctx.update(odeb=odeb, ocrd=ocrd, deb=_rx_dec(r[1]), crd=_rx_dec(r[2]))
            return (r[0] or 0) + 3

        def rows(cur, ctx):
            open_net = ctx['odeb'] - ctx['ocrd']
            yield [XR.Span('SỐ DƯ ĐẦU KỲ', 5, 'right'), open_net if open_net > 0 else None,
                   -open_net if open_net < 0 else None], 'opening'
            sql = f"""SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                      FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                      WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}
                      ORDER BY TRAN_DATE, TRAN_NO"""
            for r in fetch_rows(cur, sql, acc_params + [d_from, d_to] + list(org_params)):
                amt = r[5] if r[5] is not None else 0
                yield [r[0], r[1] or '', r[0], r[2] or '', r[3] or '',
                       amt if r[4] == 'DEB' else None, amt if r[4] == 'CRD' else None], 'data'
            yield [XR.Span('Cộng phát sinh trong kỳ', 5, 'right'), ctx['deb'], ctx['crd']], 'total'
            close_net = (ctx['odeb'] + ctx['deb']) - (ctx['ocrd'] + ctx['crd'])
            yield [XR.Span('SỐ DƯ CUỐI KỲ', 5, 'right'), close_net if close_net > 0 else None,
                   -close_net if close_net < 0 else None], 'closing'
        return dict(layout=XR.layout_bc008(info), total=0, prepare=prepare, rows=rows, needs_db=True)

    if rpt == 'BC012':
        acc_ids = _rx_list(p.get('acc_ids')) or ["111", "112", "113"]
        contra_ids = _rx_list(p.get('contra_acc_ids'))
        tran_no = str(p.get('tran_no') or '').strip()
        f_date, t_date = from_dt.strftime("%d/%m/%Y"), to_dt.strftime("%d/%m/%Y")
        # Vừa xem xong thì sổ quỹ đã nằm sẵn trong cache (cùng khoá với /api/cash_book) → xuất ngay, khỏi truy vấn lại
        cached = _cashbook_cache.get(_cashbook_key(f_date, t_date, acc_ids, contra_ids, tran_no, org_ids))
        org_filter = (_oc, org_params)

        def prepare(cur, ctx):
            ctx['flat'] = cached if cached is not None else _build_cashbook_flat(
                from_dt, to_dt, acc_ids, contra_ids, tran_no, org_ids, cur=cur, org_filter=org_filter)
            return len(ctx['flat'])
        return dict(layout=XR.layout_bc012(info), total=len(cached) if cached is not None else 0,
                    prepare=prepare, rows=lambda cur, ctx: XR.rows_bc012(ctx['flat']), needs_db=cached is None)

    if rpt == 'BC013':
        mode = 'summary' if variant == 'summary' else 'detail'
        acc_ids = _rx_list(p.get('acc_ids'))
        acc_where, acc_params = "", []
        if acc_ids:
            acc_where = " AND (" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids)) + ")"
            acc_params = [a + "%" for a in acc_ids]
        params = [d_from, d_to] + list(org_params) + acc_params
        base_where = f"DEBIT_CREDIT = 'CRD' AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}"
        group_by = "GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID"

        def prepare(cur, ctx):
            # đúng 2 câu của /api/vat_sales_report: 3 số tổng dưới bảng + số dòng theo chế độ
            cur.execute(f"""SELECT ISNULL(SUM(AMOUNT_ITEM), 0),
                                   ISNULL(SUM(CASE WHEN VAT_TAX_RATE > 0 THEN AMOUNT_ITEM ELSE 0 END), 0),
                                   ISNULL(SUM(AMOUNT), 0)
                            FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}""", params)
            t = cur.fetchone()
            ctx['totals'] = {'total_amount_item': t[0], 'taxable_amount_item': t[1], 'total_vat_amount': t[2]}
            if mode == 'summary':
                cur.execute(f"""SELECT COUNT(*) FROM (SELECT VAT_TRAN_SERIE FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                                WHERE {base_where} {group_by}) AS Grp""", params)
            else:
                cur.execute(f"SELECT COUNT(*) FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}", params)
            return (cur.fetchone()[0] or 0) + 1

        def rows(cur, ctx):
            if mode == 'summary':
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE, ISNULL(PR_DETAIL_NAME,''),
                                 ISNULL(TAX_FILE_NUMBER,''), N'Bán hàng hóa, dịch vụ', ISNULL(SUM(AMOUNT_ITEM),0),
                                 ISNULL(MAX(VAT_TAX_RATE),0), ISNULL(SUM(AMOUNT),0), N''
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where} {group_by}
                          ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO"""
            else:
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE, ISNULL(PR_DETAIL_NAME,''),
                                 ISNULL(TAX_FILE_NUMBER,''), ISNULL(ITEM_NAME,''), ISNULL(AMOUNT_ITEM,0),
                                 ISNULL(VAT_TAX_RATE,0), ISNULL(AMOUNT,0), ISNULL(COMMENTS,'')
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}
                          ORDER BY VAT_TAX_RATE, VAT_TRAN_DATE, VAT_TRAN_NO"""
            stt, s_amt, s_vat = 0, Decimal(0), Decimal(0)
            for r in fetch_rows(cur, sql, params):
                stt += 1
                amt, vat = _rx_dec(r[6]), _rx_dec(r[8])
                s_amt += amt
                s_vat += vat
                yield [stt, (r[0] or '').strip(), (r[1] or '').strip(), r[2], (r[3] or '').strip(),
                       (r[4] or '').strip(), (r[5] or '').strip(), amt, float(r[7] or 0), vat,
                       (r[9] or '').strip()], 'data'
            yield [XR.Span('Tổng cộng', 7, 'center'), s_amt, None, s_vat, None], 'total'
        return dict(layout=XR.layout_bc013(info), total=0, prepare=prepare, rows=rows,
                    after=lambda ctx: XR.bc013_summary_rows(ctx['totals']), needs_db=True)

    return "Báo cáo chưa hỗ trợ xuất."


def _rx_error_text(e):
    msg = str(e)
    low = msg.lower()
    if isinstance(e, PermissionError) or 'permission denied' in low:
        return "Không ghi được file vào thư mục Downloads\\iPOS_Ledger_Studio (thiếu quyền hoặc file đang mở)."
    if '08s01' in low or 'communication link' in low or 'tcp provider' in low:
        return "Mất kết nối tới SQL Server trong lúc xuất. Kiểm tra mạng rồi thử lại."
    if 'no space' in low or 'errno 28' in low:
        return "Ổ đĩa đã đầy, không đủ chỗ ghi file."
    return msg


def _rx_start_job(path, fmt, plan, db_cfg, report_type):
    job_id = uuid.uuid4().hex
    started = time.time()
    with _export_jobs_lock:
        # dọn job đã xong quá 2 giờ — dict này sống suốt vòng đời EXE
        for k in [k for k, j in _export_jobs.items()
                  if j.get('status') != 'running' and started - j.get('started', started) > 7200]:
            _export_jobs.pop(k, None)
        _export_jobs[job_id] = {
            'status': 'running', 'phase': 'prepare', 'current': 0, 'total': int(plan.get('total') or 0),
            'sheet': 0, 'sheets': 0, 'file_path': None, 'filename': os.path.basename(path), 'error': None,
            'cancelled': False, 'started': started, 'elapsed': 0, 'size': 0, 'rows': 0,
            'report_type': report_type, 'format': fmt,
        }

    def upd(**kw):
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            if job is not None:
                job.update(kw)
                job['elapsed'] = round(time.time() - started, 1)

    def cancelled():
        with _export_jobs_lock:
            job = _export_jobs.get(job_id)
            return bool(job and job.get('cancelled'))

    def runner():
        conn, writer = None, None
        tmp = path + '.part'   # ghi ra tên tạm, xong mới đổi tên → không bao giờ lộ file dở dang mang tên thật
        try:
            cur = None
            if plan.get('needs_db'):
                upd(phase='query')
                conn = _make_conn(db_cfg)
                cur = conn.cursor()
            ctx = {}
            total = plan.get('total') or 0
            if plan.get('prepare'):
                total = plan['prepare'](cur, ctx)
                upd(total=total)
            if cancelled():
                raise XR.ExportCancelled()
            W = XR.CsvReportWriter if fmt == 'csv' else XR.XlsxReportWriter
            writer = W(tmp, plan['layout'], total_rows=total, is_cancelled=cancelled,
                       progress=lambda n, s, ss: upd(current=n, sheet=s, sheets=ss))
            first = True
            for item in plan['rows'](cur, ctx):
                if first:
                    upd(phase='write')
                    first = False
                writer.add_row(*item)
            upd(phase='finalize', current=writer.rows_written)
            writer.close(after_rows=plan['after'](ctx) if plan.get('after') else None)
            rows_written, sheets = writer.rows_written, writer.sheet_count
            writer = None
            os.replace(tmp, path)
            upd(status='done', phase='done', file_path=path, size=os.path.getsize(path),
                current=rows_written, total=max(total, rows_written), rows=rows_written, sheet=sheets, sheets=sheets)
        except XR.ExportCancelled:
            _rx_cleanup(writer, tmp)
            upd(status='cancelled', phase='cancelled')
        except Exception as e:
            logger.exception(f"Loi xuat bao cao {report_type}")
            _rx_cleanup(writer, tmp)
            upd(status='error', phase='error', error=_rx_error_text(e))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            with _export_jobs_lock:
                _export_reserved.discard(path.lower())

    threading.Thread(target=runner, daemon=True, name=f"export-{report_type}").start()
    return job_id


def _rx_cleanup(writer, tmp):
    if writer is not None:
        try:
            writer.abort()
        except Exception:
            pass
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass


@app.route("/api/report_export/start", methods=["POST"])
def report_export_start():
    """Khởi tạo job xuất báo cáo → trả job_id; app poll /api/export/status, hủy qua /api/export/cancel."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        rpt = str(data.get('report_type') or '').strip().upper()
        if rpt not in _REPORT_EXPORT_CODES:
            return jsonify({"status": "error", "message": f"Báo cáo {rpt or '?'} chưa hỗ trợ xuất."}), 400
        fmt = 'csv' if str(data.get('format') or '').lower() == 'csv' else 'xlsx'
        db_cfg = session.get('db_config')
        if not db_cfg:
            return jsonify({"status": "error", "message": "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại."}), 401
        info = _rx_header(data.get('header'))
        params = data.get('params') if isinstance(data.get('params'), dict) else {}
        # Bộ lọc đơn vị (_org_filter_sql) và khoá cache sổ quỹ cần session + pool → tính ở đây, dưới khoá DB
        # chung giống mọi endpoint báo cáo; thread nền chỉ nhận kết quả đã tính sẵn.
        with global_db_lock:
            plan = _rx_plan(rpt, str(data.get('variant') or ''), info, params, data.get('payload'))
        if isinstance(plan, str):
            return jsonify({"status": "error", "message": plan}), 400
        path = _rx_reserve_path(data.get('filename') or rpt, fmt)
        job_id = _rx_start_job(path, fmt, plan, db_cfg, rpt)
        return jsonify({"status": "ok", "job_id": job_id, "filename": os.path.basename(path),
                        "dir": os.path.dirname(path)})
    except Exception as e:
        logger.exception("Loi khoi tao xuat bao cao")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    import threading

    import webbrowser
    import time
    import socket

    APP_URL  = 'http://localhost:5050'
    APP_PORT = 5050

    def _find_chromium_browser():
        """Tìm path Chrome/Edge/Brave để mở app ở chế độ standalone (--app)."""
        candidates = []
        if platform.system() == "Windows":
            envs = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                    os.environ.get("LocalAppData", os.path.expanduser(r"~\AppData\Local"))]
            rel_paths = [
                r"Google\Chrome\Application\chrome.exe",
                r"Microsoft\Edge\Application\msedge.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe",
            ]
            for base in envs:
                if not base: continue
                for rel in rel_paths:
                    p = os.path.join(base, rel)
                    if os.path.exists(p):
                        candidates.append(p)
        else:
            # macOS / Linux: trông vào PATH
            for name in ("google-chrome", "chrome", "chromium", "msedge", "brave-browser"):
                from shutil import which
                p = which(name)
                if p: candidates.append(p)
        return candidates[0] if candidates else None

    def _wait_port_ready(host, port, timeout=15):
        """Đợi Flask đã bind port xong rồi mới mở browser."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)
        return False

    def _shutdown_everything(reason=""):
        """Đóng connection pool, kill chính tiến trình mình + mọi process con."""
        try:
            print(f"[shutdown] {reason}")
        except Exception:
            pass
        # Đóng connection pool SQL
        try:
            with _pool_lock:
                for c in list(_conn_pool.values()):
                    try: c.close()
                    except: pass
                _conn_pool.clear()
        except Exception:
            pass
        # Kill toàn bộ process tree của EXE → Flask + bất kỳ child nào
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    f'taskkill /F /T /PID {os.getpid()}',
                    shell=True, capture_output=True
                )
            else:
                os.kill(os.getpid(), 9)
        except Exception:
            os._exit(0)

    def launch_app_window():
        """Mở app dưới dạng cửa sổ standalone. Khi user đóng cửa sổ → tắt server."""
        if not _wait_port_ready("127.0.0.1", APP_PORT):
            webbrowser.open(APP_URL)
            return  # Không track được → server chạy ngầm như cũ

        chromium = _find_chromium_browser()
        if not chromium:
            # Không có Chrome/Edge → fallback browser mặc định (không track được khi đóng)
            webbrowser.open(APP_URL)
            return

        # Profile dir riêng cho app
        if platform.system() == "Windows":
            profile_dir = os.path.join(os.environ.get("LocalAppData", os.path.expanduser(r"~\AppData\Local")),
                                       "iPOS_Ledger_Studio", "AppProfile")
        else:
            profile_dir = os.path.expanduser("~/.ipos_ledger_studio/AppProfile")

        try:
            os.makedirs(profile_dir, exist_ok=True)
        except Exception:
            profile_dir = None

        args = [
            chromium,
            f"--app={APP_URL}",
            "--new-window",
            "--disable-features=Translate",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if profile_dir:
            args.append(f"--user-data-dir={profile_dir}")

        try:
            # close_fds + KHÔNG dùng shell → có handle process thật để wait()
            _t_spawn = time.time()
            proc = subprocess.Popen(args, close_fds=True)
        except Exception:
            webbrowser.open(APP_URL)
            return

        # Block thread này cho tới khi user đóng cửa sổ Chrome --app
        try:
            proc.wait()
        except Exception:
            pass

        # ⚠️ BẪY ĐÃ TỪNG LÀM SERVER "CHẾT NGAY KHI VỪA LÊN" (phát hiện 12/08/2026):
        # Nếu ĐÃ có sẵn 1 Chrome đang dùng chung --user-data-dir này (cửa sổ app cũ chưa đóng
        # hẳn, hoặc process mồ côi còn sót), thì chrome.exe vừa spawn sẽ BÀN GIAO việc mở cửa sổ
        # cho instance cũ rồi TỰ THOÁT NGAY (<1s). proc.wait() trả về tức thì → hiểu nhầm là
        # "user đã đóng cửa sổ" → server taskkill chính nó → EXE thoát mã 1, mọi request sau đó
        # báo "Failed to fetch" dù code hoàn toàn đúng. Triệu chứng điển hình: vừa build xong,
        # chạy EXE là chết ngay, phải đóng hết Chrome mới chạy được.
        # => Thoát quá nhanh = bàn giao, KHÔNG phải user đóng cửa sổ. Giữ server chạy ngầm,
        #    đúng như nhánh dự phòng "không track được" ở trên.
        if time.time() - _t_spawn < 5:
            print("[launcher] Chrome ban giao cho instance cu (thoat <5s) -> giu server chay ngam")
            return

        # User đã đóng cửa sổ → shutdown toàn bộ
        _shutdown_everything("Cua so app da bi dong")

    # Chạy launcher ở thread riêng (không daemon vì cần block để kill khi đóng)
    launcher = threading.Thread(target=launch_app_window, daemon=True)
    launcher.start()

    # Bắt Ctrl+C / signal tắt sạch
    import signal
    def _signal_handler(signum, frame):
        _shutdown_everything(f"Nhan signal {signum}")
    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except Exception:
        pass

    # use_reloader=False để khi đóng gói EXE không spawn process con
    try:
        app.run(host="0.0.0.0", port=APP_PORT, debug=False, use_reloader=False)
    finally:
        _shutdown_everything("Flask exited")
