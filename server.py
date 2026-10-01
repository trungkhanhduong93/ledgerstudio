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
import mimetypes
import re   # _NUM_PREFIX_RE (ô lọc cột số) biên dịch lúc nạp module — trước đây re chỉ import ở gần cuối file
import xlsx_report as XR

# Font Inter đóng kèm bản EXE (vendor/fonts/*.woff2): registry Windows nhiều máy không có kiểu này
# → Flask trả application/octet-stream. Khai báo thẳng cho đúng.
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('image/webp', '.webp')   # ảnh sóc màn đăng nhập (assets/soc-it.webp) — cùng lý do

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


def _load_or_create_secret_key():
    """Khóa ký cookie phiên: KHÔNG ghi cứng (trước đây là 'IACC_SECRET_SUPREME_2026' — nằm luôn trong
    repo Public ⇒ ai cũng giả được cookie đăng nhập). Lần đầu chạy sinh ngẫu nhiên 32 byte, lưu 1 file
    cạnh dữ liệu xuất trên máy (không lên git). Mỗi máy một khóa riêng, không ai đoán được.
    Đổi khóa ⇒ cookie cũ hết hiệu lực ⇒ người dùng đăng nhập lại 1 lần (chấp nhận được)."""
    try:
        # Tính thư mục lưu ngay tại đây, KHÔNG gọi _export_dir() vì hàm đó định nghĩa sau trong file
        # (khóa được nạp ngay lúc import, trước khi tới _export_dir).
        home = os.path.expanduser("~")
        base = os.path.join(home, "Downloads", "iPOS_Ledger_Studio") if platform.system() == "Windows" \
            else os.path.join(home, "iPOS_Ledger_Studio")
        os.makedirs(base, exist_ok=True)
        key_path = os.path.join(base, '.session_key')
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                data = f.read().strip()
            if len(data) >= 32:
                return data
        key = os.urandom(32)
        with open(key_path, 'wb') as f:
            f.write(key)
        return key
    except Exception:
        # Không ghi được file (thư mục chỉ đọc…) → khóa ngẫu nhiên trong RAM: vẫn an toàn,
        # chỉ là mỗi lần khởi động lại app thì phải đăng nhập lại.
        return os.urandom(32)


app.secret_key = _load_or_create_secret_key()
# Chỉ cho chính trang app (localhost:5050) gọi API. Trước đây CORS phản chiếu MỌI origin kèm credentials
# ⇒ web lạ user mở có thể gọi app và đọc kết quả. Giới hạn về đúng localhost.
CORS(app, supports_credentials=True,
     origins=[r"http://localhost:5050", r"http://127.0.0.1:5050"])


# ===== PHIÊN ĐĂNG NHẬP CHỈ SỐNG TRONG 1 LẦN CHẠY APP (v1.10.8, Trum 30/09) =====
# Trước đây phiên là cookie Flask: chỉ KÝ (khoá .session_key lưu file), KHÔNG mã hoá, chứa nguyên db_config kể cả mật khẩu → ai
# đọc được cookie là đọc được mật khẩu; cửa sổ Chrome cũ còn sống (bàn giao, chạy nền) thì mở lại app vẫn vào thẳng vì khoá cũ còn
# khớp. Nay phiên nằm trong RAM của tiến trình, cookie chỉ giữ 1 mã ngẫu nhiên → tắt app (tiến trình chết) là hết phiên, lần mở sau
# phải đăng nhập lại; F5 trong cùng lần chạy vẫn giữ phiên. Mọi chỗ gọi session.get('db_config') giữ nguyên.
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
import secrets

_ram_sessions = {}
_ram_sessions_lock = threading.Lock()
_SID_COOKIE = "ds_sid"


class _RamSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None):
        def on_update(s):
            s.modified = True
        CallbackDict.__init__(self, initial, on_update)
        self.sid = sid
        self.modified = False


class _RamSessionInterface(SessionInterface):
    def open_session(self, app, request):
        sid = request.cookies.get(_SID_COOKIE)
        with _ram_sessions_lock:
            data = _ram_sessions.get(sid) if sid else None
        return _RamSession(dict(data) if data else None, sid if data else None)

    def save_session(self, app, sess, response):
        if not sess.modified:
            return
        if not sess:   # đăng xuất: bỏ phiên + xoá cookie
            if sess.sid:
                with _ram_sessions_lock:
                    _ram_sessions.pop(sess.sid, None)
            response.delete_cookie(_SID_COOKIE, path="/")
            return
        sid = sess.sid or secrets.token_urlsafe(32)
        with _ram_sessions_lock:
            _ram_sessions[sid] = dict(sess)
        if sid != sess.sid:
            response.set_cookie(_SID_COOKIE, sid, httponly=True, samesite="Strict", path="/")


app.session_interface = _RamSessionInterface()


@app.before_request
def _only_localhost():
    """Chặn DNS rebinding: trang web lạ trỏ tên miền của nó về 127.0.0.1 thì trình duyệt coi là CÙNG nguồn → CORS không chặn,
    đọc được API và đăng nhập bằng mật khẩu đã lưu (v1.10.8). App luôn mở bằng http://localhost:5050 → chỉ nhận Host
    localhost / 127.0.0.1."""
    host = (request.host or '').rsplit(':', 1)[0].lower()
    if host not in ('localhost', '127.0.0.1'):
        return jsonify({"status": "error", "message": "Chỉ mở được từ chính ứng dụng trên máy này."}), 403


def _is_local_request():
    """True nếu request đến từ chính trang app (localhost), hoặc không có Origin/Referer (gọi trực tiếp,
    không phải từ trang web khác). Dùng chặn web lạ ép các hành động nhạy cảm (cập nhật, cài driver)
    mà KHÔNG bắt đăng nhập — để nút 'Cập nhật ngay' ở màn hình đăng nhập vẫn bấm được."""
    from urllib.parse import urlparse
    for hdr in ('Origin', 'Referer'):
        val = request.headers.get(hdr)
        if val:
            host = (urlparse(val).hostname or '').lower()
            if host not in ('localhost', '127.0.0.1'):
                return False
    return True

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
        _t_gz = time.perf_counter()
        buf = _io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=5) as gz:
            gz.write(data)
        compressed = buf.getvalue()
        if response.headers.get('Server-Timing'):
            response.headers['Server-Timing'] += f", gzip;dur={(time.perf_counter() - _t_gz) * 1000:.1f}"
        response.set_data(compressed)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(compressed))
        response.headers['Vary'] = 'Accept-Encoding'
    except Exception:
        pass
    return response


# ===== DỊCH LỖI SANG TIẾNG VIỆT (v1.10.6, Trum yêu cầu 29/09) =====
# Lỗi gốc của SQL Server / driver ODBC / Windows / Python là tiếng Anh ("[DBNETLIB]ConnectionWrite (10054)…").
# _vi_error_text đổi thành 3 dòng mà app hiển thị tách phần:
#     <chuyện gì xảy ra>
#     Cách khắc phục: <làm gì>
#     Chi tiết kỹ thuật: <mã gốc rút gọn — để IT tra>
# Áp ở MỘT chỗ: _vi_error_response (after_request) sửa trường message / error / error_message của mọi JSON báo lỗi,
# giữ bản gốc ở <trường>_raw. Thêm endpoint mới không cần làm gì. Lỗi mới hay gặp → thêm 1 luật vào _VI_ERR_RULES.
import json   # json.dumps trong _vi_error_response (bản cũ chỉ import json ở gần cuối file)
_VI_FIX = "Cách khắc phục:"
_VI_DETAIL = "Chi tiết kỹ thuật:"
_VI_CHARS = re.compile(r'[À-ỹđĐ]')
_TECH_HINT = re.compile(r"\[Microsoft\]|\[ODBC|\[SQL Server\]|\[DBNETLIB\]|\('[0-9A-Z]{5}'|Traceback|Error\b|Exception\b|errno|WinError", re.I)
_Q = lambda m, i=1: (m.group(i) if m and m.group(i) else '').strip()

# (regex trên chữ gốc — không phân biệt hoa thường, chỉ áp khi ngữ cảnh khớp: None = mọi nơi, 'update' = tải bản cập nhật)
#  → (hàm (match) -> câu chuyện gì xảy ra, cách khắc phục). THỨ TỰ QUAN TRỌNG: luật cụ thể đứng trước luật chung.
_VI_ERR_RULES = [
    (None, r'cancelled by user',
     lambda m: ("Đã huỷ xuất file theo yêu cầu.", "Bấm Xuất lại nếu cần file.")),
    # thư mục lưu file mất giữa lúc ghi (v1.10.9: thư mục lưu theo màn hình có thể là ổ USB / ổ mạng). Lỗi OSError của Python —
    # đứng TRƯỚC luật mạng SQL: "[WinError 64] The specified network name is no longer available" là ổ mạng, không phải SQL.
    (None, r'\[winerror (?:3|21|53|64|67|1231)\]|\[errno 2\] no such file',
     lambda m: ("Không tìm thấy thư mục hoặc ổ đĩa để ghi file — ổ USB / ổ mạng vừa bị ngắt, hoặc thư mục bị xoá.",
                "Cắm lại ổ (ổ mạng thì bật VPN công ty), hoặc bấm Đổi ở dòng \"Lưu vào\" để chọn thư mục khác, rồi xuất lại.")),
    (None, r'cannot open database "([^"]+)"',
     lambda m: (f'Không mở được cơ sở dữ liệu "{_Q(m)}" — sai tên CSDL, hoặc tài khoản SQL chưa được cấp quyền vào CSDL này.',
                "Kiểm tra lại ô Cơ sở dữ liệu (đúng tên, đúng hoa thường). Tên đúng mà vẫn lỗi thì nhờ IT cấp quyền cho tài khoản vào CSDL.")),
    (None, r'password (?:has )?expired|must be changed|18487|18488',
     lambda m: ("Mật khẩu tài khoản SQL Server đã hết hạn hoặc bắt buộc đổi.", "Nhờ IT đặt lại mật khẩu cho tài khoản SQL rồi đăng nhập lại.")),
    (None, r'account is disabled|18470',
     lambda m: ("Tài khoản SQL Server đang bị khoá.", "Nhờ IT mở khoá tài khoản SQL (hoặc dùng tài khoản khác) rồi đăng nhập lại.")),
    # 2 luật riêng: SQLSTATE '28000' đứng TRƯỚC câu "Login failed for user 'x'" → gộp 1 regex là bắt trúng mã, mất tên tài khoản
    (None, r"login failed for user '([^']+)'",
     lambda m: (f"Sai tài khoản hoặc mật khẩu SQL Server (tài khoản {_Q(m)}).",
                "Gõ lại Tài khoản / Mật khẩu (phân biệt chữ hoa thường, tắt bộ gõ tiếng Việt khi gõ mật khẩu). Chắc chắn đúng mà vẫn lỗi thì nhờ IT kiểm tra tài khoản SQL.")),
    (None, r"login failed|\b28000\b|18456",
     lambda m: ("Sai tài khoản hoặc mật khẩu SQL Server.",
                "Gõ lại Tài khoản / Mật khẩu (phân biệt chữ hoa thường, tắt bộ gõ tiếng Việt khi gõ mật khẩu). Chắc chắn đúng mà vẫn lỗi thì nhờ IT kiểm tra tài khoản SQL.")),
    (None, r'ssl provider|certificate chain|certificate verify',
     lambda m: ("Driver ODBC từ chối chứng chỉ bảo mật của máy chủ SQL.",
                "Đăng nhập lại (app dùng driver \"SQL Server\" mặc định). Vẫn lỗi thì nhờ IT kiểm tra chứng chỉ SSL của máy chủ SQL.")),
    (None, r'login timeout expired|does not exist or access denied|server was not found|named pipes provider|'
           r'tcp provider: (?:no such host|the wait operation timed out|a connection attempt failed)|\b08001\b',
     lambda m: ("Không kết nối được máy chủ SQL — máy chưa vào mạng công ty, hoặc tên máy chủ sai.",
                "Bật VPN công ty rồi thử lại. Đã bật VPN mà vẫn lỗi thì kiểm tra lại tên máy chủ và hỏi IT máy chủ SQL có đang chạy không.")),
    (None, r'10054|10053|connectionwrite|connectionread|general network error|communication link failure|\b08s01\b|'
           r'forcibly closed|connection (?:is )?broken|semaphore timeout|specified network name is no longer available',
     lambda m: ("Mất kết nối tới máy chủ SQL giữa chừng — đường mạng (thường là VPN) bị ngắt trong lúc đang lấy dữ liệu.",
                "Kiểm tra VPN công ty còn kết nối rồi thử lại. Dữ liệu lớn (hàng triệu dòng) thì thu hẹp kỳ, lọc theo đơn vị hoặc xuất CSV để rút ngắn thời gian truyền.")),
    (None, r'query timeout expired|\bhyt00\b|timeout expired',
     lambda m: ("Truy vấn chạy quá lâu nên bị máy chủ ngắt.",
                "Thu hẹp kỳ hoặc thêm bộ lọc (đơn vị, tài khoản) rồi thử lại. Máy chủ đang bận (cuối tháng, nhiều người dùng) thì thử lại sau ít phút.")),
    (None, r'deadlock|\b40001\b|1205\)',
     lambda m: ("SQL Server huỷ truy vấn vì tranh chấp dữ liệu với người khác đang ghi sổ cùng lúc.", "Bấm lại lần nữa — thường sẽ chạy được ngay.")),
    (None, r'lock request time out|1222\)',
     lambda m: ("Dữ liệu đang bị một thao tác khác trên máy chủ khoá.", "Đợi ít phút rồi thử lại.")),
    (None, r"permission was denied on the object '([^']+)'|permission was denied|\b229\)|\b230\)",
     lambda m: (f"Tài khoản SQL không có quyền đọc {('“' + _Q(m) + '”') if _Q(m) else 'dữ liệu này'}.",
                "Nhờ IT cấp quyền đọc (db_datareader) cho tài khoản trên CSDL này rồi thử lại.")),
    (None, r"invalid object name '([^']+)'",
     lambda m: (f"CSDL không có bảng/view “{_Q(m)}” — có thể đang chọn nhầm CSDL không phải kế toán iPOS, hoặc CSDL là phiên bản iPOS khác.",
                "Kiểm tra đã đăng nhập đúng CSDL kế toán. Đúng CSDL mà vẫn lỗi thì chụp màn hình gửi người hỗ trợ DataStudio.")),
    (None, r"invalid column name '([^']+)'",
     lambda m: (f"CSDL thiếu cột “{_Q(m)}” mà chức năng này cần (CSDL là phiên bản iPOS khác).",
                "Chụp màn hình gửi người hỗ trợ DataStudio kèm tên CSDL đang dùng.")),
    (None, r'insufficient system memory|\b701\)',
     lambda m: ("Máy chủ SQL thiếu bộ nhớ để chạy truy vấn này.",
                "Thu hẹp kỳ hoặc thêm bộ lọc rồi thử lại. Lỗi lặp lại thường xuyên thì báo IT kiểm tra RAM máy chủ SQL.")),
    (None, r'could not allocate (?:a new page|space)|filegroup is full|transaction log for database .* is full|\b1105\)|\b9002\)',
     lambda m: ("Ổ đĩa máy chủ SQL đã hết chỗ (tempdb / nhật ký giao dịch).",
                "Báo IT dọn dung lượng máy chủ SQL. Trong lúc chờ, thu hẹp kỳ truy vấn cho nhẹ hơn.")),
    (None, r'conversion failed|error converting|arithmetic overflow|out-of-range|out of range value',
     lambda m: ("Trong CSDL có giá trị ngày/số không đọc được (thường do dữ liệu nhập sai định dạng).",
                "Thu hẹp kỳ để tìm chứng từ bị lỗi và sửa trong iPOS. Không tìm được thì chụp màn hình gửi người hỗ trợ DataStudio kèm kỳ đang xem.")),
    (None, r'divide by zero',
     lambda m: ("Máy chủ gặp phép chia cho 0 khi tính số liệu.", "Chụp màn hình gửi người hỗ trợ DataStudio kèm báo cáo và kỳ đang xem.")),
    (None, r'connection is busy with results for another',
     lambda m: ("Kết nối SQL đang bận với truy vấn trước.", "Đợi truy vấn trước chạy xong rồi bấm lại. Vẫn lỗi thì Đăng xuất rồi đăng nhập lại.")),
    (None, r'data source name not found|\bim002\b|can\'t open lib|specified driver could not be loaded',
     lambda m: ("Máy này chưa cài driver ODBC cho SQL Server.", "Cài \"ODBC Driver 17 for SQL Server\" (hoặc nhờ IT cài) rồi mở lại DataStudio.")),
    (None, r'incorrect syntax near|\b102\)|\b156\)|is not a recognized built-in function',
     lambda m: ("Máy chủ SQL không chạy được câu truy vấn của DataStudio — thường do SQL Server đời cũ hơn chức năng này cần.",
                "Chụp màn hình gửi người hỗ trợ DataStudio kèm tên CSDL và phiên bản SQL Server.")),
    # --- tải bản cập nhật từ GitHub (chỉ áp cho /api/check_update, /api/apply_update, /api/update_progress)
    ('update', r'winerror 5\b|access is denied|permission denied|winerror 32|being used by another process',
     lambda m: ("Không thay được file DataStudio — thư mục chứa file không cho ghi (vd Program Files), hoặc phần mềm diệt virus đang khoá file.",
                "Chép iPOS_Ledger_Studio.exe ra Desktop hoặc Documents rồi chạy từ đó và cập nhật lại. Vẫn lỗi thì tải tay bản mới ở trang phát hành GitHub.")),
    ('update', r'http error 403|rate limit',
     lambda m: ("GitHub tạm chặn vì máy này (hoặc cả mạng công ty) hỏi quá nhiều lần trong 1 giờ.", "Đợi khoảng 1 giờ rồi mở lại DataStudio.")),
    ('update', r'urlopen error|getaddrinfo|name or service|timed out|remote end closed|connection (?:reset|refused|aborted)|'
               r'certificate_verify_failed|ssl|http error|winerror 100\d\d|incompleteread',
     lambda m: ("Không tải được bản cập nhật từ internet.",
                "Kiểm tra máy vào được internet rồi thử lại. Mạng công ty chặn GitHub thì nhờ IT mở github.com và objects.githubusercontent.com.")),
    # --- máy người dùng (ghi file, bộ nhớ)
    (None, r'no space left|errno 28|not enough space on the disk|winerror 112',
     lambda m: ("Ổ đĩa máy này đã đầy.", "Xoá bớt file trong Downloads\\iPOS_Ledger_Studio hoặc dọn ổ C rồi làm lại.")),
    (None, r'permission denied|errno 13|winerror 5\b|access is denied|winerror 32|being used by another process',
     lambda m: ("Không ghi được file — file cùng tên đang mở trong Excel, hoặc thư mục không cho ghi.",
                "Đóng file đó trong Excel rồi làm lại, hoặc đổi tên file.")),
    (None, r'memoryerror|out of memory|cannot allocate memory',
     lambda m: ("Máy này hết bộ nhớ khi xử lý chừng này dữ liệu.", "Đóng bớt chương trình khác, thu hẹp kỳ hoặc xuất CSV thay cho Excel.")),
]
_VI_ERR_COMPILED = [(ctx, re.compile(p, re.I), fn) for ctx, p, fn in _VI_ERR_RULES]


def _err_brief(raw):
    """Chữ gốc rút gọn cho dòng "Chi tiết kỹ thuật": SQLSTATE · câu lỗi ĐẦU TIÊN, bỏ tiền tố [Microsoft][ODBC …] và tên
    hàm ODBC "(SQLExecDirectW)". Vd "01000 · [DBNETLIB]ConnectionWrite (send()). (10054)"."""
    raw = re.sub(r"['\"]\)\s*$", '', str(raw or '').strip())                  # đuôi tuple của pyodbc: …')
    st = re.search(r"^\('([0-9A-Z]{5})'", raw)
    body = re.sub(r"^\('[0-9A-Z]{5}',\s*['\"]?", '', raw)
    body = re.split(r";\s*\[[0-9A-Z]{5}\]", body)[0]                           # pyodbc nối nhiều câu bằng "; [SQLSTATE]"
    body = re.sub(r"\[(?:Microsoft|ODBC[^\]]*|SQL Server|SQL Native Client[^\]]*|[0-9A-Z]{5})\]\s*", '', body)
    body = re.sub(r"\s*\(SQL[A-Za-z]+\)", '', body)
    body = re.sub(r"\s+", ' ', re.sub(r"\\r\\n|\\n", ' ', body)).strip()
    if len(body) > 180:
        body = body[:180].rsplit(' ', 1)[0] + '…'
    return f"{st.group(1)} · {body}" if st and body else (body or raw[:180])


def _vi_error_text(err, ctx=None):
    """Lỗi (exception hoặc chuỗi) → 3 dòng tiếng Việt (xem đầu khối). Câu tiếng Việt sẵn (không có dấu vết lỗi kỹ thuật)
    → giữ nguyên. Đã dịch rồi → giữ nguyên (gọi lại nhiều lần an toàn)."""
    raw = str(err or '').strip()
    if isinstance(err, MemoryError):
        raw = raw or 'MemoryError'
    if not raw or _VI_FIX in raw:
        return raw
    for rctx, rx, fn in _VI_ERR_COMPILED:
        if rctx is not None and rctx != ctx:
            continue
        m = rx.search(raw)
        if m:
            what, fix = fn(m)
            return f"{what}\n{_VI_FIX} {fix}\n{_VI_DETAIL} {_err_brief(raw)}"
    if _VI_CHARS.search(raw) and not _TECH_HINT.search(raw):
        return raw
    return (f"{'Không tải được bản cập nhật.' if ctx == 'update' else 'Có lỗi chưa rõ nguyên nhân.'}\n"
            f"{_VI_FIX} Thử lại. Vẫn lỗi thì chụp màn hình này gửi người hỗ trợ DataStudio.\n{_VI_DETAIL} {_err_brief(raw)}")


@app.after_request
def _vi_error_response(response):
    """Dịch trường lỗi của MỌI JSON báo lỗi (xem khối trên). Chạy TRƯỚC _gzip_response (Flask gọi after_request
    ngược thứ tự khai báo) nên luôn thấy JSON chưa nén. Chỉ đụng JSON nhỏ (< 256 KB) — dữ liệu bảng lớn không bị parse lại."""
    try:
        if response.direct_passthrough or response.is_streamed or not response.is_json:
            return response
        if (response.content_length or 0) > 256 * 1024:
            return response
        # lọc rẻ trước khi parse: phản hồi thành công (đa số) không có chữ "error" → bỏ qua, khỏi json.loads
        if response.status_code < 400 and b'"error"' not in response.get_data():
            return response
        data = response.get_json(silent=True)
        if not isinstance(data, dict):
            return response
        failed = response.status_code >= 400 or data.get('status') == 'error'
        if not failed:
            return response
        ctx = 'update' if request.path in ('/api/check_update', '/api/apply_update', '/api/update_progress') else None
        changed = False
        for k in ('message', 'error', 'error_message'):
            v = data.get(k)
            if isinstance(v, str) and v:
                t = _vi_error_text(v, ctx)
                if t != v:
                    data[k], data[k + '_raw'] = t, v
                    changed = True
        if changed:
            response.set_data(json.dumps(data, ensure_ascii=False))
    except Exception:
        logger.exception("Loi dich thong bao loi")
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
    if filename.startswith("vendor/"):
        # Thư viện đóng kèm bản EXE (React, xlsx, font — xem webbuild/build.js): tên file đã kèm số phiên bản
        # (react-18.3.1…, font có mã băm) → cho giữ lâu, trình duyệt khỏi tải + dịch lại JS mỗi lần mở app.
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

def get_connection():
    """Trả connection từ pool, tạo mới nếu chưa có hoặc đã chết."""
    db_config = session.get('db_config')
    if not db_config:
        raise Exception("Vui lòng đăng nhập SQL Server trước!")
    return _pool_get(_pool_key(db_config), db_config)


def get_side_connection():
    """Kết nối PHỤ cùng tài khoản — chỉ để /api/ledger chạy COUNT+SUM song song với truy vấn lấy trang.
    An toàn luồng: chỉ get_ledger dùng, get_ledger chạy dưới global_db_lock (@with_db_lock) và luôn join luồng đếm
    trước khi trả về → không bao giờ 2 luồng dùng chung một kết nối pyodbc cùng lúc."""
    db_config = session.get('db_config')
    if not db_config:
        raise Exception("Vui lòng đăng nhập SQL Server trước!")
    return _pool_get(_pool_key(db_config) + _SIDE_SUFFIX, db_config)


_SIDE_SUFFIX = ':side'


def _drop_side_connection():
    """Bỏ kết nối phụ hỏng (lượt sau tự mở lại)."""
    db_config = session.get('db_config')
    if not db_config:
        return
    key = _pool_key(db_config) + _SIDE_SUFFIX
    with _pool_lock:
        conn = _conn_pool.pop(key, None)
        _conn_last_used.pop(key, None)
    if conn:
        try: conn.close()
        except: pass


def _pool_get(key, db_config):
    """Lấy connection theo key trong pool, tạo mới nếu chưa có hoặc đã chết."""
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
    """Đóng connection trong pool khi logout (cả kết nối phụ của /api/ledger)."""
    if not db_config:
        return
    key = _pool_key(db_config)
    for k in (key, key + _SIDE_SUFFIX):
        with _pool_lock:
            conn = _conn_pool.pop(k, None)
            _conn_last_used.pop(k, None)   # bỏ luôn mốc thời gian, giữ 2 dict luôn khớp nhau
        if conn:
            try: conn.close()
            except: pass


# SQL Server có nhận OFFSET … FETCH (2012+) không — dò 1 lần mỗi (server, database, user). 2008 → False → giữ ROW_NUMBER.
_offset_ok = {}


def _supports_offset(conn):
    key = _pool_key(session.get('db_config') or {})
    if key not in _offset_ok:
        try:
            conn.cursor().execute("SELECT 1 AS x ORDER BY x OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY").fetchall()
            _offset_ok[key] = True
        except Exception:
            _offset_ok[key] = False
    return _offset_ok[key]


def _server_timing(tm, desc=''):
    """{'count': 1.23 (giây), …} → header Server-Timing (ms). App đọc header này để hiện thời gian từng khâu."""
    parts = [f"{k};dur={v * 1000:.1f}" for k, v in tm.items()]
    if desc:
        parts.append(f'mode;desc="{desc}"')
    return ", ".join(parts)

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
    if not _is_local_request():
        return jsonify({"success": False, "message": "Chỉ thao tác từ chính ứng dụng."}), 403
    success, message = install_odbc_driver()
    return jsonify({"success": success, "message": message})

_LOGIN_WAIT = 8  # giây — kết nối qua VPN bình thường mất dưới 2 s

def _make_conn_capped(db_config, wait=_LOGIN_WAIT):
    """_make_conn nhưng chờ tối đa `wait` giây. Driver "SQL Server" bỏ qua timeout=5 khi IP không tới được
    (đo 27/09: 47,7 s mới báo lỗi; tên sai 11,2 s) → chạy trong luồng riêng, quá giờ thì báo TimeoutError.
    Luồng đó chạy nốt tới khi driver trả về; lỡ nối được thì tự đóng kết nối."""
    box, lock = {}, threading.Lock()

    def run():
        try:
            box['conn'] = _make_conn(db_config)
        except Exception as e:
            box['err'] = e
        with lock:
            box['done'] = True
            late = box.get('late')
        if late and box.get('conn') is not None:
            try:
                box['conn'].close()
            except Exception:
                pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(wait)
    with lock:
        if not box.get('done'):
            box['late'] = True
            raise TimeoutError(f"Quá {wait} giây chưa kết nối được máy chủ")
    if 'err' in box:
        raise box['err']
    return box['conn']

def _login_error_message(e, server_name):
    """Đổi lỗi đăng nhập sang câu người dùng hiểu được.
    08001 (driver "SQL Server" báo "SQL Server does not exist or access denied" — DBNETLIB) / HYT00 (hết giờ chờ)
    / quá _LOGIN_WAIT giây = máy không tới được máy chủ: gần như luôn do chưa bật VPN công ty.
    Sai mật khẩu là 28000, không vào nhánh này. Loại 'SSL': ODBC Driver 18 báo lỗi chứng chỉ cũng mang mã 08001."""
    state = e.args[0] if isinstance(e, pyodbc.Error) and e.args else ''
    text = str(e)
    if isinstance(e, TimeoutError) or ((state in ('08001', 'HYT00') or '[08001]' in text) and 'SSL' not in text):
        return (f'Không kết nối được máy chủ "{server_name}" — máy chưa vào mạng công ty.' + '\n'
                f'{_VI_FIX} Bật VPN công ty rồi đăng nhập lại. Đã bật VPN mà vẫn lỗi thì kiểm tra lại tên máy chủ.' + '\n'
                f'{_VI_DETAIL} ' + (_err_brief(text) if text else f'quá {_LOGIN_WAIT} giây chưa kết nối được'))
    return _vi_error_text(e)


# ===== KẾT NỐI ĐÃ LƯU (v1.10.8, Trum 30/09): màn đăng nhập "Kết nối gần đây" =====
# Tối đa _SAVED_MAX kết nối dùng gần nhất (máy chủ, CSDL, tài khoản, driver, lần dùng cuối) ở
# %LocalAppData%\iPOS_Ledger_Studio\saved_logins.json — cạnh AppProfile của cửa sổ app, không nằm trong Downloads.
# Mật khẩu (khi để "Ghi nhớ mật khẩu") mã hoá bằng DPAPI của Windows theo tài khoản Windows đang đăng nhập: user khác / máy khác
# chép file đi cũng không giải được. Mật khẩu KHÔNG bao giờ gửi ngược về trang: đăng nhập bằng thẻ đã lưu chỉ gửi saved_id,
# máy chủ tự giải mã. Lưu hỏng / không mã hoá được thì bỏ qua — không bao giờ làm hỏng lần đăng nhập.
import base64

_SAVED_MAX = 5
_saved_lock = threading.Lock()
_DPAPI_ENTROPY = b"DataStudio.saved_logins.v1"


def _saved_logins_path():
    if platform.system() == "Windows":
        base = os.path.join(os.environ.get("LocalAppData", os.path.expanduser(r"~\AppData\Local")), "iPOS_Ledger_Studio")
    else:
        base = os.path.expanduser("~/.ipos_ledger_studio")
    return os.path.join(base, "saved_logins.json")


def _dpapi(data, protect):
    """CryptProtectData / CryptUnprotectData (crypt32) qua ctypes — không cần pywin32. Lỗi → OSError."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    src = ctypes.create_string_buffer(data, len(data))
    ent = ctypes.create_string_buffer(_DPAPI_ENTROPY, len(_DPAPI_ENTROPY))
    b_in = Blob(len(data), ctypes.cast(src, ctypes.c_void_p))
    b_ent = Blob(len(_DPAPI_ENTROPY), ctypes.cast(ent, ctypes.c_void_p))
    b_out = Blob()
    if not fn(ctypes.byref(b_in), None, ctypes.byref(b_ent), None, None, 0x1, ctypes.byref(b_out)):   # 0x1 = UI_FORBIDDEN
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(b_out.pbData, b_out.cbData)
    finally:
        kernel32.LocalFree(b_out.pbData)


def _pw_protect(pw):
    """Mật khẩu → chuỗi base64 đã mã hoá DPAPI. None: mật khẩu rỗng / không phải Windows / mã hoá lỗi (lưu kết nối không mật khẩu)."""
    if not pw or platform.system() != "Windows":
        return None
    try:
        return base64.b64encode(_dpapi(pw.encode("utf-8"), True)).decode("ascii")
    except Exception:
        logger.exception("Khong ma hoa duoc mat khau luu")
        return None


def _pw_unprotect(blob):
    """None nếu không có / không giải được (file chép từ user Windows khác, hỏng) → trang hỏi lại mật khẩu."""
    if not blob or platform.system() != "Windows":
        return None
    try:
        return _dpapi(base64.b64decode(blob), False).decode("utf-8")
    except Exception:
        return None


def _saved_key(server, database, user):
    raw = "|".join(str(x or "").strip().lower() for x in (server, database, user))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _saved_read():
    try:
        with open(_saved_logins_path(), "r", encoding="utf-8") as f:
            items = json.load(f).get("items") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("server") and x.get("database") and x.get("user")]


def _saved_public(items):
    """Danh sách gửi trang — KHÔNG có mật khẩu, chỉ cờ has_pw."""
    return [{"id": _saved_key(x["server"], x["database"], x["user"]), "server": x["server"], "database": x["database"],
             "user": x["user"], "has_pw": bool(x.get("pw")), "last_used": x.get("last_used") or 0} for x in items]


def _saved_write(items):
    path = _saved_logins_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "items": items}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _saved_put(cfg, remember):
    """Đưa kết nối vừa đăng nhập được lên đầu danh sách. remember True → lưu (thay) mật khẩu; False → bỏ mật khẩu đã lưu của kết
    nối này; None → giữ nguyên (đăng nhập bằng thẻ đã lưu, không gõ lại mật khẩu)."""
    try:
        with _saved_lock:
            key = _saved_key(cfg["server"], cfg["database"], cfg["user"])
            items = _saved_read()
            old = next((x for x in items if _saved_key(x["server"], x["database"], x["user"]) == key), None)
            pw = old.get("pw") if old else None
            if remember is True:
                pw = _pw_protect(cfg["password"])
            elif remember is False:
                pw = None
            entry = {"server": cfg["server"], "database": cfg["database"], "user": cfg["user"],
                     "driver": cfg.get("driver") or "SQL Server", "pw": pw, "last_used": int(time.time())}
            rest = [x for x in items if _saved_key(x["server"], x["database"], x["user"]) != key]
            _saved_write([entry] + rest[:_SAVED_MAX - 1])
    except Exception:
        logger.exception("Khong luu duoc ket noi gan day")


@app.route("/api/saved_logins")
def saved_logins():
    """Public (màn đăng nhập gọi trước khi có phiên). Chỉ tên máy chủ / CSDL / tài khoản — mật khẩu không bao giờ ra khỏi máy chủ."""
    return jsonify({"status": "ok", "items": _saved_public(_saved_read()), "can_save_pw": platform.system() == "Windows"})


@app.route("/api/saved_logins/delete", methods=["POST"])
def saved_logins_delete():
    sid = str((request.get_json(silent=True) or {}).get("id") or "")
    with _saved_lock:
        items = _saved_read()
        keep = [x for x in items if _saved_key(x["server"], x["database"], x["user"]) != sid]
        if len(keep) != len(items):
            try:
                _saved_write(keep)
            except OSError as e:
                return jsonify({"status": "error", "message": str(e), "items": _saved_public(items)}), 500
    return jsonify({"status": "ok", "items": _saved_public(keep)})


def _is_login_rejected(e):
    """Sai tài khoản / mật khẩu (28000, 18456) — thẻ đã lưu thì trang mở ô nhập lại mật khẩu."""
    text = str(e)
    return (isinstance(e, pyodbc.Error) and e.args and e.args[0] == '28000') or '18456' in text or 'login failed' in text.lower()


@app.route("/api/login", methods=["POST"])
def login():
    data, saved = {}, None
    try:
        body = request.json
        remember = body.get('remember') is not False
        if body.get('saved_id'):
            # Thẻ "Kết nối gần đây": máy chủ tự lấy mật khẩu đã lưu; trang chỉ gửi mật khẩu khi người dùng gõ lại
            saved = next((x for x in _saved_read()
                          if _saved_key(x["server"], x["database"], x["user"]) == str(body['saved_id'])), None)
            if not saved:
                return jsonify({"status": "error", "items": _saved_public(_saved_read()),
                                "message": "Kết nối này không còn trong danh sách đã lưu. Chọn kết nối khác hoặc nhập lại thông tin."}), 404
            typed = str(body.get('password') or '')
            pw = typed or _pw_unprotect(saved.get('pw'))
            if not pw:
                return jsonify({"status": "error", "need_password": True,
                                "message": "Không đọc được mật khẩu đã lưu trên máy này. Nhập lại mật khẩu." if saved.get('pw')
                                else "Nhập mật khẩu để kết nối."}), 401
            data = {'server': saved['server'], 'database': saved['database'], 'user': saved['user'],
                    'driver': saved.get('driver') or 'SQL Server', 'password': pw}
            if not typed:
                remember = None
        else:
            data = {k: str(body.get(k) or '').strip() for k in ('server', 'database', 'user')}
            data['password'] = str(body.get('password') or '')
            data['driver'] = str(body.get('driver') or 'SQL Server')
        # Nếu đã login trước đó với config khác → đóng connection cũ
        old = session.get('db_config')
        if old:
            close_pool_for(old)

        # Test kết nối bằng cách tạo conn mới và lưu vào pool luôn
        conn = _make_conn_capped(data)
        # Giữ lại trong pool (không close)
        key = _pool_key(data)
        with _pool_lock:
            _conn_pool[key] = conn

        session['db_config'] = data
        _meta_cache.pop(data.get('database'), None)
        _saved_put(data, remember)
        return jsonify({"status": "ok", "message": "Kết nối SQL Server thành công!",
                        "server": data['server'], "database": data['database']})
    except Exception as e:
        res = {"status": "error", "message": _login_error_message(e, data.get('server', ''))}
        if saved is not None and _is_login_rejected(e):
            res["need_password"] = True
        return jsonify(res), 401

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
        pr_detail_classes = []
        try:
            cursor.execute("SELECT CAST(PR_DETAIL_CLASS_ID AS NVARCHAR(100)), PR_DETAIL_CLASS_NAME FROM dbo.DM_PR_DETAIL_CLASS WITH (NOLOCK) WHERE ACTIVE=1 ORDER BY PR_DETAIL_CLASS_ID")
            pr_detail_classes = [{"id": (r[0] or '').strip(), "name": r[1] or ''} for r in cursor.fetchall() if r[0]]
        except Exception:
            pass

        result = {
            "status": "ok",
            "db_info": {"database": db_name},
            "company": company,
            "global_total": global_total,
            "accounts": accounts, "orgs": orgs, "pr_details": pr_details,
            "pr_detail_classes": pr_detail_classes,
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

_NUM_PREFIX_RE = re.compile(r"-?\d*\.?\d*")


def _num_prefix_where(args, colmap):
    """Ô lọc cột số (v1.10.2): args['n_<ID>'] = chữ số người dùng gõ. So với số ĐANG HIỆN trên màn hình — làm tròn đúng số
    lẻ hiển thị (fmtInt 0, fmtNum 2), đổi ra chữ không dấu phẩy — phải BẮT ĐẦU bằng chữ số đã gõ: 145 khớp 145; 1,450;
    145,000; không khớp 2,145. Số âm phải gõ '-'. colmap: {ID: (biểu thức SQL, số lẻ)}; biểu thức None = DB không có cột đó
    (màn hình để trống) → 1=0. Gõ thứ không phải số → 1=0 (trên trang cũng không dòng nào khớp). Luật khớp với gridMatch."""
    clauses, params = [], []
    for cid, (expr, dec) in colmap.items():
        v = re.sub(r"[,\s%]", "", args.get("n_" + cid, "") or "")
        if not v:
            continue
        if expr is None or not _NUM_PREFIX_RE.fullmatch(v):
            clauses.append("1=0")
            continue
        clauses.append(f"CONVERT(VARCHAR(50), CAST(ROUND({expr}, {dec}) AS DECIMAL(38, {dec}))) LIKE ?")
        params.append(v + "%")
    return clauses, params


# Cột số từng bảng cho ô lọc: (biểu thức, số lẻ đang hiện). Thuế % hiện nguyên giá trị → so 4 số lẻ.
LEDGER_NUM_SEARCH = {
    "DEBIT":  ("CASE WHEN L.DEBIT_CREDIT = 'DEB' THEN L.AMOUNT END", 2),
    "CREDIT": ("CASE WHEN L.DEBIT_CREDIT = 'CRD' THEN L.AMOUNT END", 2),
}
PURCHASE_NUM_SEARCH = {
    "QUANTITY": ("P.QUANTITY", 2), "QUANTITY_WH": ("P.QUANTITY_WH", 2), "UNIT_PRICE": ("P.UNIT_PRICE", 2),
    "DISCOUNT_AMOUNT": ("P.DISCOUNT_AMOUNT", 0), "PURCHASE_COST": ("P.PURCHASE_COST", 2), "VAT_TAX_RATE": ("P.VAT_TAX_RATE", 4),
    "VAT_TAX_AMOUNT": ("P.VAT_TAX_AMOUNT", 0), "TOTAL_AMOUNT": ("P.TOTAL_AMOUNT", 0),
}
WAREHOUSE_NUM_SEARCH = {
    "QUANTITY": ("W.QUANTITY", 2), "QUANTITY_EXTRA": ("W.QUANTITY_EXTRA", 2), "UNIT_PRICE": ("W.UNIT_PRICE", 2), "AMOUNT": ("W.AMOUNT", 0),
}
WAREHOUSE_BALANCE_NUM_SEARCH = {   # màn hình hiện ô trống là 0.00 (fmtQty2)
    "QUANTITY": ("ISNULL(WBA.QUANTITY, 0)", 2), "QUANTITY_ADJ": ("ISNULL(WBA.QUANTITY_ADJ, 0)", 2),
}
SALE_NUM_SEARCH = {
    "QUANTITY": ("S.QUANTITY", 2), "UNIT_PRICE": ("S.UNIT_PRICE", 2), "AMOUNT": ("S.AMOUNT", 0), "DISCOUNT_AMOUNT": ("S.DISCOUNT_AMOUNT", 0),
    "VAT_TAX_RATE": ("S.VAT_TAX_RATE", 4), "VAT_TAX_AMOUNT": ("S.VAT_TAX_AMOUNT", 0), "TOTAL_AMOUNT": ("S.TOTAL_AMOUNT", 0),
    "COG_AMOUNT": ("S.COG_AMOUNT", 0),
}
SALE_EXTRA_NUM_SEARCH = ("INCOME_AMOUNT", "VAT_INCOME_AMOUNT")   # cột phụ SALE_VIEW — chỉ lọc khi DB có (Bẫy 5)
VOUCHER_NUM_SEARCH = {"AMOUNT": ("D.AMOUNT", 0)}


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

    n_clauses, n_params = _num_prefix_where(request_args, LEDGER_NUM_SEARCH)
    clauses += n_clauses
    params += n_params
    return " AND ".join(clauses), params, join_clauses, join_params

@app.route("/api/ledger")
@with_db_lock
def get_ledger():
    try:
        t_start   = time.perf_counter()
        tm        = {}   # thời gian từng khâu (giây) → header Server-Timing
        page      = int(request.args.get("page",     1))
        page_size = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        # Frontend gửi known_* khi BỘ LỌC không đổi so với lần đếm trước (đổi trang, đổi số dòng/trang, sắp xếp)
        # → dùng lại tổng, khỏi quét lại toàn bộ dòng. Bấm "Truy vấn" thì frontend không gửi → luôn đếm lại.
        known_total  = request.args.get("known_total")
        known_deb    = request.args.get("known_deb")
        known_crd    = request.args.get("known_crd")
        skip_count   = known_total is not None and not export_all

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
            offset_sql = f"""
                SELECT {BASE_COLS}
                {JOIN_TABLES}
                WHERE {where_sql}
                AND {join_filter}
                ORDER BY {order_by_sql}
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
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
            offset_sql = f"""
                SELECT {BASE_COLS}
                FROM dbo.LEDGER L WITH (NOLOCK)
                WHERE {where_sql}
                ORDER BY {order_by_sql}
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
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
            # Lấy trang: OFFSET/FETCH khi DB nhận (SQL Server 2012+), không thì ROW_NUMBER như cũ (2008).
            use_offset = _supports_offset(conn)
            modes = ['offset' if use_offset else 'rownum']
            # COUNT + SUM (quét MỌI dòng khớp lọc) chạy SONG SONG trên kết nối phụ trong lúc kết nối chính lấy trang:
            # chờ = khâu lâu hơn, thay vì cộng cả hai. Không mở được kết nối phụ → đếm tuần tự như cũ.
            worker, box = None, {}
            if not skip_count:
                try:
                    side = get_side_connection()
                except Exception:
                    side = None
                if side is not None:
                    def _count_job():
                        t = time.perf_counter()
                        try:
                            c2 = side.cursor()
                            c2.execute(count_sql, count_params)
                            box['row'] = c2.fetchone()
                        except Exception as e:
                            box['err'] = e
                        box['dur'] = time.perf_counter() - t
                    worker = threading.Thread(target=_count_job, daemon=True)
                    worker.start()
            try:
                t = time.perf_counter()
                if use_offset:
                    cursor.execute(offset_sql, data_params + [offset, page_size])
                else:
                    cursor.execute(paged_sql, data_params + [offset, offset + page_size])
                columns  = [col[0] for col in cursor.description]
                raw_rows = cursor.fetchall()
                tm['page'] = time.perf_counter() - t
            finally:
                if worker is not None:
                    worker.join()   # luôn chờ luồng đếm xong: kết nối phụ không được để lượt sau dùng khi còn đang chạy

            if skip_count:
                total_rows   = int(known_total)
                total_debit  = float(known_deb or 0)
                total_credit = float(known_crd or 0)
                modes.append('count-reuse')
            else:
                if worker is not None and 'err' not in box:
                    count_row = box['row']
                    tm['count'] = box['dur']
                    modes.append('parallel')
                else:
                    if worker is not None:   # kết nối phụ lỗi giữa chừng → bỏ nó, đếm lại trên kết nối chính
                        _drop_side_connection()
                    t = time.perf_counter()
                    cursor.execute(count_sql, count_params)
                    count_row = cursor.fetchone()
                    tm['count'] = time.perf_counter() - t
                    modes.append('sequential')
                total_rows   = count_row[0] or 0
                total_debit  = float(count_row[1] or 0)
                total_credit = float(count_row[2] or 0)

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

        t_build = time.perf_counter()
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
        tm['build'] = time.perf_counter() - t_build

        t = time.perf_counter()
        resp = jsonify({
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
        tm['json'] = time.perf_counter() - t
        tm['total'] = time.perf_counter() - t_start
        resp.headers['Server-Timing'] = _server_timing(tm, "+".join(modes) if not export_all else 'export')   # '+' vì dấu phẩy là dấu tách của header
        return resp
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

    n_clauses, n_params = _num_prefix_where(request_args, PURCHASE_NUM_SEARCH)
    clauses += n_clauses
    params += n_params
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
            SUM(ISNULL(P.TOTAL_AMOUNT,0))    AS S_TOTAL,
            SUM(ISNULL(P.PURCHASE_COST,0))   AS S_PURCHASE_COST
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
            summary = {"quantity": 0, "quantity_wh": 0, "discount": 0, "vat_tax": 0, "total": 0, "purchase_cost": 0}
            qi = {c: i for i, c in enumerate(columns)}
            for r in raw_rows:
                summary["quantity"]    += float(r[qi.get("QUANTITY")]        or 0) if "QUANTITY"        in qi else 0
                summary["quantity_wh"] += float(r[qi.get("QUANTITY_WH")]     or 0) if "QUANTITY_WH"     in qi else 0
                summary["discount"]    += float(r[qi.get("DISCOUNT_AMOUNT")] or 0) if "DISCOUNT_AMOUNT" in qi else 0
                summary["vat_tax"]     += float(r[qi.get("VAT_TAX_AMOUNT")]  or 0) if "VAT_TAX_AMOUNT"  in qi else 0
                summary["total"]       += float(r[qi.get("TOTAL_AMOUNT")]    or 0) if "TOTAL_AMOUNT"    in qi else 0
                summary["purchase_cost"] += float(r[qi.get("PURCHASE_COST")] or 0) if "PURCHASE_COST"  in qi else 0
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"quantity":0,"quantity_wh":0,"discount":0,"vat_tax":0,"total":0,"purchase_cost":0}
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
                    "purchase_cost": float(row[6] or 0),
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

    n_clauses, n_params = _num_prefix_where(request_args, WAREHOUSE_NUM_SEARCH)
    clauses += n_clauses
    params += n_params
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


# ============== THƯ MỤC LƯU FILE XUẤT THEO MÀN HÌNH (v1.10.9, Trum 30/09) ==============
# Mỗi màn hình (8 tab dữ liệu + 9 báo cáo) khai được 1 thư mục lưu file riêng, nhớ THEO MÁY (theo tài khoản Windows), dùng
# chung mọi CSDL: %LocalAppData%\iPOS_Ledger_Studio\export_dirs.json = {"v": 1, "dirs": {"<màn hình>": "<thư mục>"}}.
# Màn chưa khai → _export_dir() (Downloads\iPOS_Ledger_Studio) như cũ. Nhật ký logs\datastudio.log + .session_key vẫn ở thư
# mục mặc định. Thư mục đã khai mà không ghi được (rút USB, mất ổ mạng, bị xoá, không quyền) → KHÔNG lưu sang chỗ khác: trả
# code 'export_dir' để app cảnh báo và bắt chọn lại (Trum chốt) — app kiểm TRƯỚC khi xuất, server kiểm lại lúc tạo job.
# Khoá màn hình = khoá kind của App (/api/<kind>/stream_csv) + mã báo cáo — thêm tab/báo cáo thì thêm vào đây + EXPORT_SCREENS (index.html).
_EXPORT_SCREENS = ('ledger', 'sale', 'voucher', 'purchase', 'warehouse', 'income_alloc', 'income_alloc_month',
                   'warehouse_balance', 'pr_detail',
                   'BC005', 'BC006', 'BC007', 'BC008', 'BC009', 'BC010', 'BC011', 'BC012', 'BC013')
# Excel không mở được file có đường dẫn đầy đủ > 218 ký tự; tên file xuất thường ~40 ký tự → chặn thư mục quá sâu ngay lúc khai.
_EXPORT_DIR_MAX = 170
_EXPORT_DIR_WAIT = 6          # giây chờ tối đa khi kiểm 1 thư mục (ổ mạng mất kết nối có thể treo vài chục giây)
_export_dirs_lock = threading.Lock()
_export_known_dirs = set()    # thư mục đã ghi file trong lần chạy này — "Mở file"/"Mở folder" vẫn mở được sau khi đổi thư mục


def _export_dirs_path():
    return os.path.join(os.path.dirname(_saved_logins_path()), "export_dirs.json")


def _export_dirs_read():
    try:
        with open(_export_dirs_path(), "r", encoding="utf-8") as f:
            dirs = json.load(f).get("dirs") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: v for k, v in dirs.items() if k in _EXPORT_SCREENS and isinstance(v, str) and v.strip()}


def _export_dirs_write(dirs):
    path = _export_dirs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "dirs": dirs}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _export_dir_for(screen):
    """(thư mục lưu của màn hình, đã khai riêng?) — chưa khai / khoá lạ → thư mục mặc định."""
    d = _export_dirs_read().get(screen) if screen in _EXPORT_SCREENS else None
    return (d, True) if d else (_export_dir(), False)


def _clean_dir_input(raw):
    """Chữ người dùng dán → đường dẫn tuyệt đối đã chuẩn hoá; '' nếu không phải đường dẫn đầy đủ. Bỏ dấu nháy 2 đầu (lệnh
    "Copy as path" của Explorer), khoảng trắng, dấu \\ thừa cuối. Nhận ổ đĩa (D:\\…) hoặc thư mục mạng (\\\\máy\\chia sẻ\\…)."""
    s = str(raw or "").strip().strip('"').strip()
    if not s:
        return ""
    s = os.path.normpath(s)
    drive, rest = os.path.splitdrive(s)
    if not drive or (len(drive) == 2 and not rest.startswith(("\\", "/"))):   # "thư mục" không có ổ, hoặc "D:abc"
        return ""
    return s


def _export_dir_state(folder, write_test=True):
    """(dùng được?, lý do, tạo lại được?) của 1 thư mục đích. write_test: ghi thử 1 file rỗng rồi xoá — thư mục chỉ đọc / ổ mạng
    mất quyền chỉ lộ ra khi ghi thật. Chạy ở luồng riêng, quá _EXPORT_DIR_WAIT giây coi như không truy cập được."""
    out = {}

    def run():
        try:
            if not os.path.isdir(folder):
                drive = os.path.splitdrive(folder)[0]
                if os.path.exists(folder):
                    out["r"] = (False, "Đường dẫn này là một file, không phải thư mục.", False)
                elif drive and os.path.isdir(drive + os.sep):
                    out["r"] = (False, "Thư mục không còn — đã bị xoá hoặc đổi tên.", True)
                else:
                    out["r"] = (False, f"Không thấy ổ {drive} — ổ USB / ổ mạng đã bị ngắt, hoặc máy chưa vào mạng công ty.", False)
                return
            if write_test:
                probe = os.path.join(folder, f".ds_ghi_thu_{uuid.uuid4().hex[:8]}.tmp")
                with open(probe, "xb"):
                    pass
                os.remove(probe)
            out["r"] = (True, "", False)
        except Exception:
            out["r"] = (False, "Thư mục không cho ghi file — không có quyền, hoặc ổ chỉ đọc.", False)

    t = threading.Thread(target=run, daemon=True, name="export-dir-check")
    t.start()
    t.join(_EXPORT_DIR_WAIT)
    return out.get("r") or (False, f"Không truy cập được thư mục (quá {_EXPORT_DIR_WAIT} giây) — ổ mạng mất kết nối hoặc chưa bật VPN.", False)


def _export_dir_problem(screen):
    """None nếu thư mục của màn hình ghi được; không thì dict lỗi (code 'export_dir') — app cảnh báo + bắt chọn lại thư mục."""
    folder, custom = _export_dir_for(screen)
    if not custom:
        return None   # thư mục mặc định: _export_dir() tự tạo, không tạo được thì rơi về thư mục người dùng như cũ
    ok, reason, can_create = _export_dir_state(folder)
    if ok:
        return None
    return {"status": "error", "code": "export_dir", "screen": screen, "dir": folder, "reason": reason, "can_create": can_create,
            "message": (f"Không lưu được file vào thư mục đã chọn cho màn hình này: {reason[:1].lower()}{reason[1:]}\n"
                        f"{_VI_FIX} Chọn lại thư mục lưu (hoặc cắm lại ổ USB / bật VPN nếu là ổ mạng) rồi xuất lại.\n"
                        f"{_VI_DETAIL} {folder}")}


def _in_export_roots(path):
    """Đường dẫn nằm trong thư mục mặc định / thư mục đã khai / thư mục đã ghi file lần chạy này? (chặn /api/open_file, /api/open_folder
    mở lung tung). So abspath chứ không realpath: realpath tra cả thư mục đã khai trên ổ mạng đang mất kết nối — treo vài chục giây."""
    norm = lambda p: os.path.normcase(os.path.abspath(p))
    target = norm(path)
    for root in {_export_dir(), *_export_dirs_read().values(), *_export_known_dirs}:
        try:
            if os.path.commonpath([target, norm(root)]) == norm(root):
                return True
        except ValueError:   # khác ổ đĩa
            pass
    return False


def _pick_folder_native(start, title):
    """Hộp chọn thư mục kiểu mới của Windows (IFileOpenDialog + FOS_PICKFOLDERS) qua ctypes — không cần pywin32 / comtypes, không
    kéo tkinter vào EXE. Chạy ở luồng riêng khởi tạo COM kiểu STA (luồng request của Werkzeug không bảo đảm). Chủ của hộp = cửa sổ
    Chrome đang đứng trước (chính cửa sổ app vừa bấm nút) → hộp nổi TRÊN app, app bị khoá tới khi đóng hộp; không có chủ thì
    Windows để hộp nằm SAU cửa sổ app (tiến trình server không được giành quyền đứng trước). Trả đường dẫn, '' khi bấm Hủy."""
    out = {}

    def run():
        try:
            out["dir"] = _pick_folder_sta(start, title)
        except BaseException as e:
            out["err"] = e

    t = threading.Thread(target=run, daemon=True, name="pick-folder")
    t.start()
    t.join()
    if "err" in out:
        raise out["err"]
    return out.get("dir", "")


def _pick_owner_window(user32):
    """Cửa sổ làm chủ hộp chọn thư mục: cửa sổ đang đứng trước nếu là cửa sổ app (Chrome/Edge, tiêu đề "DataStudio" — <title> của
    index.html; mở trong tab trình duyệt thì "DataStudio - Google Chrome"); không thì cửa sổ app đầu tiên đang hiện (người dùng bấm
    nút xong chuyển sang Outlook…: hộp vẫn nằm trên app, không lọt ra sau); không có nữa thì cửa sổ Chrome/Edge đang đứng trước."""
    import ctypes
    from ctypes import wintypes

    def info(h):
        c, t = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 64)
        user32.GetWindowTextW(h, t, 256)
        return c.value, t.value

    def is_app(h):
        if not h or not user32.IsWindowVisible(h):
            return False
        c, t = info(h)
        return c == "Chrome_WidgetWin_1" and (t == "DataStudio" or t.startswith("DataStudio - "))

    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    fg = user32.GetForegroundWindow()
    if is_app(fg):
        return fg
    found = []

    def each(h, _):
        if is_app(h):
            found.append(h)
            return False   # dừng duyệt
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(each), 0)
    if found:
        return found[0]
    return fg if fg and info(fg)[0] == "Chrome_WidgetWin_1" else None


def _pick_folder_sta(start, title):
    import ctypes
    from ctypes import wintypes
    ole32 = ctypes.OleDLL("ole32")          # hàm trả HRESULT: lỗi → OSError
    ole32v = ctypes.WinDLL("ole32")         # CoUninitialize / CoTaskMemFree trả void
    shell32 = ctypes.OleDLL("shell32")
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    ole32v.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32v.CoTaskMemFree.restype = None

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    def guid(s):
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    def vcall(obj, idx, restype, *argtypes):
        """Hàm thứ idx trong bảng vtable của đối tượng COM."""
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[idx])
        return lambda *a: fn(obj, *a)

    # IFileOpenDialog: 2 Release · 3 Show · 9 SetOptions · 10 GetOptions · 12 SetFolder · 17 SetTitle · 18 SetOkButtonLabel · 20 GetResult
    # IShellItem: 2 Release · 5 GetDisplayName
    FOS = 0x8 | 0x20 | 0x40 | 0x800          # NOCHANGEDIR | PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST
    SIGDN_FILESYSPATH = 0x80058000
    ERROR_CANCELLED = 0x800704C7
    ole32.CoInitializeEx(None, 0x2 | 0x4)    # APARTMENTTHREADED | DISABLE_OLE1DDE
    dlg = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(ctypes.byref(guid("{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}")), None, 1,
                               ctypes.byref(guid("{D57C7288-D4AD-4768-BE02-9D969532D960}")), ctypes.byref(dlg))
        opts = wintypes.DWORD()
        vcall(dlg, 10, ctypes.HRESULT, ctypes.POINTER(wintypes.DWORD))(ctypes.byref(opts))
        vcall(dlg, 9, ctypes.HRESULT, wintypes.DWORD)(opts.value | FOS)
        vcall(dlg, 17, ctypes.HRESULT, wintypes.LPCWSTR)(title)
        vcall(dlg, 18, ctypes.HRESULT, wintypes.LPCWSTR)("Chọn thư mục")
        if start and os.path.isdir(start):
            item = ctypes.c_void_p()
            try:
                shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(start), None,
                                                    ctypes.byref(guid("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")), ctypes.byref(item))
                vcall(dlg, 12, ctypes.HRESULT, ctypes.c_void_p)(item)
            except OSError:
                pass
            finally:
                if item:
                    vcall(item, 2, ctypes.c_ulong)()
        owner = _pick_owner_window(user32)
        try:
            vcall(dlg, 3, ctypes.HRESULT, wintypes.HWND)(owner)
        except OSError as e:
            if (e.winerror or 0) & 0xFFFFFFFF == ERROR_CANCELLED:
                return ""
            raise
        item = ctypes.c_void_p()
        vcall(dlg, 20, ctypes.HRESULT, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(item))
        try:
            name = ctypes.c_void_p()
            vcall(item, 5, ctypes.HRESULT, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(SIGDN_FILESYSPATH, ctypes.byref(name))
            try:
                return ctypes.wstring_at(name.value)
            finally:
                ole32v.CoTaskMemFree(name)
        finally:
            vcall(item, 2, ctypes.c_ulong)()
    finally:
        if dlg:
            vcall(dlg, 2, ctypes.c_ulong)()
        ole32v.CoUninitialize()


# In-memory map theo dõi tiến trình job export
# { job_id: { status, current, total, file_path, filename, error } }
_export_jobs = {}
_export_jobs_lock = threading.Lock()


# ============== XUẤT FILE LỚN CHỊU ĐƯỢC MẠNG CHẬP CHỜN (v1.10.6, Trum 29/09) ==============
# Sự cố: xuất BC007 ≈ 2,86 triệu dòng (IACC_CHULONG, qua VPN) → "[DBNETLIB]ConnectionWrite (10054)" giữa chừng, mất trắng.
# Bản cũ giữ MỘT truy vấn mở suốt lúc ghi file (đọc 5.000 dòng → ghi → đọc tiếp): file càng lớn kết nối càng phải sống
# lâu, VPN chớp 1 lần là hỏng cả file. Nay mọi job xuất (báo cáo + danh sách chứng từ) đi 2 giai đoạn:
#   1. TẢI — chia truy vấn thành các khúc theo khoảng NGÀY (_day_chunks: ngày là khoá sắp xếp đầu nên nối các khúc
#      = đúng thứ tự của 1 truy vấn), đọc từng khúc vào file tạm nén trên máy (_ExportSpool). Đứt mạng → đóng kết nối
#      hỏng, chờ, nối lại, bỏ phần dở của khúc đang tải rồi tải lại ĐÚNG khúc đó (_ExportDb). Khúc đã tải giữ nguyên.
#   2. GHI — tải xong mới nhả kết nối SQL rồi ghi Excel/CSV từ file tạm: khâu lâu nhất không còn phụ thuộc mạng.
# Mỗi job ghi nhật ký (mốc thời gian từng khâu, từng khúc, lần nối lại, lỗi rút gọn) vào
# Downloads\iPOS_Ledger_Studio\logs\datastudio.log — trước đây EXE không ghi log ra đâu cả, lỗi ở máy người dùng là mù.
import logging.handlers
import pickle
import struct
import tempfile
import zlib

_EXPORT_CHUNK_ROWS = 200000   # dòng/khúc tối thiểu (gộp các ngày liền nhau tới mốc; 1 ngày to hơn thì đứng riêng 1 khúc)
# Tối đa ~8 khúc: khúc cỡ trăm nghìn dòng thì SQL thường QUÉT CẢ BẢNG LEDGER thay vì tra index ngày (tra khoá từng dòng đắt
# hơn) — CHULONG LEDGER 1,75 GB, buffer pool Express 1,4 GB (skill chulong-db-perf) → mỗi khúc 1 lượt đọc đĩa, làm chậm người
# đang nhập liệu. 8 khúc = 8 lượt quét thay vì 1, đổi lại mỗi khúc sắp xếp gọn trong RAM (câu 2,86 triệu dòng cũ tràn
# tempdb) và đứt mạng chỉ tải lại ≤ 1/8. Nhật ký ghi "dong dau sau x s" từng khúc → biết thật sự quét hay tra index.
_EXPORT_MAX_CHUNKS = 8
_EXPORT_FETCH_ROWS = 5000
_NET_RETRY_WAITS = (3, 5, 10, 20, 30, 45, 60, 60)   # giây chờ trước mỗi lần nối lại (~4 phút) — hết lượt mới báo lỗi
_EXPORT_CONNECT_WAIT = 15     # giây chờ tối đa mỗi lần nối lại (driver "SQL Server" bỏ qua timeout=5 — xem _make_conn_capped)
_CHUNK_MARK = "/*CHUNK*/"     # chỗ chèn điều kiện ngày của khúc: CUỐI mệnh đề WHERE, trước ORDER BY (xem _day_chunks)

_xlog = logging.getLogger("datastudio.export")
_xlog_state = {"path": None}
_xlog_lock = threading.Lock()


def _export_log_path():
    """Gắn (1 lần) file nhật ký xuất, trả đường dẫn ('' nếu không ghi được). Chỉ ghi tên CSDL, số dòng, thời gian,
    lỗi rút gọn — KHÔNG ghi mật khẩu / chuỗi kết nối. Xoay vòng 1 MB × 4 file."""
    with _xlog_lock:
        if _xlog_state["path"] is None:
            try:
                folder = os.path.join(_export_dir(), "logs")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, "datastudio.log")
                h = logging.handlers.RotatingFileHandler(path, maxBytes=1000000, backupCount=3, encoding="utf-8", delay=True)
                h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                _xlog.addHandler(h)
                _xlog.setLevel(logging.INFO)
                _xlog.propagate = False
                _xlog_state["path"] = path
            except Exception:
                _xlog_state["path"] = ""
        return _xlog_state["path"]


# Lỗi đáng thử lại: mạng/kết nối đứt, hết giờ chờ, bị chọn làm nạn nhân deadlock. Lỗi SQL thật (sai cú pháp, thiếu cột,
# thiếu quyền, sai mật khẩu…) KHÔNG thử lại — báo ngay như cũ.
_NET_ERR = re.compile(
    r"\b08S01\b|\b0800[134]\b|\bHYT0[01]\b|1005[34]|1006[01]|connectionwrite|connectionread|connectioncheckfordata|"
    r"connectionopen|general network error|communication link failure|tcp provider|named pipes provider|"
    r"shared memory provider|session provider|physical connection is not usable|forcibly closed|semaphore timeout|"
    r"network name is no longer available|connection (?:is )?broken|severe error occurred|timeout expired|deadlock|\b40001\b",
    re.I)


def _is_net_error(e):
    return isinstance(e, (TimeoutError, ConnectionError)) or bool(_NET_ERR.search(str(e)))


class _ExportNetError(Exception):
    """Đã tự nối lại hết lượt mà mạng vẫn đứt — câu báo đã là tiếng Việt 3 phần (_vi_error_text giữ nguyên)."""


class _ExportCtl:
    """Cập nhật / hỏi huỷ / ghi nhật ký cho 1 job trong _export_jobs (dùng chung job báo cáo và job danh sách)."""

    def __init__(self, job_id, started, tag):
        self.job_id, self.started, self.tag = job_id, started, tag
        _export_log_path()

    def upd(self, **kw):
        with _export_jobs_lock:
            job = _export_jobs.get(self.job_id)
            if job is not None:
                job.update(kw)
                job['elapsed'] = round(time.time() - self.started, 1)

    def cancelled(self):
        with _export_jobs_lock:
            job = _export_jobs.get(self.job_id)
            return bool(job and job.get('cancelled'))

    def log(self, msg, *args, level=logging.INFO):
        try:
            _xlog.log(level, f"[{self.job_id[:8]} {self.tag}] " + msg, *args)
        except Exception:
            pass


class _ExportSpool:
    """File tạm nén chứa các dòng đã tải: mỗi khung = 4 byte độ dài + zlib(pickle(list dòng)). mark/rollback để bỏ phần
    dở của khúc đang tải khi đứt mạng. Đo 29/09 (dòng giả kiểu BC007): 2,86 triệu dòng ghi ~10 s, đọc ~4 s, ~55 MB.
    pickle an toàn ở đây: chỉ chính job này ghi rồi đọc lại file của nó."""

    def __init__(self):
        folder = tempfile.gettempdir()
        try:   # dọn file tạm mồ côi (EXE bị tắt ngang giữa lúc xuất) — chỉ file cũ hơn 6 giờ
            now = time.time()
            for fn in os.listdir(folder):
                fp = os.path.join(folder, fn)
                if fn.startswith("ds_spool_") and fn.endswith(".tmp") and now - os.path.getmtime(fp) > 6 * 3600:
                    os.remove(fp)
        except Exception:
            pass
        fd, self.path = tempfile.mkstemp(prefix="ds_spool_", suffix=".tmp", dir=folder)
        self.fh = os.fdopen(fd, "w+b")
        self.count = 0
        _live_spools.add(self)

    def mark(self):
        return self.fh.tell(), self.count

    def rollback(self, m):
        self.fh.seek(m[0])
        self.fh.truncate()
        self.count = m[1]

    def write(self, batch):
        blob = zlib.compress(pickle.dumps(batch, pickle.HIGHEST_PROTOCOL), 1)
        self.fh.write(struct.pack("<I", len(blob)))
        self.fh.write(blob)
        self.count += len(batch)

    def size(self):
        return self.fh.tell()

    def iter_rows(self):
        self.fh.flush()
        self.fh.seek(0)
        while True:
            head = self.fh.read(4)
            if len(head) < 4:
                break
            (n,) = struct.unpack("<I", head)
            for r in pickle.loads(zlib.decompress(self.fh.read(n))):
                yield r

    def close(self):
        _live_spools.discard(self)
        try:
            self.fh.close()
        except Exception:
            pass
        try:
            os.remove(self.path)
        except Exception:
            pass


# File tạm của các job đang chạy — tắt app giữa lúc xuất thì _shutdown_everything xoá luôn (mỗi file có thể vài chục MB)
_live_spools = set()


def _drop_live_spools():
    for sp in list(_live_spools):
        sp.close()


def _cleanup_orphan_exports():
    """Lúc mở app: xoá file tạm (%TEMP%\\ds_spool_*.tmp) và file Excel dở (*.part) của lần chạy trước bị tắt giữa lúc xuất.
    Chỉ gọi lúc khởi động — tiến trình cũ đã bị kill_process_on_port tắt, chưa job nào chạy nên xoá hết, không cần chờ 6 giờ."""
    for folder, test in ((tempfile.gettempdir(), lambda fn: fn.startswith("ds_spool_") and fn.endswith(".tmp")),
                         (_export_dir(), lambda fn: fn.endswith(".part"))):
        try:
            for fn in os.listdir(folder):
                if test(fn):
                    try:
                        os.remove(os.path.join(folder, fn))
                    except OSError:
                        pass
        except OSError:
            pass


class _ExportDb:
    """Kết nối SQL RIÊNG của 1 job xuất (không dùng pool, không cần session). Lỗi mạng → đóng kết nối hỏng, chờ
    _NET_RETRY_WAITS, nối lại, làm lại đúng bước đang dở. Mọi bước chỉ SELECT nên làm lại là an toàn."""

    def __init__(self, db_cfg, ctl):
        self.db_cfg, self.ctl, self.conn = db_cfg, ctl, None
        self.reconnects = 0

    def cursor(self):
        if self.conn is None:
            self.conn = _make_conn_capped(self.db_cfg, _EXPORT_CONNECT_WAIT)
        return self.conn.cursor()

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def _retry(self, what, attempt):
        tries, t_begin = 0, time.time()
        while True:
            try:
                out = attempt()
                if tries:
                    self.ctl.upd(retry=None)
                    self.ctl.log("%s: da noi lai, chay tiep", what)
                return out
            except (XR.ExportCancelled, _ExportNetError):
                raise
            except Exception as e:
                if not _is_net_error(e):
                    raise
                self.close()
                if tries >= len(_NET_RETRY_WAITS):
                    self.ctl.log("%s: bo cuoc sau %d lan noi lai: %s", what, tries, _err_brief(e), level=logging.ERROR)
                    logp = _export_log_path()
                    raise _ExportNetError(
                        f"Mất kết nối tới máy chủ SQL khi đang tải dữ liệu — đã tự kết nối lại {tries} lần trong "
                        f"{max(1, round((time.time() - t_begin) / 60))} phút vẫn không được.\n"
                        f"{_VI_FIX} Kiểm tra VPN công ty còn kết nối rồi bấm xuất lại. Mạng yếu kéo dài thì thu hẹp kỳ "
                        f"hoặc lọc bớt đơn vị cho ít dòng hơn.\n"
                        f"{_VI_DETAIL} {_err_brief(e)}" + (f" · nhật ký: {logp}" if logp else "")) from e
                wait = _NET_RETRY_WAITS[tries]
                tries += 1
                self.reconnects += 1
                self.ctl.log("%s: loi mang (lan %d/%d, cho %ds): %s", what, tries, len(_NET_RETRY_WAITS), wait,
                             _err_brief(e), level=logging.WARNING)
                self.ctl.upd(retries=self.reconnects,
                             retry={'n': tries, 'max': len(_NET_RETRY_WAITS), 'wait': wait, 'until': time.time() + wait})
                deadline = time.time() + wait
                while time.time() < deadline:
                    if self.ctl.cancelled():
                        raise XR.ExportCancelled()
                    time.sleep(0.25)

    def run(self, fn, what):
        """fn(cursor) → kết quả; đứt mạng thì nối lại và gọi lại fn từ đầu."""
        return self._retry(what, lambda: fn(self.cursor()))

    def all(self, sql, params=None, what="truy van"):
        def go(cur):
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur.fetchall()
        return self.run(go, what)

    def one(self, sql, params=None, what="truy van"):
        rows = self.all(sql, params, what)
        return rows[0] if rows else None

    def fetch(self, chunks, spool):
        """Tải lần lượt các khúc [(sql, params), …] vào spool, cập nhật current = số dòng đã tải.
        Trả tên cột (cursor.description) — bộ xuất danh sách cần để map dòng."""
        cols, n = None, len(chunks)
        for i, (sql, params) in enumerate(chunks, 1):
            mark = spool.mark()
            timing = {}

            def attempt():
                nonlocal cols
                spool.rollback(mark)   # lần thử lại: bỏ phần dở của khúc này, tải lại từ đầu khúc
                self.ctl.upd(current=spool.count)
                t0 = time.time()
                cur = self.cursor()
                cur.execute(sql, params)
                if cols is None:
                    cols = [c[0] for c in cur.description]
                timing.pop('first', None)
                while True:
                    batch = cur.fetchmany(_EXPORT_FETCH_ROWS)
                    timing.setdefault('first', time.time() - t0)
                    if not batch:
                        break
                    spool.write([tuple(r) for r in batch])
                    self.ctl.upd(current=spool.count)
                    if self.ctl.cancelled():
                        raise XR.ExportCancelled()
                cur.close()
                timing['total'] = time.time() - t0

            self._retry(f"khuc {i}/{n}", attempt)
            self.ctl.upd(chunk=i)
            self.ctl.log("khuc %d/%d: %d dong, dong dau sau %.1fs, xong %.1fs", i, n, spool.count - mark[1],
                         timing.get('first', 0), timing.get('total', 0))
        return cols or []


def _day_chunks(sql, params, day_counts, col, desc=False, target=None):
    """Chia 1 truy vấn xuất thành các khúc theo khoảng ngày (xem đầu khối).
    sql chứa đúng 1 _CHUNK_MARK ở CUỐI mệnh đề WHERE (sau mọi điều kiện có '?', trước ORDER BY — ORDER BY không có '?')
    → điều kiện ngày của khúc chèn vào đó, tham số nối vào CUỐI params (Bẫy 2).
    day_counts: [(ngày 'YYYYMMDD', số dòng), …] do GROUP BY CONVERT(VARCHAR(8), col, 112) trên CÙNG WHERE trả về.
    WHERE gốc đã giới hạn [từ ngày, tới ngày] nên khúc đầu chỉ cần cận trên, khúc cuối chỉ cần cận dưới, cận giữa nửa mở
    → hợp các khúc = đúng tập dòng của truy vấn gốc, không trùng không sót (TRAN_DATE có giờ vẫn đúng).
    CHỈ dùng khi ORDER BY bắt đầu bằng chính cột ngày này (desc = cột đó sắp giảm dần) — nối khúc theo ngày mới giữ đúng thứ
    tự. Dòng trùng cả khoá sắp xếp vốn không có thứ tự cố định (Bẫy 20), chia khúc không làm khác đi.
    Không chia được (thiếu dấu, có dòng ngày NULL, chỉ 1 khúc) → 1 khúc = truy vấn gốc.
    target (dòng/khúc) mặc định = max(_EXPORT_CHUNK_ROWS, tổng / _EXPORT_MAX_CHUNKS)."""
    whole = [(sql.replace(_CHUNK_MARK, ""), list(params))]
    if sql.count(_CHUNK_MARK) != 1 or any(d is None for d, _ in day_counts):
        return whole
    total = sum(int(n or 0) for _, n in day_counts)
    target = target or max(_EXPORT_CHUNK_ROWS, -(-total // _EXPORT_MAX_CHUNKS))
    starts, acc = [], 0
    for d, n in sorted((str(d).strip(), int(n or 0)) for d, n in day_counts):
        if not starts or acc >= target:   # gộp ngày tới khi CHẠM mốc → mỗi khúc ≥ target (trừ khúc cuối), số khúc ≤ tổng/target
            starts.append(d)
            acc = 0
        acc += n
    if len(starts) <= 1:
        return whole
    out = []
    for k, s in enumerate(starts):
        if k == 0:
            pred, p = f"{col} < ?", [starts[1]]
        elif k == len(starts) - 1:
            pred, p = f"{col} >= ?", [s]
        else:
            pred, p = f"{col} >= ? AND {col} < ?", [s, starts[k + 1]]
        out.append((sql.replace(_CHUNK_MARK, " AND " + pred), list(params) + p))
    return out[::-1] if desc else out


def _list_day_split(order_by_sql, date_col, from_sql, where_sql, params, tail=""):
    """Bộ xuất danh sách: ORDER BY bắt đầu bằng cột ngày (mặc định "X.TRAN_DATE DESC, X.TRAN_NO") → day_split cho
    _start_export_job; người dùng sắp theo cột khác → None (tải 1 khúc, đứt mạng thì tải lại cả truy vấn)."""
    first = order_by_sql.split(",")[0].split()
    if not first or first[0] != date_col:
        return None
    return (date_col, len(first) > 1 and first[1].upper() == "DESC",
            f"SELECT CONVERT(VARCHAR(8), {date_col}, 112), COUNT(*) {from_sql} WHERE {where_sql} "
            f"GROUP BY CONVERT(VARCHAR(8), {date_col}, 112){tail}", list(params))


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
                job['status'] = 'cancelled' if job.get('cancelled') else 'error'
                job['error']  = str(e)


# Tách sheet danh sách chứng từ khi chạm mốc này (trần Excel 1.048.576 dòng/sheet) — cùng mốc với báo cáo.
LIST_XLSX_SHEET_ROWS = 1000000


def _write_xlsx_to_disk(job_id, headers, row_iter, filename, total_estimate, out_path=None, spec=None):
    """Ghi dữ liệu lớn ra XLSX (constant_memory), tự sang sheet mới khi chạm LIST_XLSX_SHEET_ROWS dòng.

    spec (tuỳ chọn — DT chờ phân bổ theo tháng, v1.10.6): {'header_dates': {cột: datetime} tiêu đề là ngày thật (hiện mm/yyyy),
    'formulas': {cột: '=SUM(O{r}:Z{r})'} ô ghi công thức ({r} = số dòng Excel) kèm giá trị tính sẵn, 'sum_cols': [cột…] dòng
    "Tổng cộng" cuối bảng (1 sheet → công thức SUM, nhiều sheet → số), 'bold_cols': [cột…] ô số in đậm (v1.10.7)}.

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
        spec = spec or {}
        hdr_dates, formulas = spec.get('header_dates') or {}, spec.get('formulas') or {}
        sum_cols = [c for c in (spec.get('sum_cols') or []) if c < ncols]
        sums = {c: _Dec(0) for c in sum_cols}
        bold_cols = set(spec.get('bold_cols') or [])
        int_bold = workbook.add_format(dict(base, num_format='#,##0', bold=True)) if bold_cols else int_format
        dec_bold = workbook.add_format(dict(base, num_format='#,##0.##', bold=True)) if bold_cols else dec_format
        hdr_date_format = workbook.add_format(dict(base, bold=True, bg_color='#F1F5F9', align='center', valign='vcenter',
                                                   border=1, border_color='#CBD5E1', num_format='mm/yyyy'))

        def new_sheet(idx):
            ws = workbook.add_worksheet(f"Sheet {idx}")
            ws.freeze_panes(1, 0)
            ws.set_row(0, 30)
            for col_num, header in enumerate(headers):
                if col_num in hdr_dates:
                    ws.write_datetime(0, col_num, hdr_dates[col_num], hdr_date_format)
                else:
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
                    if col_num in bold_cols:
                        nfmt = int_bold if num.is_integer() else dec_bold
                    else:
                        nfmt = int_format if num.is_integer() else dec_format
                    if col_num in formulas:
                        worksheet.write_formula(row_num, col_num, formulas[col_num].replace('{r}', str(row_num + 1)), nfmt, num)
                    else:
                        worksheet.write_number(row_num, col_num, num, nfmt)
                    if col_num in sums:
                        sums[col_num] += val if isinstance(val, _Dec) else _Dec(repr(val))
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
        if sum_cols and count:
            from xlsxwriter.utility import xl_col_to_name
            tot_fmt = workbook.add_format(dict(base, bold=True, num_format='#,##0', bg_color='#F8FAFC', top=1, top_color='#94A3B8'))
            tot_lbl = workbook.add_format(dict(base, bold=True, bg_color='#F8FAFC', top=1, top_color='#94A3B8'))
            for c in range(ncols):
                if c in sums:
                    v = float(sums[c])
                    if len(sheets) == 1:
                        L = xl_col_to_name(c)
                        worksheet.write_formula(row_num, c, f"=SUM({L}2:{L}{row_num})", tot_fmt, v)
                    else:   # nhiều sheet: SUM 1 sheet sẽ sai → ghi số tổng mọi sheet
                        worksheet.write_number(row_num, c, v, tot_fmt)
                elif c == 0:
                    worksheet.write_string(row_num, 0, "Tổng cộng" if len(sheets) == 1 else "Tổng cộng (mọi sheet)", tot_lbl)
                else:
                    worksheet.write_blank(row_num, c, None, tot_lbl)
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
                job['status'] = 'cancelled' if job.get('cancelled') else 'error'
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
        if not _is_local_request():
            return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
        data = request.get_json(force=True, silent=True) or {}
        path = data.get("path", "")
        # Validate: chỉ mở file xuất (.xlsx/.csv) nằm trong thư mục lưu (mặc định / đã khai theo màn hình) để tránh bị abuse
        # — thư mục người dùng khai có thể chứa file khác, kể cả .exe.
        norm = os.path.abspath(path)
        if not path or not _in_export_roots(norm) or os.path.splitext(norm)[1].lower() not in ('.xlsx', '.csv', '.xls'):
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
        if not _is_local_request():
            return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
        data = request.get_json(force=True, silent=True) or {}
        path = data.get("path", "")
        norm = os.path.abspath(path)
        if not path or not _in_export_roots(norm):
            return jsonify({"status": "error", "message": "Đường dẫn không hợp lệ"}), 400
        # file đã bị xoá / đổi tên → mở thư mục chứa nó (thư mục lưu theo màn hình), mất cả thư mục mới về thư mục mặc định
        exp_root = os.path.dirname(norm) if os.path.isdir(os.path.dirname(norm)) else _export_dir()
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


def _start_export_job(filename, headers, sql, params, transform_row, total_estimate=0, day_split=None, xlsx_spec=None):
    """Job nền xuất danh sách chứng từ: kết nối riêng (cùng db_config session) → TẢI hết dòng vào file tạm (chịu đứt
    mạng — xem khối "XUẤT FILE LỚN CHỊU ĐƯỢC MẠNG CHẬP CHỜN") → nhả kết nối → GHI xlsx/csv.

    transform_row(raw_row, sql_cols) → list giá trị theo thứ tự headers.
    day_split (tuỳ chọn, từ _list_day_split) = (cột ngày, giảm dần?, câu đếm theo ngày, tham số): chia khúc theo ngày —
    sql phải có _CHUNK_MARK cuối WHERE. Không truyền → tải 1 khúc (đứt mạng thì tải lại cả truy vấn).
    xlsx_spec (tuỳ chọn): tiêu đề ngày / công thức / dòng tổng cho file xlsx — xem _write_xlsx_to_disk.
    Trả về job_id ngay.
    """
    job_id = uuid.uuid4().hex
    started = time.time()
    ext = 'xlsx' if filename.lower().endswith('.xlsx') else 'csv'
    # Thư mục lưu theo màn hình (v1.10.9): màn hình = đoạn giữa /api/<màn>/stream_csv — trùng khoá kind của App. Thư mục đã khai
    # mà hỏng → job lỗi ngay, code 'export_dir' (app cảnh báo + bắt chọn lại rồi xuất lại). App đã kiểm trước khi gọi; đây là lưới
    # an toàn khi thư mục mất trong lúc app còn đang đếm dòng.
    parts = request.path.strip('/').split('/')
    screen = parts[1] if len(parts) == 3 and parts[0] == 'api' else ''
    problem = _export_dir_problem(screen)
    if problem:
        with _export_jobs_lock:
            _export_jobs[job_id] = {'status': 'error', 'phase': 'error', 'current': 0, 'total': total_estimate, 'file_path': None,
                                    'filename': filename, 'error': problem['message'], 'cancelled': False, 'started': started,
                                    'elapsed': 0, 'retries': 0, 'retry': None, 'format': ext,
                                    **{k: problem[k] for k in ('code', 'screen', 'dir', 'reason', 'can_create')}}
        return job_id
    # Tên file không trùng file cũ: trước đây xuất lại cùng khoảng ngày là GHI ĐÈ — mà file cũ đang mở trong Excel
    # thì Windows khoá file ⇒ job lỗi "Permission denied". Nay tự thêm (2), (3)… và ghi ra *.part rồi mới đổi tên.
    final_path = _rx_reserve_path(filename, ext, _export_dir_for(screen)[0])
    filename = os.path.basename(final_path)
    with _export_jobs_lock:
        _export_jobs[job_id] = {
            'status': 'running', 'phase': 'prepare', 'current': 0, 'total': total_estimate,
            'file_path': None, 'filename': filename, 'error': None,
            'cancelled': False, 'started': started, 'elapsed': 0, 'retries': 0, 'retry': None,
            'format': ext,
        }
    db_cfg = session.get('db_config')
    ctl = _ExportCtl(job_id, started, f"danh sach {filename}")

    def _runner():
        db, spool = None, None
        try:
            if not db_cfg:
                raise Exception("Chưa đăng nhập SQL Server")
            ctl.log("bat dau: CSDL %s, uoc tinh %d dong, %s", db_cfg.get('database'), total_estimate, ext)
            db = _ExportDb(db_cfg, ctl)
            chunks, total = [(sql.replace(_CHUNK_MARK, ""), list(params))], total_estimate
            if day_split:
                col, desc, count_sql, count_params = day_split
                ctl.upd(phase='query')
                t = time.time()
                days = db.all(count_sql, count_params, "dem dong theo ngay")
                total = sum(int(r[1] or 0) for r in days)
                chunks = _day_chunks(sql, params, [(r[0], r[1]) for r in days], col, desc)
                ctl.upd(total=total)
                ctl.log("dem: %d dong, %d ngay -> %d khuc, %.1fs", total, len(days), len(chunks), time.time() - t)
            t = time.time()
            ctl.upd(phase='fetch', current=0, chunk=0, chunks=len(chunks))
            spool = _ExportSpool()
            sql_cols = db.fetch(chunks, spool)
            db.close()   # tải xong → nhả kết nối TRƯỚC khi ghi file
            ctl.log("tai xong: %d dong, %.1fs, file tam %.1f MB, noi lai %d lan", spool.count, time.time() - t,
                    spool.size() / 1048576, db.reconnects)
            db = None
            if ctl.cancelled():
                raise XR.ExportCancelled()
            t = time.time()
            ctl.upd(phase='write', current=0, total=spool.count)
            rows = (transform_row(raw, sql_cols) for raw in spool.iter_rows())
            if ext == 'xlsx':
                _write_xlsx_to_disk(job_id, headers, rows, filename, spool.count, out_path=final_path + '.part', spec=xlsx_spec)
            else:
                _write_csv_to_disk(job_id, headers, rows, filename, spool.count, out_path=final_path + '.part')
            with _export_jobs_lock:
                job = _export_jobs.get(job_id) or {}
                st, err = job.get('status'), job.get('error')
            if st == 'done':
                ctl.upd(phase='done')
                ctl.log("ghi xong: %.1fs, tong %.1fs", time.time() - t, time.time() - started)
            else:
                ctl.log("ghi file loi: %s", _err_brief(err), level=logging.ERROR)
        except XR.ExportCancelled:
            ctl.upd(status='cancelled', phase='cancelled')
            ctl.log("nguoi dung huy")
        except Exception as e:
            ctl.log("loi: %s", _err_brief(e), level=logging.ERROR)
            ctl.upd(status='error', phase='error', error=str(e))
        finally:
            if db is not None:
                db.close()
            if spool is not None:
                spool.close()
            with _export_jobs_lock:
                _export_reserved.discard(final_path.lower())

    threading.Thread(target=_runner, daemon=True, name=f"export-list-{job_id[:8]}").start()
    return job_id


def _pick_export_cols(args, full_cols, extra_cols=()):
    """Xuất "Như đang xem" (v1.10.0): args['cols'] = 'KEY1,KEY2,…' — đúng các cột đang hiện, theo thứ tự trên màn hình.
    Chỉ nhận khoá có trong bộ cột xuất của tab (full_cols) hoặc cột chỉ có trên màn hình (extra_cols): khoá lạ bỏ qua,
    không đụng tới SQL. Không gửi cols / không còn khoá hợp lệ → xuất đủ như cũ. Tên cột giữ theo bộ cột xuất chuẩn."""
    raw = (args.get("cols") or "").strip()
    if not raw:
        return list(full_cols)
    labels = dict(extra_cols)
    labels.update(full_cols)
    picked, seen = [], set()
    for key in raw.split(","):
        key = key.strip()
        if key in labels and key not in seen:
            seen.add(key)
            picked.append((key, labels[key]))
    return picked or list(full_cols)


def _tran_name_map():
    """Mã loại chứng từ → tên (SYS_TRAN) lấy từ cache danh mục của CSDL đang đăng nhập.
    Gọi trong request (cần session) — KHÔNG gọi trong transform (chạy ở thread nền)."""
    db_name = session.get('db_config', {}).get('database', 'N/A')
    meta = _meta_cache.get(db_name) or {}
    return {(it.get('id') or '').strip(): it.get('name') or '' for it in meta.get('tran_ids', [])}


# Cột "Tên chứng từ" có trên màn hình bán hàng/nhập kho/kho nhưng bộ cột xuất chuẩn của 3 tab này không có
# → chỉ xuất khi chọn "Như đang xem" và cột đang hiện.
TRAN_NAME_EXPORT_COL = [("TRAN_NAME", "Tên chứng từ")]


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
        sql = f"SELECT {BASE_COLS} {jt} WHERE {where_sql} AND {join_filter}{_CHUNK_MARK} ORDER BY {order_by_sql}"
        # câu đếm theo ngày: như /api/ledger/count — chỉ kèm JOIN khi có ô tìm theo tên (số dòng chỉ để chia khúc + tiến trình)
        day_split = _list_day_split(order_by_sql, "L.TRAN_DATE", jt if join_clauses else "FROM dbo.LEDGER L WITH (NOLOCK)",
                                    f"{where_sql} AND {join_filter}", params + join_params)
        cols = _pick_export_cols(args, LEDGER_CSV_COLS)
        all_keys = [k for k, _ in LEDGER_CSV_COLS]
        pick = [all_keys.index(k) for k, _ in cols]
        if pick == list(range(len(all_keys))):
            pick = None   # xuất đủ như cũ — khỏi chép lại từng dòng

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
            out = [
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
            return out if pick is None else [out[i] for i in pick]

        headers = [label for _, label in cols]
        fname   = f"ChungTuTongHop_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params + join_params, transform, total_estimate, day_split)
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
        sql = f"SELECT {SELECT_LIST} {JOIN_SQL} WHERE {where_sql}{_CHUNK_MARK} ORDER BY {order_by_sql}"
        day_split = _list_day_split(order_by_sql, "P.TRAN_DATE", JOIN_SQL, where_sql, params)
        cols = _pick_export_cols(args, PURCHASE_CSV_COLS, TRAN_NAME_EXPORT_COL)
        tran_map = _tran_name_map() if any(k == "TRAN_NAME" for k, _ in cols) else None

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            if tran_map is not None and 'TRAN_NAME' not in d:
                d['TRAN_NAME'] = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname   = f"PhieuNhapKho_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate, day_split)
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
        sql = f"SELECT {SELECT_LIST} {JOIN_SQL} WHERE {where_sql}{_CHUNK_MARK} ORDER BY {order_by_sql}"
        day_split = _list_day_split(order_by_sql, "W.TRAN_DATE", JOIN_SQL, where_sql, params)

        cols = _pick_export_cols(args, WAREHOUSE_CSV_COLS, TRAN_NAME_EXPORT_COL)
        tran_map = _tran_name_map() if any(k == "TRAN_NAME" for k, _ in cols) else None

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            if tran_map is not None and 'TRAN_NAME' not in d:
                d['TRAN_NAME'] = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname   = f"ChungTuKho_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate, day_split)
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

    n_clauses, n_params = _num_prefix_where(request_args, WAREHOUSE_BALANCE_NUM_SEARCH)
    clauses += n_clauses
    params += n_params
    return " AND ".join(clauses), params


@app.route("/api/warehouse_balance")
@with_db_lock
def get_warehouse_balance():
    try:
        page      = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 100))
        export_all  = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        known_sums  = request.args.get("known_sums")   # JSON dòng tổng lần đếm trước (v1.10.3)
        skip_count  = page > 1 and known_total is not None and known_sums is not None and not export_all

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
            qi = {c: i for i, c in enumerate(columns)}
            summary = {k: sum(float(r[qi[c]] or 0) for r in raw_rows) if c in qi else 0
                       for c, k in (("QUANTITY", "quantity"), ("QUANTITY_ADJ", "quantity_adj"))}
        else:
            if skip_count:
                import json as _json
                total_rows = int(known_total)
                try:    summary = _json.loads(known_sums)
                except: summary = {"quantity": 0, "quantity_adj": 0}
            else:
                # Dòng tổng (v1.10.3): màn hình hiện ô trống là 0.00 → cộng ISNULL(…,0), cùng cách lọc số ở WAREHOUSE_BALANCE_NUM_SEARCH
                cursor.execute(f"SELECT COUNT(*), SUM(ISNULL(WBA.QUANTITY,0)), SUM(ISNULL(WBA.QUANTITY_ADJ,0)) {_WBA_JOIN_SQL} WHERE {where_sql}", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                summary = {"quantity": float(row[1] or 0), "quantity_adj": float(row[2] or 0)}

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
            },
            "summary": summary
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

        cols = _pick_export_cols(args, WAREHOUSE_BALANCE_CSV_COLS)

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname   = f"TonKhoThucTe_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============== DM_PR_DETAIL (Danh mục đối tượng pháp nhân / công nợ) ===============
PR_DETAIL_BASE_COLUMNS = [
    "PR_DETAIL_ID", "PR_DETAIL_NAME", "PR_DETAIL_TYPE_ID",
    "PR_DETAIL_CLASS_ID", "TAX_FILE_NUMBER", "PHONE", "EMAIL", "ADDRESS",
    "PR_ACCOUNT_ID", "BANK_NAME", "BANK_ACCOUNT", "BANK_BRANCH",
    "BANK_ACCOUNT_HOLDER", "ACTIVE", "USER_ID", "FAX",
    "PRICE_LEVEL_ID", "PROVINCE_ID", "PAYMENT_TERM_ID", "BANK_CARD_NO"
]

PR_DETAIL_TYPE_MAP = {
    "00": "Khách hàng",
    "01": "Nhà cung cấp",
    "02": "Đại lý",
    "03": "Phòng ban/Bộ phận",
    "04": "Nhân viên",
    "05": "Khác",
    "06": "Khách",
    "07": "Đối tác",
    "08": "Cục thuế"
}

PR_DETAIL_SORT_WHITELIST = {col: f"P.{col}" for col in PR_DETAIL_BASE_COLUMNS}
PR_DETAIL_SORT_WHITELIST["PR_DETAIL_CLASS_NAME"] = "C.PR_DETAIL_CLASS_NAME"

PR_DETAIL_CSV_COLS = [
    ("PR_DETAIL_ID", "Mã đối tượng"),
    ("PR_DETAIL_NAME", "Tên đối tượng"),
    ("PR_DETAIL_CLASS_ID", "Mã nhóm"),
    ("PR_DETAIL_CLASS_NAME", "Tên nhóm đối tượng"),
    ("PR_DETAIL_TYPE_ID", "Mã loại ĐT"),
    ("PR_DETAIL_TYPE_NAME", "Tên loại đối tượng"),
    ("TAX_FILE_NUMBER", "Mã số thuế"),
    ("PHONE", "Điện thoại"),
    ("EMAIL", "Email"),
    ("ADDRESS", "Địa chỉ"),
    ("PR_ACCOUNT_ID", "Tài khoản ngầm định"),
    ("BANK_NAME", "Tên ngân hàng"),
    ("BANK_ACCOUNT", "Số tài khoản NH"),
    ("BANK_BRANCH", "Chi nhánh NH"),
    ("BANK_ACCOUNT_HOLDER", "Chủ tài khoản NH"),
    ("ACTIVE", "Trạng thái"),
    ("USER_ID", "Người tạo"),
    ("FAX", "Fax"),
    ("PROVINCE_ID", "Tỉnh thành"),
]


def _pr_detail_join_and_select(cursor):
    """Kiểm tra có bảng DM_PR_DETAIL_CLASS để JOIN lấy tên nhóm hay không."""
    has_class_tbl = False
    try:
        cursor.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'DM_PR_DETAIL_CLASS'")
        has_class_tbl = cursor.fetchone() is not None
    except Exception:
        pass

    col_list = ", ".join(f"P.{c}" for c in PR_DETAIL_BASE_COLUMNS)
    if has_class_tbl:
        join_sql = "FROM dbo.DM_PR_DETAIL P WITH (NOLOCK) LEFT JOIN dbo.DM_PR_DETAIL_CLASS C WITH (NOLOCK) ON P.PR_DETAIL_CLASS_ID = C.PR_DETAIL_CLASS_ID"
        select_list = f"{col_list}, C.PR_DETAIL_CLASS_NAME AS PR_DETAIL_CLASS_NAME"
    else:
        join_sql = "FROM dbo.DM_PR_DETAIL P WITH (NOLOCK)"
        select_list = f"{col_list}, NULL AS PR_DETAIL_CLASS_NAME"
    return join_sql, select_list


def _build_pr_detail_where(request_args):
    clauses = ["1=1"]
    params = []

    act = request_args.get("active", "").strip()
    if act in ("1", "0"):
        clauses.append("P.ACTIVE = ?")
        params.append(int(act))

    raw_classes = request_args.get("class_ids", "")
    classes = [c.strip() for c in raw_classes.split(",") if c.strip()]
    if classes:
        clauses.append(f"P.PR_DETAIL_CLASS_ID IN ({','.join(['?']*len(classes))})")
        params.extend(classes)

    raw_types = request_args.get("type_ids", "")
    types = [t.strip() for t in raw_types.split(",") if t.strip()]
    if types:
        clauses.append(f"P.PR_DETAIL_TYPE_ID IN ({','.join(['?']*len(types))})")
        params.extend(types)

    q = request_args.get("search", "").strip() or request_args.get("q", "").strip()
    if q:
        clauses.append("(P.PR_DETAIL_ID LIKE ? OR P.PR_DETAIL_NAME LIKE ? OR P.TAX_FILE_NUMBER LIKE ? OR P.PHONE LIKE ? OR P.ADDRESS LIKE ? OR P.BANK_ACCOUNT LIKE ?)")
        params.extend([f"%{q}%"] * 6)

    for field, arg in [
        ("P.PR_DETAIL_ID",        "s_id"),
        ("P.PR_DETAIL_CLASS_ID",  "s_class_id"),
        ("P.PR_DETAIL_TYPE_ID",   "s_type_id"),
        ("P.TAX_FILE_NUMBER",     "s_tax"),
        ("P.PHONE",               "s_phone"),
        ("P.PR_ACCOUNT_ID",       "s_acc_id"),
        ("P.BANK_ACCOUNT",        "s_bank_account"),
        ("P.USER_ID",             "s_user_id"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"{val}%")

    for field, arg in [
        ("P.PR_DETAIL_NAME",       "s_name"),
        ("C.PR_DETAIL_CLASS_NAME", "s_class_name"),
        ("P.EMAIL",                "s_email"),
        ("P.ADDRESS",              "s_address"),
        ("P.BANK_NAME",            "s_bank_name"),
        ("P.BANK_BRANCH",          "s_bank_branch"),
        ("P.BANK_ACCOUNT_HOLDER",  "s_holder"),
    ]:
        val = request_args.get(arg, "").strip()
        if val:
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{val}%")

    return " AND ".join(clauses), params


@app.route("/api/pr_detail")
@with_db_lock
def get_pr_detail():
    try:
        page       = int(request.args.get("page", 1))
        page_size  = int(request.args.get("page_size", 100))
        export_all = request.args.get("export_all") == "1"
        known_total = request.args.get("known_total")
        skip_count  = page > 1 and known_total is not None and not export_all

        conn = get_connection()
        cursor = conn.cursor()

        join_sql, select_list = _pr_detail_join_and_select(cursor)
        where_sql, params = _build_pr_detail_where(request.args)
        order_by_sql = _resolve_order_by(
            request.args, PR_DETAIL_SORT_WHITELIST,
            "P.PR_DETAIL_ID ASC"
        )

        if export_all:
            sql = f"SELECT {select_list} {join_sql} WHERE {where_sql} ORDER BY {order_by_sql}"
            cursor.execute(sql, params)
            columns = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()
            total_rows = len(raw_rows)
            active_cnt = sum(1 for r in raw_rows if "ACTIVE" in columns and r[columns.index("ACTIVE")] == 1)
            summary = {"total_rows": total_rows, "active_count": active_cnt, "inactive_count": total_rows - active_cnt}
        else:
            if skip_count:
                total_rows = int(known_total)
                summary = {"total_rows": total_rows}
            else:
                cursor.execute(f"SELECT COUNT(*), SUM(CASE WHEN P.ACTIVE=1 THEN 1 ELSE 0 END) {join_sql} WHERE {where_sql}", params)
                row = cursor.fetchone()
                total_rows = row[0] or 0
                active_cnt = row[1] or 0
                summary = {"total_rows": total_rows, "active_count": int(active_cnt), "inactive_count": int(total_rows - active_cnt)}

            offset = (page - 1) * page_size
            sql = f"""
                SELECT * FROM (
                    SELECT {select_list},
                           ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                    {join_sql}
                    WHERE {where_sql}
                ) AS RowConstrainedResult
                WHERE RowNum > ? AND RowNum <= ?
            """
            cursor.execute(sql, params + [offset, offset + page_size])
            columns = [c[0] for c in cursor.description]
            raw_rows = cursor.fetchall()

        rows = []
        for raw in raw_rows:
            r = dict(zip(columns, raw))
            for k in ("PR_DETAIL_ID", "PR_DETAIL_NAME", "PR_DETAIL_CLASS_ID", "PR_DETAIL_CLASS_NAME",
                      "PR_DETAIL_TYPE_ID", "TAX_FILE_NUMBER", "PHONE", "EMAIL", "ADDRESS",
                      "PR_ACCOUNT_ID", "BANK_NAME", "BANK_ACCOUNT", "BANK_BRANCH", "BANK_ACCOUNT_HOLDER", "USER_ID"):
                if k in r and r[k] is not None:
                    r[k] = str(r[k]).strip()
            tid = str(r.get("PR_DETAIL_TYPE_ID") or "").strip()
            r["PR_DETAIL_TYPE_NAME"] = PR_DETAIL_TYPE_MAP.get(tid, "")
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


@app.route("/api/pr_detail/count")
@with_db_lock
def get_pr_detail_count():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        join_sql, _ = _pr_detail_join_and_select(cursor)
        where_sql, params = _build_pr_detail_where(request.args)
        cursor.execute(f"SELECT COUNT(*) {join_sql} WHERE {where_sql}", params)
        total = cursor.fetchone()[0] or 0
        return jsonify({"status": "ok", "total": int(total)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/pr_detail/stream_csv", methods=["POST", "GET"])
def get_pr_detail_stream_csv():
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        conn = get_connection()
        cursor = conn.cursor()
        join_sql, select_list = _pr_detail_join_and_select(cursor)
        where_sql, params = _build_pr_detail_where(args)
        order_by_sql = _resolve_order_by(
            args, PR_DETAIL_SORT_WHITELIST,
            "P.PR_DETAIL_ID ASC"
        )
        sql = f"SELECT {select_list} {join_sql} WHERE {where_sql} ORDER BY {order_by_sql}"
        cols = _pick_export_cols(args, PR_DETAIL_CSV_COLS)

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            tid = str(d.get("PR_DETAIL_TYPE_ID") or "").strip()
            d["PR_DETAIL_TYPE_NAME"] = PR_DETAIL_TYPE_MAP.get(tid, "")
            if "ACTIVE" in d:
                d["ACTIVE"] = "Đang dùng" if d["ACTIVE"] == 1 else "Ngừng"
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname = f"DanhMucDoiTuong.{args.get('format', 'xlsx')}"
        job_id = _start_export_job(fname, headers, sql, params, transform, total_estimate)
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


def _like_literal(v):
    """Chữ người dùng gõ vào LIKE: % _ [ là chữ thường, không phải ký tự đại diện (khớp đúng cách lọc trên trang)."""
    return v.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


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

    # Ô Địa chỉ (v1.10.3): SALE_VIEW.ADDRESS — cột gốc (SALE_BASE_COLUMNS), chứa chữ đã gõ; % _ [ là chữ thường như lọc trên trang
    addr = request_args.get("s_address", "").strip()
    if addr:
        clauses.append("S.ADDRESS LIKE ?")
        params.append(f"%{_like_literal(addr)}%")

    # Ô lọc cột v1.10.1 — HTTT, nguồn đơn, ghi chú: cột phụ của SALE_VIEW, chỉ lọc khi DB có cột đó (Bẫy 5). DB không có →
    # màn hình để trống cả cột → không dòng nào khớp → 1=0. Tên HTTT/nguồn không nằm trong SALE_VIEW (map ở Python từ
    # DM_PAYMENT_METHOD / DM_EXTRA_2) → dò tên trong danh mục ra danh sách mã rồi IN, khớp đúng chữ đang hiện trên màn hình.
    dim_search = [(col, request_args.get(a_id, "").strip(), request_args.get(a_name, "").strip(), map_key)
                  for col, a_id, a_name, map_key in (("PAYMENT_METHOD_ID", "s_pay_id", "s_pay_name", "pay"),
                                                     ("EXTRA_ID_2", "s_src_id", "s_src_name", "extra2"))]
    comments = request_args.get("s_comments", "").strip()
    if comments or any(v_id or v_name for _, v_id, v_name, _ in dim_search):
        dim = _sale_dim_info()
        for col, v_id, v_name, map_key in dim_search:
            if not (v_id or v_name):
                continue
            if col not in dim["cols"]:
                clauses.append("1=0")
                continue
            expr = f"CAST(S.{col} AS NVARCHAR(100))"
            if v_id:
                clauses.append(f"{expr} LIKE ?")
                params.append(f"{_like_literal(v_id)}%")
            if v_name:
                q = v_name.lower()
                ids = [k for k, name in dim[map_key].items() if k and q in (name or '').lower()]
                if not ids:
                    clauses.append("1=0")
                elif len(ids) <= 1000:   # quá nhiều mã (hiếm) → bỏ lọc server, vẫn lọc trên trang
                    clauses.append(f"{expr} IN ({','.join('?' * len(ids))})")
                    params.extend(ids)
        if comments:
            if "COMMENTS" in dim["cols"]:
                clauses.append("S.COMMENTS LIKE ?")
                params.append(f"%{_like_literal(comments)}%")
            else:
                clauses.append("1=0")

    # Ô "Trả": '1' = chỉ hàng trả lại; giá trị khác (gõ chữ không khớp "trả") → không dòng nào
    s_ret = request_args.get("s_return", "").strip()
    if s_ret == "1":
        clauses.append("ISNULL(S.IS_RETURN,0) = 1")
    elif s_ret:
        clauses.append("1=0")

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

    num_cols = dict(SALE_NUM_SEARCH)
    if any((request_args.get("n_" + c, "") or "").strip() for c in SALE_EXTRA_NUM_SEARCH):
        cols = _sale_dim_info()["cols"]
        num_cols.update({c: (f"S.{c}" if c in cols else None, 0) for c in SALE_EXTRA_NUM_SEARCH})
    n_clauses, n_params = _num_prefix_where(request_args, num_cols)
    clauses += n_clauses
    params += n_params
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
        # Tổng cột phụ (v1.10.3): Doanh thu 511 / Doanh thu trước thuế — chỉ khi SALE_VIEW có cột (Bẫy 5). Thiếu cột → summary không có
        # khoá → ô tổng trên màn hình để trống.
        sum_extra = [(c, k) for c, k in (("INCOME_AMOUNT", "income_amount"), ("VAT_INCOME_AMOUNT", "vat_income_amount")) if c in extra_cols]
        SUM_SQL += "".join(f", SUM(ISNULL(S.{c},0)) AS S_{c}" for c, _ in sum_extra)

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
            for c, k in sum_extra:
                summary[k] = sum(float(r[qi[c]] or 0) for r in raw_rows) if c in qi else 0
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
                for i, (_, k) in enumerate(sum_extra):
                    summary[k] = float(row[7 + i] or 0)

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
    ("INCOME_AMOUNT","Doanh thu 511"), ("VAT_INCOME_AMOUNT","Doanh thu trước thuế"),
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
        sql = f"SELECT {_sale_select_list(need_join, extra_cols)} {join_from} WHERE {where_sql}{_CHUNK_MARK} ORDER BY {order_by_sql} OPTION (RECOMPILE)"
        day_split = _list_day_split(order_by_sql, "S.TRAN_DATE", join_from, where_sql, params, " OPTION (RECOMPILE)")
        cols = _pick_export_cols(args, SALE_CSV_COLS, TRAN_NAME_EXPORT_COL)
        tran_map = _tran_name_map() if any(k == "TRAN_NAME" for k, _ in cols) else None

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            if not need_join:
                d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
                d['EXPENSE_NAME']      = exp_map.get((str(d.get('EXPENSE_ID') or '')).strip(), '')
            d['WAREHOUSE_NAME'] = wh_map.get((str(d.get('WAREHOUSE_ID') or '')).strip(), '')
            d['UNIT_NAME']      = unit_map.get((str(d.get('UNIT_ID') or '')).strip(), '')
            d['PAYMENT_METHOD_NAME'] = dim["pay"].get((str(d.get('PAYMENT_METHOD_ID') or '')).strip(), '')
            d['EXTRA_NAME_2']        = dim["extra2"].get((str(d.get('EXTRA_ID_2') or '')).strip(), '')
            if tran_map is not None and 'TRAN_NAME' not in d:
                d['TRAN_NAME'] = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname   = f"ChungTuBanHang_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, params, transform, total_estimate, day_split)
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

    n_clauses, n_params = _num_prefix_where(request_args, VOUCHER_NUM_SEARCH)
    clauses += n_clauses
    params += n_params
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
    (A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0)) AS CON_LAI,
    PD.PR_DETAIL_NAME AS PR_DETAIL_NAME""")


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


# Tên đối tượng JOIN thẳng DM_PR_DETAIL theo mã trên INCOME_ALLOCATION (Trum 29/09): trước lấy từ danh mục nạp sẵn — danh mục đó chỉ
# có đối tượng ACTIVE=1 nên khách đã ngừng dùng bị trống tên.
INCOME_ALLOC_FROM = ("FROM dbo.INCOME_ALLOCATION A WITH (NOLOCK) LEFT JOIN D ON D.FR_KEY = A.PR_KEY "
                     "LEFT JOIN dbo.DM_PR_DETAIL PD WITH (NOLOCK) ON PD.PR_DETAIL_ID = A.PR_DETAIL_ID")


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
        r['PR_DETAIL_NAME']    = (r.get('PR_DETAIL_NAME') or '').strip() or pr_map.get((str(r.get('PR_DETAIL_ID') or '')).strip(), '')
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
        cols = _pick_export_cols(args, INCOME_ALLOC_CSV_COLS)

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
            d['ITEM_NAME']         = item_map.get((str(d.get('ITEM_ID') or '')).strip(), '')
            d['PR_DETAIL_NAME']    = (d.get('PR_DETAIL_NAME') or '').strip() or pr_map.get((str(d.get('PR_DETAIL_ID') or '')).strip(), '')
            d['TRAN_NAME']         = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            d['ALLOCATION_METHOD_NAME'] = ALLOC_METHOD_MAP.get(str(d.get('ALLOCATION_METHOD') or '').strip(),
                                                               str(d.get('ALLOCATION_METHOD') or ''))
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
        fname   = f"DoanhThuChoPhanBo_{args.get('from_date','').replace('/','')}-{args.get('to_date','').replace('/','')}.{args.get('format', 'csv')}"
        job_id  = _start_export_job(fname, headers, sql, d_params + w_params, transform, total_estimate)
        return jsonify({"status": "ok", "job_id": job_id, "filename": fname})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ======================================================================
# DOANH THU CHỜ PHÂN BỔ THEO THÁNG (v1.10.6, Trum 29/09 — theo mẫu "Bao cao_DTCTH_sample.xlsx")
# ----------------------------------------------------------------------
# Mỗi khoản INCOME_ALLOCATION 1 dòng, số phân bổ trải ra từng tháng của khoảng [từ tháng, đến tháng] (tối đa 36 tháng):
#   • Tháng m     = SUM(DETAIL.AMOUNT) các kỳ có DAY_END trong tháng m. Kỳ vắt nhiều tháng (tiêu thức Quý/Năm) tính vào tháng kết
#                   thúc kỳ — cùng cách tính Lũy kế của danh sách DT chờ phân bổ → cột Còn lại 2 bảng bằng nhau (Trum duyệt).
#   • LK trước kỳ = các kỳ có DAY_END trước ngày 1 của "từ tháng" (khoảng T1 → Tn cùng năm: mẫu gọi "Lũy kế năm trước").
#   • LK trong kỳ = cộng các tháng · Còn lại = Doanh thu − LK trước kỳ − LK trong kỳ.
#   • Tên đối tượng: JOIN thẳng DM_PR_DETAIL theo PR_DETAIL_ID (cả đối tượng ngừng dùng — danh mục nạp sẵn chỉ có ACTIVE=1).
#   • Tên tài khoản DT (Loại doanh thu) = DM_ACCOUNT.ACCOUNT_NAME của ACCOUNT_ID_DES.
#   • Số Hóa đơn = SALE.VAT_TRAN_NO, Số hợp đồng = SALE.COMMENTS của phiếu gốc (Trum chốt). Nối theo Mã + Số + Ngày CT + Đơn vị:
#     KHÔNG dùng PR_KEY_CTU — PR_KEY trùng giữa SALE và VOUCHER (DB demo trùng 120 khoá) và có dòng trỏ vào khoá CHI TIẾT;
#     số phiếu lặp lại giữa các đơn vị (TRUNGDEMO 1.049 phiếu / 894 bộ Mã+Số+Ngày, thêm Đơn vị → 1.048). Phiếu không phải
#     bán hàng (không có trong SALE) → 2 cột này trống.
# Dòng hiện: mọi khoản có ngày CT tới hết "đến tháng" (Trum: "hiện hết"); Trạng thái thẻ / Giá trị phân bổ để người dùng tự lọc.
# ======================================================================
INCOME_MONTH_MAX = 36
INCOME_MONTH_BASE = ["PR_KEY", "ORGANIZATION_ID", "TRAN_ID", "TRAN_NO", "TRAN_DATE", "USE_DATE", "DESCRIPTION", "ITEM_ID",
                     "ALLOCATION_RATE", "INCOME_AMOUNT", "ACCOUNT_ID_DES", "PR_DETAIL_ID", "ACTIVE"]
_sale_link_cache = {}


def _add_month(d, n=1):
    k = d.year * 12 + d.month - 1 + n
    return date(k // 12, k % 12 + 1, 1)


def _income_month_range(args):
    """from_month / to_month dạng 'MM/YYYY' → (danh sách ngày 1 của từng tháng, (nhãn LK trước, nhãn LK trong kỳ)).
    Thiếu / sai → năm nay: tháng 1 → tháng hiện tại. Quá INCOME_MONTH_MAX tháng → giữ các tháng CUỐI (tới "đến tháng")."""
    today = date.today()

    def parse(s, dflt):
        try:
            m, y = str(s or '').strip().split('/')
            return date(int(y), int(m), 1)
        except (ValueError, TypeError):
            return dflt
    f = parse(args.get('from_month'), date(today.year, 1, 1))
    t = parse(args.get('to_month'), date(today.year, today.month, 1))
    if t < f:
        f, t = t, f
    if (t.year * 12 + t.month) - (f.year * 12 + f.month) + 1 > INCOME_MONTH_MAX:
        f = _add_month(t, 1 - INCOME_MONTH_MAX)
    months, d = [], f
    while d <= t:
        months.append(d)
        d = _add_month(d)
    labels = (("Lũy kế năm trước", "Lũy kế năm nay") if f.month == 1 and f.year == t.year
              else ("Lũy kế trước kỳ", "Lũy kế trong kỳ"))
    return months, labels


def _month_key(m):
    return f"M{m.year:04d}{m.month:02d}"


def _income_month_cte(months, sale=True):
    """CTE D (tổng chi tiết theo từng tháng) + CTE S (số HĐ, số hợp đồng từ SALE nếu DB có đủ cột — chỉ bản xuất còn dùng S; danh
    sách tra SALE theo khoá của trang, xem _income_month_sale_lookup). Ngày ghi thẳng dạng 'YYYYMMDD' (tự sinh từ date, không
    nhận chữ người dùng) → khỏi 70 tham số và khỏi lệch thứ tự '?' (Bẫy 2)."""
    lit = lambda d: "'" + d.strftime('%Y%m%d') + "'"
    start, end_next = months[0], _add_month(months[-1])
    parts = [f"SUM(CASE WHEN DAY_END < {lit(start)} THEN AMOUNT ELSE 0 END) AS CUM_BEFORE"]
    for m in months:
        parts.append(f"SUM(CASE WHEN DAY_END >= {lit(m)} AND DAY_END < {lit(_add_month(m))} THEN AMOUNT ELSE 0 END) AS {_month_key(m)}")
    parts.append(f"SUM(CASE WHEN DAY_END >= {lit(start)} AND DAY_END < {lit(end_next)} THEN AMOUNT ELSE 0 END) AS CUM_IN")
    # CUM_AMT = lũy kế tới hết kỳ — tên trùng CTE của danh sách cũ để dùng lại luật lọc "Giá trị phân bổ" (_build_income_alloc_where)
    parts.append(f"SUM(CASE WHEN DAY_END < {lit(end_next)} THEN AMOUNT ELSE 0 END) AS CUM_AMT")
    sql = ("WITH D AS (SELECT FR_KEY, " + ", ".join(parts) +
           " FROM dbo.INCOME_ALLOCATION_DETAIL WITH (NOLOCK) GROUP BY FR_KEY)")
    if sale and _sale_link_ok():
        sql += """, S AS (
            SELECT S.TRAN_ID, S.TRAN_NO, S.TRAN_DATE, S.ORGANIZATION_ID,
                   MAX(S.VAT_TRAN_NO) AS VAT_TRAN_NO, MAX(CAST(S.COMMENTS AS NVARCHAR(4000))) AS CONTRACT_NO
            FROM dbo.SALE S WITH (NOLOCK)
            WHERE EXISTS (SELECT 1 FROM dbo.INCOME_ALLOCATION X WITH (NOLOCK)
                          WHERE X.TRAN_ID = S.TRAN_ID AND X.TRAN_NO = S.TRAN_NO AND X.TRAN_DATE = S.TRAN_DATE
                            AND X.ORGANIZATION_ID = S.ORGANIZATION_ID)
            GROUP BY S.TRAN_ID, S.TRAN_NO, S.TRAN_DATE, S.ORGANIZATION_ID)"""
    return sql


def _sale_link_ok():
    """SALE có đủ cột để lấy Số HĐ / Số hợp đồng không (dò 1 lần mỗi CSDL — Bẫy 5: SELECT cột không có là sập 500 + ngắt pool)."""
    db = (session.get('db_config') or {}).get('database', '')
    if db not in _sale_link_cache:
        try:
            cur = get_connection().cursor()
            cur.execute("SELECT UPPER(COLUMN_NAME) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'SALE'")
            have = {r[0] for r in cur.fetchall()}
            _sale_link_cache[db] = {'TRAN_ID', 'TRAN_NO', 'TRAN_DATE', 'ORGANIZATION_ID', 'VAT_TRAN_NO', 'COMMENTS'} <= have
        except Exception:
            _sale_link_cache[db] = False
    return _sale_link_cache[db]


def _income_month_select(months):
    have = set(_income_alloc_cols())
    base = [f"A.{c}" for c in INCOME_MONTH_BASE if c in have]
    nums = (["ISNULL(D.CUM_BEFORE,0) AS CUM_BEFORE"] + [f"ISNULL(D.{_month_key(m)},0) AS {_month_key(m)}" for m in months]
            + ["ISNULL(D.CUM_IN,0) AS CUM_IN", "(A.INCOME_AMOUNT - ISNULL(D.CUM_BEFORE,0) - ISNULL(D.CUM_IN,0)) AS CON_LAI",
               "PD.PR_DETAIL_NAME AS PR_DETAIL_NAME", "AC.ACCOUNT_NAME AS ACCOUNT_NAME_DES"])
    return ", ".join(base + nums)


INCOME_MONTH_FROM = """FROM dbo.INCOME_ALLOCATION A WITH (NOLOCK)
    LEFT JOIN D ON D.FR_KEY = A.PR_KEY
    LEFT JOIN dbo.DM_PR_DETAIL PD WITH (NOLOCK) ON PD.PR_DETAIL_ID = A.PR_DETAIL_ID
    LEFT JOIN dbo.DM_ACCOUNT   AC WITH (NOLOCK) ON AC.ACCOUNT_ID   = A.ACCOUNT_ID_DES"""


def _income_month_sale_cols():
    return ("S.VAT_TRAN_NO AS VAT_TRAN_NO, S.CONTRACT_NO AS CONTRACT_NO" if _sale_link_ok()
            else "CAST(NULL AS NVARCHAR(20)) AS VAT_TRAN_NO, CAST(NULL AS NVARCHAR(200)) AS CONTRACT_NO")


_INCOME_MONTH_SALE_JOIN = ("LEFT JOIN S ON S.TRAN_ID = T.TRAN_ID AND S.TRAN_NO = T.TRAN_NO AND S.TRAN_DATE = T.TRAN_DATE "
                           "AND S.ORGANIZATION_ID = T.ORGANIZATION_ID")


def _income_month_where(args, months):
    """Dùng lại bộ lọc của danh sách DT chờ phân bổ (A.TRAN_DATE ≤ hết "đến tháng", ACTIVE, Giá trị phân bổ, đơn vị, hàng,
    đối tượng, TK đích, số CT…). Mặc định: mọi trạng thái thẻ (không gửi active). alloc_status: '' = còn giá trị đầu kỳ,
    'remaining' = còn giá trị cuối kỳ, 'done' = hết trong kỳ, 'in_period' = có phân bổ trong kỳ, 'all' = tất cả.
    Trum 29/09: thẻ đã hết giá trị TRƯỚC kỳ (Doanh thu − Lũy kế trước kỳ = 0) thì bỏ qua — mọi lựa chọn trừ 'all'."""
    last_day = date.fromordinal(_add_month(months[-1]).toordinal() - 1)
    a = {k: args.get(k) for k in args}
    a['from_date'] = months[0].strftime("%d/%m/%Y")
    a['to_date'] = last_day.strftime("%d/%m/%Y")
    a['active'] = args.get('active', '')
    status = args.get('alloc_status', '')
    a['alloc_status'] = status if status in ('remaining', 'done') else ''
    where_sql, params, _f, _t = _build_income_alloc_where(a)
    if status != 'all':
        where_sql += " AND (A.INCOME_AMOUNT - ISNULL(D.CUM_BEFORE,0)) <> 0"
    if status == 'in_period':
        where_sql += " AND ISNULL(D.CUM_IN,0) <> 0"
    return where_sql, params


def _income_month_sort(months):
    wl = {k: v for k, v in _income_alloc_sort_whitelist().items() if k != "PERIOD_AMT"}
    wl.update({
        "CUM_BEFORE": "ISNULL(D.CUM_BEFORE,0)", "CUM_IN": "ISNULL(D.CUM_IN,0)",
        "CON_LAI": "(A.INCOME_AMOUNT - ISNULL(D.CUM_AMT,0))",
        "PR_DETAIL_NAME": "PD.PR_DETAIL_NAME", "ACCOUNT_NAME_DES": "AC.ACCOUNT_NAME",
    })
    wl.update({_month_key(m): f"ISNULL(D.{_month_key(m)},0)" for m in months})
    return wl


def _income_month_order(args, months):
    """ORDER BY của danh sách + bản xuất (cùng một thứ tự — Bẫy 6). Thêm A.PR_KEY làm khoá phụ: dòng trùng khoá sắp xếp (cùng ngày +
    số CT…) có thứ tự cố định → sang trang không lặp / sót dòng."""
    sql = _resolve_order_by(args, _income_month_sort(months), "A.TRAN_DATE, A.TRAN_NO")
    return sql if re.search(r"\bA\.PR_KEY\b", sql) else sql + ", A.PR_KEY"   # \b: sắp theo A.PR_KEY_CTU vẫn thêm khoá phụ


def _income_month_page_sql(months, where_sql, order_by_sql, totals, paged):
    """Câu lấy trang (v1.10.7 — Trum 29/09: lọc 3 tháng gần 3 phút). Trước: câu đếm riêng + câu trang, mỗi câu gom LẠI toàn bộ
    lịch phân bổ (D — không có index FR_KEY), câu trang còn sắp xếp nguyên dòng rồi nối CTE S gom cả bảng SALE.
      • K sắp xếp + đánh số trên cột HẸP (khoá thẻ + các số của D), xong mới nối lấy đủ cột cho các dòng của trang.
      • totals → cộng tổng bằng COUNT/SUM … OVER () ngay trong câu này: D chỉ tính 1 lần (bỏ câu đếm riêng). Tổng khớp câu đếm cũ
        từng số (đo DS_TEST_PERF 29/09). App gửi lại tổng khi chỉ đổi trang / sắp xếp → totals=False.
      • Số HĐ / Số hợp đồng không nối ở đây — _income_month_sale_lookup tra riêng cho các dòng trả về.
    DB giả cỡ thật (125k thẻ, 1,33 triệu dòng lịch, SALE 400k), 3 tháng: đếm 0,61 s + trang 2,07 s → 0,96 s + tra SALE 0,03 s."""
    nums = ["CUM_BEFORE"] + [_month_key(m) for m in months] + ["CUM_IN"]
    k_cols = [f"ISNULL(D.{n},0) AS {n}" for n in nums]
    out_tot = ""
    if totals:
        k_cols += (["COUNT(*) OVER () AS T_ROWS", "SUM(A.INCOME_AMOUNT) OVER () AS T_INCOME_AMOUNT"]
                   + [f"SUM(ISNULL(D.{n},0)) OVER () AS T_{n}" for n in nums]
                   + ["SUM(A.INCOME_AMOUNT - ISNULL(D.CUM_BEFORE,0) - ISNULL(D.CUM_IN,0)) OVER () AS T_CON_LAI"])
        out_tot = ", " + ", ".join(f"K.T_{n}" for n in ["ROWS", "INCOME_AMOUNT"] + nums + ["CON_LAI"])
    have = set(_income_alloc_cols())
    base = [f"A.{c}" for c in INCOME_MONTH_BASE if c in have]
    return f"""{_income_month_cte(months, sale=False)}, K AS (
            SELECT A.PR_KEY AS K_KEY, {", ".join(k_cols)}, ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
            {INCOME_MONTH_FROM} WHERE {where_sql})
        SELECT {", ".join(base)}, {", ".join("K." + n for n in nums)}, (A.INCOME_AMOUNT - K.CUM_BEFORE - K.CUM_IN) AS CON_LAI,
               PD.PR_DETAIL_NAME AS PR_DETAIL_NAME, AC.ACCOUNT_NAME AS ACCOUNT_NAME_DES{out_tot}
        FROM K JOIN dbo.INCOME_ALLOCATION A WITH (NOLOCK) ON A.PR_KEY = K.K_KEY
            LEFT JOIN dbo.DM_PR_DETAIL PD WITH (NOLOCK) ON PD.PR_DETAIL_ID = A.PR_DETAIL_ID
            LEFT JOIN dbo.DM_ACCOUNT   AC WITH (NOLOCK) ON AC.ACCOUNT_ID   = A.ACCOUNT_ID_DES
        {"WHERE K.RowNum > ? AND K.RowNum <= ?" if paged else ""} ORDER BY K.RowNum"""


def _income_month_count(cursor, months, where_sql, w_params, sum_keys):
    """Câu đếm + cộng tổng riêng — chỉ còn dùng khi trang xin vượt quá trang cuối (câu trang không trả dòng nào để đọc tổng)."""
    mkeys = [_month_key(m) for m in months]
    cursor.execute(f"""{_income_month_cte(months, sale=False)}
        SELECT COUNT(*), SUM(A.INCOME_AMOUNT), SUM(ISNULL(D.CUM_BEFORE,0)), {", ".join(f"SUM(ISNULL(D.{k},0))" for k in mkeys)},
               SUM(ISNULL(D.CUM_IN,0)), SUM(A.INCOME_AMOUNT - ISNULL(D.CUM_BEFORE,0) - ISNULL(D.CUM_IN,0))
        {INCOME_MONTH_FROM} WHERE {where_sql}""", w_params)
    row = cursor.fetchone()
    return int(row[0] or 0), {k: float(v or 0) for k, v in zip(sum_keys, row[1:])}


# Tra SALE theo lô: danh sách ngày CT / số CT ĐỆM tới các cỡ cố định (lặp giá trị cuối) → câu SQL giống nhau giữa các trang, SQL Server
# dùng lại plan đã biên dịch. Danh sách IN 1.000 số CT viết thẳng biên dịch mất 0,5–2 s MỖI trang (đo 29/09), VALUES đệm: 33–68 ms 1 lần.
_IM_SALE_NOS = (64, 256, 1024, 1536)   # số CT khác nhau tối đa mỗi lượt = 1.536 (+ ≤ 128 ngày → dưới trần 2.100 tham số)
_IM_SALE_DATES = (8, 32, 128)          # lượt có > 128 ngày CT khác nhau (trang sắp theo cột khác, ngày rải rác) → lọc khoảng ngày


def _pad_to(xs, sizes):
    n = next((s for s in sizes if s >= len(xs)), len(xs))
    return xs + [xs[-1]] * (n - len(xs))


def _sql_dt(d):
    """date / datetime → 'YYYYMMDD HH:MM:SS[.mmm]': SQL đổi chuỗi sang kiểu cột (index TRAN_DATE vẫn dùng được), không phụ thuộc
    DATEFORMAT (Bẫy 3). Cũng là khoá so ngày ở Python."""
    s = d.strftime('%Y%m%d %H:%M:%S')
    ms = getattr(d, 'microsecond', 0) // 1000
    return f"{s}.{ms:03d}" if ms else s


def _as_dt(v):
    """Giá trị ngày từ DB → date/datetime. Driver "SQL Server" (mặc định của app) trả CHUỖI cho cột kiểu date / datetime2
    ('2026-01-15', '2026-01-15 10:00:00.0000000') — iPOS dùng smalldatetime (ra datetime) nhưng DB khách khác cấu trúc thì vẫn khớp."""
    if isinstance(v, (date, datetime)):
        return v
    if isinstance(v, str):
        s = v.strip()
        for n, f in ((19, '%Y-%m-%d %H:%M:%S'), (10, '%Y-%m-%d')):
            try:
                return datetime.strptime(s[:n], f)
            except ValueError:
                pass
    return None


def _income_month_sale_lookup(cursor, rows):
    """Số HĐ (SALE.VAT_TRAN_NO) / Số hợp đồng (SALE.COMMENTS) cho ĐÚNG các dòng đang trả về — thay CTE S gom cả bảng SALE mỗi lần
    lấy trang. Tra SALE theo ngày CT + số CT của các dòng (index TRAN_DATE), rồi khớp đủ Mã + Số + Ngày + Đơn vị như phép nối cũ
    (Bẫy 26), so khoá kiểu collation CI của iPOS: bỏ khoảng trắng cuối, không phân biệt hoa thường; nhiều phiếu SALE cùng khoá →
    MAX như cũ. Chia lượt theo NGÀY (khoá xếp theo ngày CT): ≤ 128 ngày → tra từng ngày; nhiều hơn → khoảng ngày của lượt.
    Gán VAT_TRAN_NO / CONTRACT_NO vào từng dòng (TRAN_DATE còn là ngày, chưa đổi chữ). Trả số lượt đã chạy."""
    norm = lambda s: str(s).rstrip(' ').upper()
    want, pairs = {}, set()
    for r in rows:
        r['VAT_TRAN_NO'] = r['CONTRACT_NO'] = None
        tid, no, d, org = r.get('TRAN_ID'), r.get('TRAN_NO'), _as_dt(r.get('TRAN_DATE')), r.get('ORGANIZATION_ID')
        if tid is None or no is None or org is None or d is None:
            continue   # thiếu khoá → phép nối cũ cũng không khớp
        want.setdefault((_sql_dt(d), norm(no), norm(tid), norm(org)), []).append(r)
        pairs.add((_sql_dt(d), no))
    chunks, dates, nos = [], set(), set()
    for d, no in sorted(pairs):
        if no not in nos and len(nos) >= _IM_SALE_NOS[-1]:
            chunks.append((dates, nos))
            dates, nos = set(), set()
        dates.add(d)
        nos.add(no)
    if nos:
        chunks.append((dates, nos))
    for dates, nos in chunks:
        ds, ns = sorted(dates), _pad_to(sorted(nos), _IM_SALE_NOS)
        if len(ds) <= _IM_SALE_DATES[-1]:
            ds = _pad_to(ds, _IM_SALE_DATES)
            date_sql = f"S.TRAN_DATE IN ({','.join('?' * len(ds))})"
        else:
            ds = [ds[0], ds[-1]]
            date_sql = "S.TRAN_DATE >= ? AND S.TRAN_DATE <= ?"
        cursor.execute(f"""SELECT S.TRAN_ID, S.TRAN_NO, S.TRAN_DATE, S.ORGANIZATION_ID,
                                  MAX(S.VAT_TRAN_NO), MAX(CAST(S.COMMENTS AS NVARCHAR(4000)))
                           FROM dbo.SALE S WITH (NOLOCK)
                           WHERE {date_sql} AND S.TRAN_NO IN (SELECT n FROM (VALUES {','.join(['(?)'] * len(ns))}) AS X(n))
                           GROUP BY S.TRAN_ID, S.TRAN_NO, S.TRAN_DATE, S.ORGANIZATION_ID""", ds + ns)
        for tid, no, d, org, vat, contract in cursor.fetchall():
            d = _as_dt(d)
            if tid is None or no is None or org is None or d is None:
                continue
            for r in want.get((_sql_dt(d), norm(no), norm(tid), norm(org)), ()):
                r['VAT_TRAN_NO'], r['CONTRACT_NO'] = vat, contract
    return len(chunks)


def _income_month_meta(months, labels):
    return {"months": [{"key": _month_key(m), "year": m.year, "month": m.month} for m in months],
            "labels": {"CUM_BEFORE": labels[0], "CUM_IN": labels[1]}}


def _income_month_row(r, months):
    for dk in ("TRAN_DATE", "USE_DATE"):
        v = r.get(dk)
        if isinstance(v, (date, datetime)):
            r[dk] = v.strftime("%d/%m/%Y")
    for nk in ["ALLOCATION_RATE", "INCOME_AMOUNT", "CUM_BEFORE", "CUM_IN", "CON_LAI"] + [_month_key(m) for m in months]:
        v = r.get(nk)
        if v is not None:
            try:
                r[nk] = float(v)
            except (TypeError, ValueError):
                pass
    for sk in ("PR_DETAIL_NAME", "ACCOUNT_NAME_DES", "CONTRACT_NO", "VAT_TRAN_NO"):
        if isinstance(r.get(sk), str):
            r[sk] = r[sk].strip()
    r.pop('RowNum', None)
    return r


@app.route("/api/income_alloc_month")
@with_db_lock
def get_income_alloc_month():
    """Doanh thu chờ phân bổ theo tháng — xem khối chú thích ở trên. Tốc độ (v1.10.7): 1 câu lấy trang kèm tổng
    (_income_month_page_sql) + tra Số HĐ / Số hợp đồng cho các dòng của trang (_income_month_sale_lookup). Header Server-Timing
    (page / count / sale / build / json / total — ms) → thanh trạng thái; mỗi lần truy vấn ghi 1 dòng vào datastudio.log."""
    try:
        t_start = time.perf_counter()
        tm = {}
        args = request.args
        page = max(1, int(args.get("page", 1)))
        page_size = max(1, int(args.get("page_size", 1000)))
        export_all = args.get("export_all") == "1"
        # App gửi known_* khi bộ lọc không đổi so với lần cộng tổng trước (đổi trang, sắp xếp) → khỏi cộng lại. Bấm Truy vấn thì
        # không gửi → luôn cộng lại (như sổ cái — Bẫy 20).
        known_total, known_sums = args.get("known_total"), args.get("known_sums")
        reuse = known_total is not None and known_sums is not None and not export_all
        months, labels = _income_month_range(args)
        mkeys = [_month_key(m) for m in months]
        where_sql, w_params = _income_month_where(args, months)
        order_by_sql = _income_month_order(args, months)
        cursor = get_connection().cursor()
        sum_keys = ["income_amount", "cum_before"] + [k.lower() for k in mkeys] + ["cum_in", "con_lai"]
        tot_cols = ["T_INCOME_AMOUNT", "T_CUM_BEFORE"] + [f"T_{k}" for k in mkeys] + ["T_CUM_IN", "T_CON_LAI"]

        offset = (page - 1) * page_size
        t = time.perf_counter()
        cursor.execute(_income_month_page_sql(months, where_sql, order_by_sql, totals=not reuse, paged=not export_all),
                       w_params + ([] if export_all else [offset, offset + page_size]))
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, raw)) for raw in cursor.fetchall()]
        tm['page'] = time.perf_counter() - t
        mode = ['rownum']
        if reuse:
            total_rows = int(known_total)
            try:
                summary = json.loads(known_sums)
            except (TypeError, ValueError):
                summary = {}
            mode.append('count-reuse')
        elif rows:
            total_rows = int(rows[0]['T_ROWS'] or 0)
            summary = {k: float(rows[0][c] or 0) for k, c in zip(sum_keys, tot_cols)}
            mode.append('totals')
        elif export_all or page == 1:
            total_rows, summary = 0, {k: 0.0 for k in sum_keys}
            mode.append('totals')
        else:   # xin trang vượt quá trang cuối (bộ lọc vừa đổi) → không có dòng để đọc tổng → đếm riêng
            t = time.perf_counter()
            total_rows, summary = _income_month_count(cursor, months, where_sql, w_params, sum_keys)
            tm['count'] = time.perf_counter() - t
            mode.append('count')
        for r in rows:
            for c in ['T_ROWS'] + tot_cols:
                r.pop(c, None)

        lookups = 0
        if rows and _sale_link_ok():
            t = time.perf_counter()
            lookups = _income_month_sale_lookup(cursor, rows)
            tm['sale'] = time.perf_counter() - t
        else:
            for r in rows:
                r['VAT_TRAN_NO'] = r['CONTRACT_NO'] = None
        t = time.perf_counter()
        rows = [_income_month_row(r, months) for r in rows]
        tm['build'] = time.perf_counter() - t
        if export_all:
            total_rows = len(rows)

        t = time.perf_counter()
        resp = jsonify({
            "status": "ok", "data": rows, "summary": summary, **_income_month_meta(months, labels),
            "pagination": {"total_rows": total_rows, "total_pages": max(1, (total_rows + page_size - 1) // page_size),
                           "page": 1 if export_all else page},
        })
        tm['json'] = time.perf_counter() - t
        tm['total'] = time.perf_counter() - t_start
        resp.headers['Server-Timing'] = _server_timing(tm, "+".join(mode)) + f', lookups;desc="{lookups}"'
        if _export_log_path():   # Trum gửi datastudio.log là biết khâu nào chậm trên DB thật
            _xlog.info("dt theo thang: CSDL %s, %d thang, trang %d x %d, %d dong, %s: sql trang %.2fs%s, tra SALE %.2fs (%d luot), tong %.2fs",
                       (session.get('db_config') or {}).get('database', ''), len(months), page, page_size, total_rows,
                       "+".join(mode), tm['page'], f", dem rieng {tm['count']:.2f}s" if 'count' in tm else "",
                       tm.get('sale', 0), lookups, tm['total'])
        return resp
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        logger.error(f"Error in get_income_alloc_month: {msg}")
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


@app.route("/api/income_alloc_month/count")
@with_db_lock
def get_income_alloc_month_count():
    try:
        months, _labels = _income_month_range(request.args)
        where_sql, w_params = _income_month_where(request.args, months)
        cursor = get_connection().cursor()
        cursor.execute(f"{_income_month_cte(months, sale=False)} SELECT COUNT(*) {INCOME_MONTH_FROM} WHERE {where_sql}", w_params)
        return jsonify({"status": "ok", "total": int(cursor.fetchone()[0] or 0)})
    except Exception as e:
        msg = str(e)
        if "đăng nhập" not in msg:
            invalidate_pool()
        return jsonify({"status": "error", "message": msg}), 401 if "đăng nhập" in msg else 500


def _income_month_export_cols(months, labels):
    """Bộ cột xuất = đúng thứ tự file mẫu. Khoá 'MONTHS' (App gửi khi xuất "Như đang xem") = cả dải cột tháng."""
    return ([("ORGANIZATION_ID", "Đơn vị"), ("TRAN_ID", "Mã ctừ"), ("TRAN_NO", "Số ctừ"), ("TRAN_DATE", "Ngày ctừ"),
             ("USE_DATE", "Ngày pbổ"), ("DESCRIPTION", "Diễn giải"), ("ITEM_ID", "Hàng hóa"), ("ALLOCATION_RATE", "Tỷ lệ pb"),
             ("INCOME_AMOUNT", "Doanh thu"), ("ACCOUNT_ID_DES", "Tk đích"), ("PR_DETAIL_ID", "Mã đối tượng"),
             ("CONTRACT_NO", "Số hợp đồng"), ("VAT_TRAN_NO", "Số Hóa đơn"), ("CUM_BEFORE", labels[0])]
            + [(_month_key(m), f"{m.month:02d}/{m.year}") for m in months]
            + [("CUM_IN", labels[1]), ("CON_LAI", "Giá trị còn lại"), ("PR_DETAIL_NAME", "Tên đối tượng"),
               ("ACCOUNT_NAME_DES", "Tên tài khoản DT (Loại doanh thu)")])


def _income_month_xlsx_spec(cols, months):
    """Như file mẫu: tiêu đề cột tháng là NGÀY thật (hiện mm/yyyy); Lũy kế trong kỳ = SUM các ô tháng, Còn lại = Doanh thu − LK
    trước − LK trong kỳ ghi CÔNG THỨC (kèm giá trị tính sẵn); dòng tổng cuối SUM các cột tiền. Cột phụ thuộc bị ẩn khi xuất
    "Như đang xem" → ô đó ghi số, không ghi công thức. Dải LK trước · các tháng · LK trong kỳ · Còn lại in đậm như màn hình
    (v1.10.7, Trum 29/09 — chỉ in đậm, không tô nền)."""
    from xlsxwriter.utility import xl_col_to_name as L
    pos = {k: i for i, (k, _) in enumerate(cols)}
    mk = [_month_key(m) for m in months]
    spec = {'header_dates': {pos[_month_key(m)]: datetime(m.year, m.month, 1) for m in months if _month_key(m) in pos},
            'formulas': {}, 'sum_cols': [pos[k] for k in ["INCOME_AMOUNT", "CUM_BEFORE"] + mk + ["CUM_IN", "CON_LAI"] if k in pos],
            'bold_cols': [pos[k] for k in ["CUM_BEFORE"] + mk + ["CUM_IN", "CON_LAI"] if k in pos]}
    if "CUM_IN" in pos and mk and all(k in pos for k in mk):
        idx = [pos[k] for k in mk]
        if idx == list(range(idx[0], idx[0] + len(idx))):
            spec['formulas'][pos["CUM_IN"]] = f"=SUM({L(idx[0])}{{r}}:{L(idx[-1])}{{r}})"
        else:
            spec['formulas'][pos["CUM_IN"]] = "=SUM(" + ",".join(f"{L(i)}{{r}}" for i in idx) + ")"
    if all(k in pos for k in ("CON_LAI", "INCOME_AMOUNT", "CUM_BEFORE", "CUM_IN")):
        spec['formulas'][pos["CON_LAI"]] = f"={L(pos['INCOME_AMOUNT'])}{{r}}-{L(pos['CUM_BEFORE'])}{{r}}-{L(pos['CUM_IN'])}{{r}}"
    return spec


@app.route("/api/income_alloc_month/stream_csv", methods=["POST", "GET"])
def get_income_alloc_month_stream_csv():
    """Job xuất (xlsx/csv) — cùng đường tải-rồi-ghi chịu đứt mạng như các danh sách khác (Bẫy 25)."""
    try:
        args = request.args
        total_estimate = int(args.get("total", 0) or 0)
        months, labels = _income_month_range(args)
        where_sql, w_params = _income_month_where(args, months)
        order_by_sql = _income_month_order(args, months)
        full = _income_month_export_cols(months, labels)
        raw_cols = (args.get("cols") or "").strip()
        if raw_cols:   # "MONTHS" (khối cột tháng trên màn hình) → bung ra các khoá tháng
            keys = []
            for k in raw_cols.split(","):
                keys.extend([_month_key(m) for m in months] if k.strip() == "MONTHS" else [k.strip()])
            args = {**{k: args.get(k) for k in args}, "cols": ",".join(keys)}
        cols = _pick_export_cols(args, full)
        sale_ok = _sale_link_ok()
        sql = f"""{_income_month_cte(months)}, T AS (
                SELECT {_income_month_select(months)}, ROW_NUMBER() OVER (ORDER BY {order_by_sql}) AS RowNum
                {INCOME_MONTH_FROM} WHERE {where_sql})
            SELECT T.*, {_income_month_sale_cols()} FROM T {_INCOME_MONTH_SALE_JOIN if sale_ok else ''}
            ORDER BY T.RowNum"""

        def transform(raw, sql_cols):   # ngày giữ kiểu ngày, số giữ Decimal — bộ ghi xlsx tự định dạng (Bẫy 12)
            d = dict(zip(sql_cols, raw))
            return [(d.get(key).strip() if isinstance(d.get(key), str) else d.get(key)) for key, _ in cols]

        headers = [label for _, label in cols]
        f0, f1 = months[0], months[-1]
        fname = f"DoanhThuChoPhanBoTheoThang_{f0.month:02d}{f0.year}-{f1.month:02d}{f1.year}.{args.get('format', 'csv')}"
        job_id = _start_export_job(fname, headers, sql, w_params, transform, total_estimate,
                                   xlsx_spec=_income_month_xlsx_spec(cols, months))
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
        cols = _pick_export_cols(args, VOUCHER_CSV_COLS)

        def transform(raw, sql_cols):
            d = dict(zip(sql_cols, raw))
            d['ORGANIZATION_NAME'] = org_map.get((str(d.get('ORGANIZATION_ID') or '')).strip(), '')
            d['TRAN_NAME']         = tran_map.get((str(d.get('TRAN_ID') or '')).strip(), '')
            pd = pr_map.get((str(d.get('PR_DETAIL_ID_DEBIT') or '')).strip()) or ('', '', '')
            d['PR_DETAIL_NAME_DEBIT'], d['BANK_NAME_DEBIT'], d['BANK_ACCOUNT_DEBIT'] = pd
            pc = pr_map.get((str(d.get('PR_DETAIL_ID_CREDIT') or '')).strip()) or ('', '', '')
            d['PR_DETAIL_NAME_CREDIT'], d['BANK_NAME_CREDIT'], d['BANK_ACCOUNT_CREDIT'] = pc
            return [d.get(key) for key, _ in cols]

        headers = [label for _, label in cols]
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
            # BẢNG KÊ THUẾ GTGT bán ra / mua vào (vat_kind = BR | MV) — cột y hệt bảng trên web, xuất TOÀN BỘ (không phân trang).
            # Bộ lọc phải khớp /api/vat_sales_report: đơn vị dùng _org_filter_sql (không chọn ⇒ loại đơn vị
            # ngoài cây '00'), tài khoản LIKE prefix đa chọn — nếu dùng org_where thường sẽ lệch số so màn hình.
            vat_kind = _vat_kind(request.args.get("vat_kind"))
            if not vat_kind:
                return jsonify({"status": "error", "message": "Loại bảng kê không hợp lệ (BR = bán ra, MV = mua vào)."}), 400
            tran_id, item_sql, detail_order = _VAT_KINDS[vat_kind]
            acc_ids_13 = [v.strip() for v in request.args.get("acc_ids", "").split(",") if v.strip()]
            _oc, _op = _org_filter_sql(org_ids, "ORGANIZATION_ID")
            vat_org_where = (" AND " + _oc) if _oc else ""
            vat_acc_where, vat_acc_params = "", []
            if acc_ids_13:
                vat_acc_where = " AND (" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids_13)) + ")"
                vat_acc_params = [a + "%" for a in acc_ids_13]
            buy = vat_kind == 'MV'
            headers = ["TT", "Ký hiệu hóa đơn", "Số hóa đơn", "Ngày phát hành",
                       "Tên người bán" if buy else "Tên người mua",
                       "Mã số thuế người bán" if buy else "Mã số thuế người mua", "Mặt hàng",
                       "Doanh số mua chưa có thuế" if buy else "Doanh số bán chưa có thuế",
                       "Thuế suất (%)", "Thuế GTGT", "Ghi chú"]
            if mode == "summary":
                # Gộp mỗi số hóa đơn 1 dòng — GROUP BY y hệt nhánh summary của /api/vat_sales_report
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE,
                                 ISNULL(PR_DETAIL_NAME,''), ISNULL(TAX_FILE_NUMBER,''),
                                 {item_sql}, ISNULL(SUM(AMOUNT_ITEM),0),
                                 ISNULL(MAX(VAT_TAX_RATE),0), ISNULL(SUM(AMOUNT),0), N''
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                          WHERE TRAN_ID = '{tran_id}'
                            AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{vat_org_where}{vat_acc_where}
                          GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID
                          ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO"""
            else:
                sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE,
                                 ISNULL(PR_DETAIL_NAME,''), ISNULL(TAX_FILE_NUMBER,''), ISNULL(ITEM_NAME,''),
                                 ISNULL(AMOUNT_ITEM,0), ISNULL(VAT_TAX_RATE,0), ISNULL(AMOUNT,0), ISNULL(COMMENTS,'')
                          FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                          WHERE TRAN_ID = '{tran_id}'
                            AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{vat_org_where}{vat_acc_where}
                          ORDER BY {detail_order}"""
            params = [d_from, d_to] + list(_op) + vat_acc_params
            fname = (f"BC013_Bang_Ke_Thue_GTGT_{'Mua_Vao' if buy else 'Ban_Ra'}_{'TongHop' if mode == 'summary' else 'ChiTiet'}"
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
                elif report_type == "BC013":  # BẢNG KÊ THUẾ GTGT — TT tự đánh, mã giữ dạng text, chốt Tổng cộng
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


# Bảng kê thuế GTGT (BC013): VAT_TRANSACTION_VIEW chứa cả đầu ra lẫn đầu vào, phân biệt bằng TRAN_ID (Trum 01/10/2026):
# VAT_BR = bán ra, VAT_MV = mua vào. Trước v1.11.0 lọc DEBIT_CREDIT = 'CRD' → chỉ có bán ra (DB demo: VAT_BR toàn CRD,
# VAT_MV toàn DEB). Giá trị lấy từ bảng dưới, không nhận chữ người dùng → ghi thẳng vào SQL, không thêm dấu ? (Bẫy 2).
# Dùng chung cho màn hình (/api/vat_sales_report), job xuất (_rx_plan) và CSV cũ (/api/report_export_csv) — sửa 1 chỗ.
_VAT_KINDS = {
    # loại: (TRAN_ID, chữ cột Mặt hàng ở chế độ Tổng hợp, ORDER BY chế độ Chi tiết)
    'BR': ('VAT_BR', "N'Bán hàng hóa, dịch vụ'", "VAT_TAX_RATE, VAT_TRAN_DATE, VAT_TRAN_NO"),
    'MV': ('VAT_MV', "N'Mua hàng hóa, dịch vụ'", "VAT_TRAN_DATE, VAT_TRAN_NO"),   # như báo cáo mua vào của iPOS
}


def _vat_kind(v):
    """'BR' (mặc định — app cũ không gửi) | 'MV'; giá trị lạ → None (nơi gọi báo lỗi, không tự đoán)."""
    k = str(v or 'BR').strip().upper()
    return k if k in _VAT_KINDS else None


@app.route("/api/vat_sales_report")
@with_db_lock
def get_vat_sales_report():
    """Bảng kê thuế GTGT bán ra / mua vào (vat_kind = BR | MV) — Tổng hợp & Chi tiết."""
    try:
        f_date = request.args.get("from_date")
        t_date = request.args.get("to_date")
        mode = request.args.get("mode", "detail")  # 'detail' | 'summary'
        kind = _vat_kind(request.args.get("vat_kind"))
        if not kind:
            return jsonify({"status": "error", "message": "Loại bảng kê không hợp lệ (BR = bán ra, MV = mua vào)."}), 400
        tran_id, item_sql, detail_order = _VAT_KINDS[kind]
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
            WHERE TRAN_ID = '{tran_id}'
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
                    WHERE TRAN_ID = '{tran_id}'
                      AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}
                    GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID
                ) AS Grp
            """
        else:
            count_sql = f"""
                SELECT COUNT(*)
                FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                WHERE TRAN_ID = '{tran_id}'
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
                        {item_sql} AS item,
                        ISNULL(SUM(AMOUNT_ITEM), 0) AS amount_item,
                        ISNULL(MAX(VAT_TAX_RATE), 0) AS tax_rate,
                        ISNULL(SUM(AMOUNT), 0) AS vat_amount,
                        N'' AS comments,
                        ISNULL(ACCOUNT_ID, '') AS account_id,
                        ROW_NUMBER() OVER (ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO) AS RowNum
                    FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                    WHERE TRAN_ID = '{tran_id}'
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
                        ROW_NUMBER() OVER (ORDER BY {detail_order}) AS RowNum
                    FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                    WHERE TRAN_ID = '{tran_id}'
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

        # vat_kind trả về để app ghi tiêu đề / xuất file theo loại của DỮ LIỆU ĐANG HIỆN, không theo nút vừa bấm
        return jsonify({"status": "ok", "data": rows, "totals": totals, "pagination": pagination, "vat_kind": kind})
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
    """Thư mục lưu file. Không có screen → thư mục mặc định (như cũ). Có screen → thư mục của màn đó, đã khai riêng chưa, dùng
    được không (app gọi TRƯỚC khi xuất: hỏng thì cảnh báo + bắt chọn lại). quick=1: chỉ xem còn thư mục không, không ghi thử
    (menu Xuất Excel gọi mỗi lần mở — khỏi tạo file thử trong thư mục người dùng mỗi lần)."""
    screen = request.args.get("screen", "")
    if not screen:
        return jsonify({"status": "ok", "dir": _export_dir()})
    folder, custom = _export_dir_for(screen)
    ok, reason, can_create = (_export_dir_state(folder, write_test=request.args.get("quick") != "1") if custom
                              else (True, "", False))
    return jsonify({"status": "ok", "screen": screen, "dir": folder, "default": _export_dir(), "custom": custom,
                    "ok": ok, "reason": reason, "can_create": can_create})


@app.route("/api/export/dir", methods=["POST"])
def set_export_dir():
    """Khai thư mục lưu cho 1 màn hình ({screen, dir, all, create}). all=True: mọi màn hình. dir rỗng (hoặc đúng thư mục mặc định)
    → về mặc định. create=True: tạo thư mục nếu chưa có — chỉ khi người dùng tự bấm "Tạo thư mục" / "Tạo lại thư mục".
    Thư mục phải ghi được mới lưu."""
    if not _is_local_request():
        return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
    data = request.get_json(force=True, silent=True) or {}
    screen = str(data.get("screen") or "")
    if screen not in _EXPORT_SCREENS:
        return jsonify({"status": "error", "message": "Màn hình không hợp lệ."}), 400
    raw = str(data.get("dir") or "").strip()
    folder = _clean_dir_input(raw) if raw else ""

    def bad(what, fix, can_create=False):
        return jsonify({"status": "error", "code": "bad_dir", "dir": folder or raw, "reason": what, "can_create": can_create,
                        "message": f"{what}\n{_VI_FIX} {fix}\n{_VI_DETAIL} {folder or raw}"}), 400

    if raw and not folder:
        return bad("Đường dẫn chưa đúng — cần đường dẫn đầy đủ, bắt đầu bằng ổ đĩa (D:\\...) hoặc thư mục mạng (\\\\máy chủ\\...).",
                   "Bấm \"Chọn thư mục…\", hoặc copy đường dẫn từ thanh địa chỉ của File Explorer rồi dán vào ô.")
    if folder and os.path.normcase(folder) == os.path.normcase(_export_dir()):
        folder = ""   # chọn đúng thư mục mặc định = về mặc định
    if folder:
        if len(folder) > _EXPORT_DIR_MAX:
            return bad(f"Đường dẫn quá dài ({len(folder)} ký tự) — Excel không mở được file nằm sâu như vậy.",
                       f"Chọn thư mục có đường dẫn ngắn hơn ({_EXPORT_DIR_MAX} ký tự trở xuống).")
        if data.get("create") and not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except FileNotFoundError:
                return bad("Không tạo được thư mục — ổ đĩa không còn.", "Cắm lại ổ USB / bật VPN nếu là ổ mạng, hoặc chọn thư mục khác.")
            except OSError:
                return bad("Không tạo được thư mục này.",
                           "Kiểm tra lại tên thư mục (không dùng ký tự / : * ? \" < > |) và quyền ghi trên ổ đĩa, hoặc chọn thư mục khác.")
        ok, reason, can_create = _export_dir_state(folder)
        if not ok and can_create:   # đang khai đường dẫn mới: thư mục chưa có (không phải "đã bị xoá")
            return bad("Thư mục này chưa có trên máy.", "Bấm \"Tạo thư mục này\" để tạo, hoặc kiểm tra lại đường dẫn.", True)
        if not ok:
            return bad(reason, "Chọn thư mục khác.")
    try:
        with _export_dirs_lock:
            dirs = _export_dirs_read()
            for s in (_EXPORT_SCREENS if data.get("all") else (screen,)):
                if folder:
                    dirs[s] = folder
                else:
                    dirs.pop(s, None)
            _export_dirs_write(dirs)
    except OSError as e:
        logger.exception("Khong luu duoc export_dirs.json")
        return jsonify({"status": "error", "message": (f"Không lưu được cấu hình thư mục trên máy này.\n{_VI_FIX} Thử lại. Vẫn lỗi thì "
                                                       f"chụp màn hình gửi người hỗ trợ DataStudio.\n{_VI_DETAIL} {_err_brief(e)}")}), 500
    now, custom = _export_dir_for(screen)
    return jsonify({"status": "ok", "screen": screen, "dir": now, "default": _export_dir(), "custom": custom, "ok": True,
                    "reason": "", "can_create": False})


_pick_lock = threading.Lock()


@app.route("/api/export/pick_dir", methods=["POST"])
def pick_export_dir():
    """Mở hộp chọn thư mục của Windows (nổi trên cửa sổ app) → {status: 'ok', dir} | {status: 'cancel'} | lỗi. Chờ tới khi người
    dùng đóng hộp. Mỗi lần 1 hộp (bấm 2 lần → 'busy'). Chỉ chọn — lưu cấu hình vẫn qua POST /api/export/dir."""
    if not _is_local_request():
        return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
    if platform.system() != "Windows":
        return jsonify({"status": "error", "message": "Hộp chọn thư mục chỉ có trên Windows — dán đường dẫn thư mục vào ô."}), 400
    data = request.get_json(force=True, silent=True) or {}
    start = _clean_dir_input(data.get("start")) or _export_dir()
    if not _pick_lock.acquire(blocking=False):
        return jsonify({"status": "busy"})
    try:
        folder = _pick_folder_native(start, "Chọn thư mục lưu file xuất")
    except Exception as e:
        logger.exception("Khong mo duoc hop chon thu muc")
        return jsonify({"status": "error", "message": (f"Không mở được hộp chọn thư mục của Windows.\n{_VI_FIX} Copy đường dẫn từ thanh "
                                                       f"địa chỉ của File Explorer rồi dán vào ô.\n{_VI_DETAIL} {_err_brief(e)}")}), 500
    finally:
        _pick_lock.release()
    return jsonify({"status": "ok", "dir": folder} if folder else {"status": "cancel"})


@app.route("/api/export/save_file", methods=["POST"])
def save_export_file():
    """Lưu file Excel dựng ở trình duyệt ("Tách sheet theo đơn vị") vào thư mục của màn hình (?screen=&filename=, body = nội dung
    file). Trước v1.10.9 trình duyệt tự tải về Downloads của Chrome — lệch 2 kiểu xuất kia và không có Mở file / Mở folder.
    Trùng tên tự thêm (2), (3)…; ghi ra *.part rồi mới đổi tên."""
    if not _is_local_request():
        return jsonify({"status": "error", "message": "Yêu cầu không hợp lệ."}), 403
    screen = request.args.get("screen", "")
    problem = _export_dir_problem(screen)
    if problem:
        return jsonify(problem), 409
    path = _rx_reserve_path(request.args.get("filename") or "DanhSach", "xlsx", _export_dir_for(screen)[0])
    tmp = path + ".part"
    try:
        size = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = request.stream.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
        if not size:
            raise ValueError("File rỗng — trình duyệt không gửi nội dung.")
        os.replace(tmp, path)
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        logger.exception("Loi luu file tach sheet")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        with _export_jobs_lock:
            _export_reserved.discard(path.lower())
    return jsonify({"status": "ok", "path": path, "filename": os.path.basename(path), "dir": os.path.dirname(path), "size": size})


def _rx_list(v):
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').split(',') if x.strip()]


def _rx_reserve_path(filename, ext, folder=None):
    """Tên file sạch + không đè file đã có (file cũ có thể đang mở trong Excel → ghi đè sẽ lỗi quyền).
    folder: thư mục lưu của màn hình (_export_dir_for) — không truyền = thư mục mặc định."""
    base = os.path.basename(str(filename or '')).strip()
    if base.lower().endswith('.' + ext):
        base = base[:-(len(ext) + 1)]
    base = _re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', base).strip(' ._')[:150] or 'BaoCao'
    default = _export_dir()
    folder = folder or default
    # Dọn *.part mồ côi (EXE bị tắt ngang lúc đang ghi) — chỉ file cũ hơn 6 giờ, không đụng job đang chạy. CHỈ ở thư mục mặc định:
    # thư mục người dùng chọn có thể chứa file tải dở của trình duyệt khác (Firefox cũng dùng đuôi .part).
    if os.path.normcase(folder) == os.path.normcase(default):
        try:
            now = time.time()
            for fn in os.listdir(folder):
                fp = os.path.join(folder, fn)
                if fn.endswith('.part') and now - os.path.getmtime(fp) > 6 * 3600:
                    os.remove(fp)
        except Exception:
            pass
    with _export_jobs_lock:
        _export_known_dirs.add(folder)
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


def _rx_ledger_days(db, where, params):
    """COUNT + SUM Nợ/Có của LEDGER_VIEW theo TỪNG NGÀY (1 lượt quét, cùng WHERE với câu tải) → (số dòng, Nợ, Có,
    [(ngày, số dòng)]). Cộng các ngày lại = đúng câu đếm + tổng của màn hình (/api/journal, /api/account_details)."""
    rows = db.all(f"""SELECT CONVERT(VARCHAR(8), TRAN_DATE, 112), COUNT(*),
                             SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                             SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                      FROM dbo.LEDGER_VIEW WITH (NOLOCK) WHERE {where}
                      GROUP BY CONVERT(VARCHAR(8), TRAN_DATE, 112)""", params, "dem dong + tong theo ngay")
    return (sum(int(r[1] or 0) for r in rows), sum((_rx_dec(r[2]) for r in rows), Decimal(0)),
            sum((_rx_dec(r[3]) for r in rows), Decimal(0)), [(r[0], r[1]) for r in rows])


def _rx_plan(rpt, variant, info, p, payload):
    """Kế hoạch xuất 1 báo cáo. GỌI TRONG REQUEST (cần session cho bộ lọc đơn vị / cache sổ quỹ).
    Trả dict {layout, total, rows(src, ctx), prepare(db, ctx)?, after(ctx)?, needs_db} hoặc chuỗi lỗi.
    prepare chạy ở job nền với db = _ExportDb (tự nối lại khi đứt mạng), trả tổng số dòng dự kiến và đặt
    ctx['fetch'] = [(sql, params), …] = các khúc cần tải; job tải hết vào file tạm rồi gọi rows(src, ctx) với src = các
    dòng đã tải theo đúng thứ tự (None nếu báo cáo không tải gì)."""
    payload = payload if isinstance(payload, dict) else {}

    # ---- Báo cáo gộp: dữ liệu = đúng các dòng app đang hiển thị ----
    if rpt == 'BC005':
        n = len(payload.get('rows') or [])
        return dict(layout=XR.layout_bc005(info), total=n, rows=lambda src, ctx: XR.rows_bc005(payload))
    if rpt in ('BC006', 'BC011'):
        is11 = rpt == 'BC011'
        n = len(payload.get('rows') or []) + (1 if payload.get('total') else 0)
        return dict(layout=XR.layout_bc006(info, is11), total=n, rows=lambda src, ctx: XR.rows_bc006(payload, is11))
    if rpt in ('BC009', 'BC010'):
        n = len(payload.get('rows') or [])
        return dict(layout=XR.layout_cash_flow(info, rpt == 'BC009'), total=n,
                    rows=lambda src, ctx: XR.rows_cash_flow(payload))

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

    if rpt == 'BC007' and variant == 'full':
        # "Nhật ký chung đầy đủ cột" — mẫu SQL người dùng đưa (trước đây chỉ có ở CSV mode=detail)
        _lvc, _lvp = _org_filter_sql(org_ids, "LV.ORGANIZATION_ID")
        org_where_lv = (" AND " + _lvc) if _lvc else ""
        sql = f"""SELECT LV.ORGANIZATION_ID, O.ORGANIZATION_NAME, LV.JOB_NAME, LV.TRAN_ID, LV.TRAN_DATE, LV.TRAN_NO,
                         LV.DESCRIPTION, LV.ACCOUNT_ID, LV.ACCOUNT_ID_CONTRA, LV.PR_DETAIL_ID, LV.PR_DETAIL_NAME,
                         LV.DEBIT_CREDIT, LV.AMOUNT, LV.COMMENTS
                  FROM dbo.LEDGER_VIEW LV WITH (NOLOCK)
                  LEFT JOIN dbo.DM_ORGANIZATION O WITH (NOLOCK) ON LV.ORGANIZATION_ID = O.ORGANIZATION_ID
                  WHERE LV.TRAN_DATE >= ? AND LV.TRAN_DATE <= ? {org_where_lv}{_CHUNK_MARK}
                  ORDER BY LV.TRAN_DATE, LV.TRAN_NO"""

        def prepare(db, ctx):
            n, ctx['deb'], ctx['crd'], days = _rx_ledger_days(
                db, f"TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}", [d_from, d_to] + list(org_params))
            ctx['fetch'] = _day_chunks(sql, [d_from, d_to] + list(_lvp), days, "LV.TRAN_DATE")
            return n + 1

        def rows(src, ctx):
            for r in src:
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
        sql = f"""SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT,
                         ORGANIZATION_ID, TRAN_ID
                  FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                  WHERE TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}{_CHUNK_MARK}
                  ORDER BY TRAN_DATE, TRAN_NO"""

        def prepare(db, ctx):
            # đúng câu đếm + tổng của /api/journal (thêm GROUP BY ngày để chia khúc) → dòng "Cộng lũy kế" khớp màn hình
            n, ctx['deb'], ctx['crd'], days = _rx_ledger_days(
                db, f"TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}", [d_from, d_to] + list(org_params))
            ctx['org_map'] = {}
            if view_mode == 'detail':
                try:
                    ctx['org_map'] = {(x[0] or '').strip(): (x[1] or '').strip() for x in db.all(
                        "SELECT CAST(ORGANIZATION_ID AS NVARCHAR(100)), ORGANIZATION_NAME FROM dbo.DM_ORGANIZATION WITH (NOLOCK)",
                        what="danh muc don vi")}
                except (XR.ExportCancelled, _ExportNetError):
                    raise
                except Exception:
                    pass
            ctx['fetch'] = _day_chunks(sql, [d_from, d_to] + list(org_params), days, "TRAN_DATE")
            return n + 1

        def rows(src, ctx):
            org_map = ctx['org_map']
            for r in src:
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
        sql = f"""SELECT TRAN_DATE, TRAN_NO, DESCRIPTION, ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT
                  FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                  WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}{_CHUNK_MARK}
                  ORDER BY TRAN_DATE, TRAN_NO"""
        sql_params = acc_params + [d_from, d_to] + list(org_params)

        def prepare(db, ctx):
            # y hệt get_account_details: dư đầu = BALANCE_VIEW đầu năm + LEDGER_VIEW từ đầu năm tới trước kỳ
            r = db.one(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                  SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                           FROM dbo.BALANCE_VIEW WITH (NOLOCK) WHERE {acc_clause} AND TRAN_DATE = ? {org_where}""",
                       acc_params + [first_day] + list(org_params), "so du dau nam")
            odeb, ocrd = _rx_dec(r[0] if r else 0), _rx_dec(r[1] if r else 0)
            if from_dt > date(from_dt.year, 1, 1):
                r = db.one(f"""SELECT SUM(CASE WHEN DEBIT_CREDIT='DEB' THEN AMOUNT ELSE 0 END),
                                      SUM(CASE WHEN DEBIT_CREDIT='CRD' THEN AMOUNT ELSE 0 END)
                               FROM dbo.LEDGER_VIEW WITH (NOLOCK)
                               WHERE {acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE < ? {org_where}""",
                           acc_params + [first_day, d_from] + list(org_params), "phat sinh truoc ky")
                if r:
                    odeb += _rx_dec(r[0])
                    ocrd += _rx_dec(r[1])
            n, deb, crd, days = _rx_ledger_days(
                db, f"{acc_clause} AND TRAN_DATE >= ? AND TRAN_DATE <= ? {org_where}", sql_params)
            ctx.update(odeb=odeb, ocrd=ocrd, deb=deb, crd=crd)
            ctx['fetch'] = _day_chunks(sql, sql_params, days, "TRAN_DATE")
            return n + 3

        def rows(src, ctx):
            open_net = ctx['odeb'] - ctx['ocrd']
            yield [XR.Span('SỐ DƯ ĐẦU KỲ', 5, 'right'), open_net if open_net > 0 else None,
                   -open_net if open_net < 0 else None], 'opening'
            for r in src:
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

        def prepare(db, ctx):
            # sổ quỹ dựng trong RAM (số dư luỹ kế) — đứt mạng giữa chừng thì nối lại và dựng lại từ đầu
            ctx['flat'] = cached if cached is not None else db.run(lambda cur: _build_cashbook_flat(
                from_dt, to_dt, acc_ids, contra_ids, tran_no, org_ids, cur=cur, org_filter=org_filter), "dung so quy")
            return len(ctx['flat'])
        return dict(layout=XR.layout_bc012(info), total=len(cached) if cached is not None else 0,
                    prepare=prepare, rows=lambda src, ctx: XR.rows_bc012(ctx['flat']), needs_db=cached is None)

    if rpt == 'BC013':
        mode = 'summary' if variant == 'summary' else 'detail'
        kind = _vat_kind(p.get('vat_kind'))   # app gửi loại của dữ liệu ĐANG HIỆN (bán ra / mua vào)
        if not kind:
            return "Loại bảng kê không hợp lệ (BR = bán ra, MV = mua vào)."
        tran_id, item_sql, detail_order = _VAT_KINDS[kind]
        acc_ids = _rx_list(p.get('acc_ids'))
        acc_where, acc_params = "", []
        if acc_ids:
            acc_where = " AND (" + " OR ".join(["ACCOUNT_ID LIKE ?"] * len(acc_ids)) + ")"
            acc_params = [a + "%" for a in acc_ids]
        params = [d_from, d_to] + list(org_params) + acc_params
        base_where = f"TRAN_ID = '{tran_id}' AND VAT_TRAN_DATE >= ? AND VAT_TRAN_DATE <= ?{org_where}{acc_where}"
        group_by = "GROUP BY VAT_TRAN_SERIE, VAT_TRAN_NO, VAT_TRAN_DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID"

        if mode == 'summary':
            sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE, ISNULL(PR_DETAIL_NAME,''),
                             ISNULL(TAX_FILE_NUMBER,''), {item_sql}, ISNULL(SUM(AMOUNT_ITEM),0),
                             ISNULL(MAX(VAT_TAX_RATE),0), ISNULL(SUM(AMOUNT),0), N''
                      FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where} {group_by}
                      ORDER BY VAT_TRAN_DATE, VAT_TRAN_NO"""
        else:
            sql = f"""SELECT ISNULL(VAT_TRAN_SERIE,''), ISNULL(VAT_TRAN_NO,''), VAT_TRAN_DATE, ISNULL(PR_DETAIL_NAME,''),
                             ISNULL(TAX_FILE_NUMBER,''), ISNULL(ITEM_NAME,''), ISNULL(AMOUNT_ITEM,0),
                             ISNULL(VAT_TAX_RATE,0), ISNULL(AMOUNT,0), ISNULL(COMMENTS,'')
                      FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}
                      ORDER BY {detail_order}"""

        def prepare(db, ctx):
            # đúng 2 câu của /api/vat_sales_report: 3 số tổng dưới bảng + số dòng theo chế độ
            t = db.one(f"""SELECT ISNULL(SUM(AMOUNT_ITEM), 0),
                                  ISNULL(SUM(CASE WHEN VAT_TAX_RATE > 0 THEN AMOUNT_ITEM ELSE 0 END), 0),
                                  ISNULL(SUM(AMOUNT), 0)
                           FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}""", params, "tong bang ke")
            ctx['totals'] = {'total_amount_item': t[0], 'taxable_amount_item': t[1], 'total_vat_amount': t[2]}
            if mode == 'summary':
                c = db.one(f"""SELECT COUNT(*) FROM (SELECT VAT_TRAN_SERIE FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK)
                               WHERE {base_where} {group_by}) AS Grp""", params, "dem dong")
            else:
                c = db.one(f"SELECT COUNT(*) FROM dbo.VAT_TRANSACTION_VIEW WITH (NOLOCK) WHERE {base_where}", params, "dem dong")
            # 1 khúc: bán ra sắp theo thuế suất trước rồi mới tới ngày → không chia theo ngày được (mua vào sắp theo ngày
            # nhưng cũng để 1 khúc cho gọn). Vẫn tải vào file tạm trước khi ghi (kết nối không phải sống suốt lúc ghi file),
            # đứt mạng thì tải lại cả truy vấn.
            ctx['fetch'] = [(sql, params)]
            return (c[0] or 0) + 1

        def rows(src, ctx):
            stt, s_amt, s_vat = 0, Decimal(0), Decimal(0)
            for r in src:
                stt += 1
                amt, vat = _rx_dec(r[6]), _rx_dec(r[8])
                s_amt += amt
                s_vat += vat
                yield [stt, (r[0] or '').strip(), (r[1] or '').strip(), r[2], (r[3] or '').strip(),
                       (r[4] or '').strip(), (r[5] or '').strip(), amt, float(r[7] or 0), vat,
                       (r[9] or '').strip()], 'data'
            yield [XR.Span('Tổng cộng', 7, 'center'), s_amt, None, s_vat, None], 'total'
        return dict(layout=XR.layout_bc013(info, kind), total=0, prepare=prepare, rows=rows,
                    after=lambda ctx: XR.bc013_summary_rows(ctx['totals'], kind), needs_db=True)

    return "Báo cáo chưa hỗ trợ xuất."


def _rx_error_text(e):
    # v1.10.6: dùng bộ dịch chung (_vi_error_text). Trước đây chỉ nhận 08S01 / "communication link" → lỗi mạng của
    # driver cũ "SQL Server" ("[DBNETLIB]ConnectionWrite (10054) … General network error") hiện nguyên tiếng Anh (Trum 29/09).
    return _vi_error_text(e)


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
            'report_type': report_type, 'format': fmt, 'retries': 0, 'retry': None, 'timing': {},
        }
    ctl = _ExportCtl(job_id, started, f"{report_type} {fmt}")
    upd, cancelled = ctl.upd, ctl.cancelled

    def runner():
        db, writer, spool = None, None, None
        tmp = path + '.part'   # ghi ra tên tạm, xong mới đổi tên → không bao giờ lộ file dở dang mang tên thật
        timing = {}
        try:
            ctl.log("bat dau: CSDL %s, %s", (db_cfg or {}).get('database'), os.path.basename(path))
            ctx = {}
            total = plan.get('total') or 0
            t = time.time()
            if plan.get('needs_db'):
                upd(phase='query')
                db = _ExportDb(db_cfg, ctl)
            if plan.get('prepare'):
                total = plan['prepare'](db, ctx)
                upd(total=total)
            timing['query'] = round(time.time() - t, 1)
            if cancelled():
                raise XR.ExportCancelled()
            if ctx.get('fetch'):
                # Giai đoạn TẢI: từng khúc vào file tạm, đứt mạng tự nối lại (xem khối "XUẤT FILE LỚN CHỊU ĐƯỢC MẠNG…")
                ctl.log("dem: %d dong -> %d khuc, %.1fs", total, len(ctx['fetch']), timing['query'])
                t = time.time()
                upd(phase='fetch', current=0, chunk=0, chunks=len(ctx['fetch']))
                spool = _ExportSpool()
                db.fetch(ctx['fetch'], spool)
                timing['fetch'] = round(time.time() - t, 1)
                ctl.log("tai xong: %d dong, %.1fs, file tam %.1f MB, noi lai %d lan", spool.count, timing['fetch'],
                        spool.size() / 1048576, db.reconnects)
            if db is not None:
                db.close()   # nhả kết nối TRƯỚC khi ghi file — khâu ghi dài nhất không còn phụ thuộc mạng
            if cancelled():
                raise XR.ExportCancelled()
            t = time.time()
            upd(phase='write', current=0, timing=dict(timing))
            W = XR.CsvReportWriter if fmt == 'csv' else XR.XlsxReportWriter
            writer = W(tmp, plan['layout'], total_rows=total, is_cancelled=cancelled,
                       progress=lambda n, s, ss: upd(current=n, sheet=s, sheets=ss))
            for item in plan['rows'](spool.iter_rows() if spool is not None else None, ctx):
                writer.add_row(*item)
            timing['write'] = round(time.time() - t, 1)
            t = time.time()
            upd(phase='finalize', current=writer.rows_written, timing=dict(timing))
            writer.close(after_rows=plan['after'](ctx) if plan.get('after') else None)
            rows_written, sheets = writer.rows_written, writer.sheet_count
            writer = None
            os.replace(tmp, path)
            timing['finalize'] = round(time.time() - t, 1)
            size = os.path.getsize(path)
            upd(status='done', phase='done', file_path=path, size=size, timing=dict(timing),
                current=rows_written, total=max(total, rows_written), rows=rows_written, sheet=sheets, sheets=sheets)
            ctl.log("xong: %d dong, %d sheet, %.1f MB, tong %.1fs %s", rows_written, sheets, size / 1048576,
                    time.time() - started, timing)
        except XR.ExportCancelled:
            _rx_cleanup(writer, tmp)
            upd(status='cancelled', phase='cancelled')
            ctl.log("nguoi dung huy")
        except Exception as e:
            ctl.log("loi: %s", _err_brief(e), level=logging.ERROR)
            logger.exception(f"Loi xuat bao cao {report_type}")
            _rx_cleanup(writer, tmp)
            upd(status='error', phase='error', error=_rx_error_text(e))
        finally:
            if db is not None:
                db.close()
            if spool is not None:
                spool.close()
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
        problem = _export_dir_problem(rpt)   # thư mục đã khai cho báo cáo này hỏng → app cảnh báo + bắt chọn lại (kiểm trước khi dựng plan)
        if problem:
            return jsonify(problem), 409
        info = _rx_header(data.get('header'))
        params = data.get('params') if isinstance(data.get('params'), dict) else {}
        # Bộ lọc đơn vị (_org_filter_sql) và khoá cache sổ quỹ cần session + pool → tính ở đây, dưới khoá DB
        # chung giống mọi endpoint báo cáo; thread nền chỉ nhận kết quả đã tính sẵn.
        with global_db_lock:
            plan = _rx_plan(rpt, str(data.get('variant') or ''), info, params, data.get('payload'))
        if isinstance(plan, str):
            return jsonify({"status": "error", "message": plan}), 400
        path = _rx_reserve_path(data.get('filename') or rpt, fmt, _export_dir_for(rpt)[0])
        job_id = _rx_start_job(path, fmt, plan, db_cfg, rpt)
        return jsonify({"status": "ok", "job_id": job_id, "filename": os.path.basename(path),
                        "dir": os.path.dirname(path)})
    except Exception as e:
        logger.exception("Loi khoi tao xuat bao cao")
        return jsonify({"status": "error", "message": str(e)}), 500


# ==============================================================================
# TỰ CẬP NHẬT QUA GITHUB RELEASES (port từ LedgerReport 17/09/2026)
# App mở → /api/check_update so tag release mới nhất với APP_VERSION → banner "Cập nhật ngay"
# → /api/apply_update tải EXE vào <exe>.new (kiểm dung lượng + SHA-256) → đổi tên exe đang chạy thành
# <exe>.old → đặt bản mới vào đúng tên cũ → đóng cửa sổ app → chạy bản mới → thoát.
# Bản mới khởi động thì dọn <exe>.old (xem __main__).
# ⚠️ Repo PHẢI để Public: EXE gọi API không đăng nhập, repo Private trả 404 → không máy nào thấy bản mới.
# ⚠️ Asset phải tên đúng UPDATE_ASSET_NAME — updater không lấy "file .exe đầu tiên" để khỏi thay nhầm file khác.
# ==============================================================================
import urllib.request
import json
import re

UPDATE_API_URL = "https://api.github.com/repos/trungkhanhduong93/ledgerstudio/releases/latest"
UPDATE_ASSET_NAME = "iPOS_Ledger_Studio.exe"
_UPDATE_UA = f"iPOS-Ledger-Studio/{APP_VERSION}"

_update_lock = threading.Lock()
_update_state = {
    "status": "idle",       # idle | downloading | applying | ready | error
    "progress": 0,          # 0 - 100
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "error_message": "",
    "target_version": ""
}
# Handle Chrome --app do launch_app_window mở — updater phải đóng cửa sổ này trước khi chạy bản mới.
_app_window_proc = None
# Bật trong lúc thay EXE: launch_app_window thấy cửa sổ bị đóng sẽ KHÔNG tự tắt server.
_update_in_progress = False


def _set_update_state(**kw):
    with _update_lock:
        _update_state.update(kw)


def _update_paths():
    exe_path = os.path.abspath(sys.executable)
    return exe_path, exe_path + ".new", exe_path + ".old"


def _cleanup_old_executables(retry_seconds=0):
    """Dọn <exe>.old / <exe>.new do lần cập nhật trước để lại.

    CHỈ đụng đúng 2 file mang tên EXE đang chạy. Bản LedgerReport xoá MỌI *.old / *.new / *.tmp_dl
    trong thư mục chứa EXE — người dùng để EXE ở Downloads/Desktop là mất luôn file .old/.new của họ.
    Bản vừa cập nhật phải gọi với retry_seconds > 0: <exe>.old là image của tiến trình cũ vừa khởi chạy
    mình, Windows còn khoá nó tới khi tiến trình đó thoát hẳn — xoá một lần là thất bại im lặng."""
    if not getattr(sys, 'frozen', False):
        return
    exe_path, new_path, old_path = _update_paths()
    deadline = time.time() + max(0, retry_seconds)
    while True:
        targets = [old_path]
        # Đang tải thì <exe>.new là file đang ghi dở — xoá là giết luôn bản đang tải
        if _update_state.get("status") not in ("downloading", "applying"):
            targets.append(new_path)
        con_lai = False
        for p in targets:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    con_lai = True
        if not con_lai or time.time() >= deadline:
            return
        time.sleep(1.0)


def _child_env_without_pyi():
    """Env sạch để spawn EXE mới — PHẢI gỡ các biến bootloader PyInstaller onefile.

    ⚠️ BẪY ĐÃ LÀM CHẾT TỰ CẬP NHẬT BÊN LEDGERREPORT (28/08/2026): Popen([exe]) kế thừa env có
    `_PYI_APPLICATION_HOME_DIR` / `_PYI_ARCHIVE_FILE` / `_PYI_PARENT_PROCESS_LEVEL` (PyInstaller <=5: `_MEIPASS2`).
    Bootloader của EXE mới tưởng mình là tiến trình con giai đoạn 2, so executable với cha (`...exe.old`) → khác
    → hộp thoại "Security validation failure: parent process has different executable!", Python chưa chạy dòng nào.
    Triệu chứng: tải xong chỉ thấy EXE cũ thành .old, bản mới không lên (tasklist còn ~10 MB, không LISTEN 5050)."""
    env = os.environ.copy()
    for k in ("_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL",
              "_PYI_SPLASH_IPC", "_MEIPASS2"):
        env.pop(k, None)
    return env


def _parse_semver(v_str):
    """'v1.8.3' -> (1, 8, 3). Chuỗi không có số ('dev' khi chạy từ source) -> (0, 0, 0)."""
    nums = re.findall(r'\d+', str(v_str or ''))
    return tuple(int(n) for n in nums[:3]) if nums else (0, 0, 0)


def _fetch_latest_release(timeout):
    req = urllib.request.Request(UPDATE_API_URL, headers={
        "User-Agent": _UPDATE_UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _pick_exe_asset(release):
    for a in release.get('assets') or []:
        if (a.get('name') or '').lower() == UPDATE_ASSET_NAME.lower():
            return a
    return None


# ---- Tóm tắt thay đổi cho hộp "Cập nhật ngay" (v1.10.5, Trum yêu cầu 28/09) ----
# Máy đang ở bản X thấy bản mới Y → hộp cập nhật liệt kê từng bản X < v ≤ Y kèm gạch đầu dòng rút từ ghi chú release.
# Ghi chú release có 3 kiểu viết: "## DataStudio vX — tóm tắt" + mục **Mới** / **Sửa lỗi**…; gạch đầu dòng trơn (Gemini);
# "### Mới" (v1.8.x). Mục "Cập nhật" là hướng dẫn cài → bỏ. Viết ghi chú release mới thì giữ kiểu thứ nhất.
UPDATE_LIST_URL = "https://api.github.com/repos/trungkhanhduong93/ledgerstudio/releases?per_page=30"
_CHANGES_MAX_VERSIONS = 12   # tụt quá nhiều bản thì chỉ liệt kê 12 bản mới nhất (+ changes_more)
_CHANGES_MAX_ITEMS = 6       # mỗi bản tối đa 6 gạch đầu dòng (+ more)
_CHANGE_ITEM_LEN = 170       # gạch đầu dòng dài hơn → lấy câu đầu / cắt ở ranh giới từ


def _fetch_release_list(timeout):
    req = urllib.request.Request(UPDATE_LIST_URL, headers={
        "User-Agent": _UPDATE_UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _md_plain(s):
    """Bỏ định dạng markdown đơn giản: [chữ](link) → chữ, **đậm**, `mã`, *nghiêng*. Không đụng dấu _ (tên cột DM_PR_DETAIL)."""
    s = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', s or '')
    s = s.replace('**', '').replace('`', '')
    s = re.sub(r'(?<![\w*])\*([^*\n]+)\*(?![\w*])', r'\1', s)
    return re.sub(r'\s+', ' ', s).strip()


def _short_item(text):
    if len(text) <= 120:
        return text
    first = re.split(r'(?<=[.!?])\s+(?=[A-ZĐÀ-Ỹ"“(])', text, maxsplit=1)[0]
    if len(first) >= 30:
        text = first
    if len(text) > _CHANGE_ITEM_LEN:
        text = text[:_CHANGE_ITEM_LEN].rsplit(' ', 1)[0].rstrip(',;:—-') + '…'
    return text


_GENERIC_SECTIONS = ('mới', 'có gì mới', 'sửa lỗi', 'sửa nhỏ', 'thay đổi', 'vá bảo mật', 'datastudio', 'ipos ledger studio', 'v1', 'phiên bản')


def _release_summary(body, name=''):
    """Ghi chú release (markdown) → (tóm tắt 1 dòng, [gạch đầu dòng]). Bỏ mục "Cập nhật" (hướng dẫn cài).
    Gạch đầu dòng cha kết thúc bằng ":" thì nối các gạch con vào ("Tải lại danh mục: A; B; C")."""
    title, items, section, label, cur, first_para = '', [], '', '', None, ''
    for raw in (body or '').splitlines():
        if not raw.strip():
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', raw.strip())
        if m:                                           # "## DataStudio v1.10.4 — tóm tắt" / "### Mới"
            h = _md_plain(m.group(2))
            if len(m.group(1)) <= 2 and not title and ' — ' in h:
                title = h.split(' — ', 1)[1]
            section, label, cur = h.lower(), h, None
            continue
        m = re.match(r'^\*\*([^*]+)\*\*\s*(\([^)]*\))?\s*$', raw.strip())
        if m:                                           # "**Mới**", "**Đổi tên cột** (…)" đứng riêng 1 dòng
            label = _md_plain(m.group(1))
            section, cur = label.lower(), None
            continue
        install = section.startswith(('cập nhật', 'cài đặt'))
        m = re.match(r'^[-*]\s+(.*)$', raw)             # gạch đầu dòng cấp 1 (không thụt đầu dòng)
        if m:
            cur = None
            if not install:
                # mục đặc thù ("Đổi tên cột") → ghi tên mục phía trước cho khỏi cụt nghĩa; mục chung (Mới, Sửa lỗi…) thì thôi
                pre = '' if (not section or section.startswith(_GENERIC_SECTIONS)) else label + ': '
                cur = [pre + _md_plain(m.group(1))]
                items.append(cur)
            continue
        m = re.match(r'^\s+[-*]\s+(.*)$', raw)          # gạch con
        if m:
            if cur is not None and cur[0].endswith(':'):
                cur.append(_md_plain(m.group(1)))
            continue
        if install or raw.lstrip().startswith('>'):
            continue
        para = _md_plain(raw)
        if para.lower().startswith('lưu ý'):            # "**Lưu ý:** …" → cũng là 1 thay đổi người dùng thấy
            items.append([para])
        elif not first_para:
            first_para = re.sub(r'^Phiên bản\s+v?[\d.]+\s*:\s*', '', para, flags=re.I)
    out = []
    for it in items:
        text = it[0] if len(it) == 1 else it[0] + ' ' + '; '.join(x.rstrip('.') for x in it[1:]) + '.'
        if text.strip(':').strip():
            out.append(_short_item(text))
    if not out and first_para:                          # ghi chú chỉ có 1 câu (v1.9.9)
        out = [_short_item(first_para)]
    if not title and ' — ' in (name or ''):
        title = _md_plain(name.split(' — ', 1)[1])
    return title, out


def _changes_between(releases, current, latest):
    """Các bản current < v ≤ latest (bỏ nháp / thử nghiệm), mới nhất trước."""
    cur_v, lat_v = _parse_semver(current), _parse_semver(latest)
    picked = []
    for r in releases or []:
        if r.get('draft') or r.get('prerelease'):
            continue
        v = _parse_semver(r.get('tag_name'))
        if cur_v < v <= lat_v:
            picked.append((v, r))
    picked.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, r in picked[:_CHANGES_MAX_VERSIONS]:
        title, items = _release_summary(r.get('body'), r.get('name'))
        out.append({"version": r.get('tag_name', ''), "published_at": r.get('published_at', ''), "title": title,
                    "items": items[:_CHANGES_MAX_ITEMS], "more": max(0, len(items) - _CHANGES_MAX_ITEMS)})
    return out, max(0, len(picked) - _CHANGES_MAX_VERSIONS)


@app.route('/api/check_update', methods=['GET'])
def check_update_api():
    """Public — so release mới nhất trên GitHub với APP_VERSION. Lỗi mạng / chưa có release → has_update=False."""
    frozen = getattr(sys, 'frozen', False)
    try:
        rel = _fetch_latest_release(timeout=3.0)
        asset = _pick_exe_asset(rel) or {}
        tag = rel.get('tag_name', '')
        digest = asset.get('digest') or ''
        has_update = bool(asset) and _parse_semver(tag) > _parse_semver(APP_VERSION)
        # Chỉ khi có bản mới mới gọi thêm danh sách release (API GitHub không đăng nhập: 60 lượt/giờ/IP).
        # Lỗi → hộp cập nhật hiện như cũ (không có danh sách thay đổi), KHÔNG làm hỏng việc báo bản mới.
        changes, changes_more = [], 0
        if has_update:
            try:
                changes, changes_more = _changes_between(_fetch_release_list(timeout=3.0), APP_VERSION, tag)
            except Exception:
                pass
        return jsonify({
            "status": "ok",
            "has_update": has_update,
            "changes": changes,
            "changes_more": changes_more,
            "current_version": APP_VERSION,
            "latest_version": tag,
            "release_name": rel.get('name', ''),
            "release_notes": rel.get('body', ''),
            "published_at": rel.get('published_at', ''),
            "file_size": asset.get('size', 0),
            "sha256": digest[7:] if digest.startswith('sha256:') else '',
            "is_frozen": frozen,
        })
    except Exception as e:
        return jsonify({"status": "error", "has_update": False, "message": str(e),
                        "current_version": APP_VERSION, "is_frozen": frozen})


@app.route('/api/update_progress', methods=['GET'])
def update_progress_api():
    with _update_lock:
        return jsonify(dict(_update_state))


@app.route('/api/apply_update', methods=['POST'])
def apply_update_api():
    """Tải bản mới trong nền rồi thay EXE tại chỗ; app poll /api/update_progress."""
    if not _is_local_request():
        return jsonify({"status": "error", "message": "Chỉ thao tác từ chính ứng dụng."}), 403
    if not getattr(sys, 'frozen', False):
        return jsonify({"status": "error", "message": "Tự cập nhật chỉ chạy khi mở app từ file EXE."}), 400
    with _update_lock:
        if _update_state["status"] in ("downloading", "applying", "ready"):
            return jsonify({"status": "busy", "message": "Đang có tiến trình cập nhật chạy."})
        _update_state.update(status="downloading", progress=0, downloaded_bytes=0, total_bytes=0,
                             error_message="", target_version="")
    threading.Thread(target=_download_and_swap, daemon=True).start()
    return jsonify({"status": "ok", "message": "Đang tải bản cập nhật trong nền."})


def _download_and_swap():
    global _update_in_progress
    exe_path, new_path, old_path = _update_paths()
    exe_dir = os.path.dirname(exe_path)
    renamed = False
    try:
        rel = _fetch_latest_release(timeout=5.0)
        tag = rel.get('tag_name', '')
        asset = _pick_exe_asset(rel)
        if not asset or not asset.get('browser_download_url'):
            raise ValueError(f"Bản phát hành {tag or 'mới nhất'} trên GitHub không có file {UPDATE_ASSET_NAME}.")
        if _parse_semver(tag) <= _parse_semver(APP_VERSION):
            raise ValueError(f"Máy đang chạy v{APP_VERSION}, không cũ hơn bản trên GitHub ({tag}).")
        expected_size = int(asset.get('size') or 0)
        digest = asset.get('digest') or ''
        expected_sha = digest[7:].lower() if digest.startswith('sha256:') else ''
        _set_update_state(target_version=tag, total_bytes=expected_size)

        # 1. Tải vào <exe>.new, băm SHA-256 ngay trong lúc tải
        sha = hashlib.sha256()
        downloaded = 0
        req = urllib.request.Request(asset['browser_download_url'], headers={"User-Agent": _UPDATE_UA})
        with urllib.request.urlopen(req, timeout=30.0) as resp, open(new_path, 'wb') as out:
            total = int(resp.headers.get('Content-Length') or 0) or expected_size
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                downloaded += len(chunk)
                _set_update_state(downloaded_bytes=downloaded, total_bytes=total,
                                  progress=min(100, int(downloaded * 100 / total)) if total else 50)

        # 2. Kiểm toàn vẹn TRƯỚC khi đụng vào exe đang chạy — thay bằng file hỏng là máy đó không mở được app nữa
        if expected_size and downloaded != expected_size:
            raise ValueError(f"Tải thiếu: {downloaded:,} / {expected_size:,} byte.")
        if downloaded < 5 * 1024 * 1024:
            raise ValueError(f"File tải về chỉ {downloaded:,} byte — không phải EXE hợp lệ.")
        if expected_sha and sha.hexdigest() != expected_sha:
            raise ValueError("Mã SHA-256 không khớp bản trên GitHub — file tải về bị hỏng.")
        _set_update_state(status="applying", progress=100)

        # 3. Windows cho ĐỔI TÊN exe đang chạy nhưng không cho ghi đè → đổi tên rồi đặt bản mới vào tên cũ
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        os.rename(exe_path, old_path)
        renamed = True
        os.rename(new_path, exe_path)
        _set_update_state(status="ready")

        # 4. Đóng cửa sổ app cũ trước khi chạy bản mới. Chrome dùng chung --user-data-dir: instance cũ còn
        #    sống thì cửa sổ của bản mới bị "bàn giao" rồi tự thoát → bản mới chạy ngầm, không có cửa sổ.
        #    Bật cờ TRƯỚC để launch_app_window không tưởng user đóng cửa sổ rồi tự tắt server giữa chừng.
        _update_in_progress = True
        proc = _app_window_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass

        # 5. Chạy bản mới tách khỏi process tree (env sạch biến bootloader), đóng pool SQL rồi thoát
        time.sleep(0.8)
        flags = (0x00000008 | 0x00000200) if platform.system() == "Windows" else 0   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe_path], creationflags=flags, close_fds=True, cwd=exe_dir,
                         env=_child_env_without_pyi())
        with _pool_lock:
            for c in list(_conn_pool.values()):
                try:
                    c.close()
                except Exception:
                    pass
            _conn_pool.clear()
        time.sleep(0.5)
        os._exit(0)
    except Exception as err:
        logger.exception("Tu cap nhat that bai")
        _update_in_progress = False
        # Đã đổi tên exe cũ mà chưa đặt được bản mới vào → trả tên cũ lại, không để máy mất file app
        if renamed and not os.path.exists(exe_path) and os.path.exists(old_path):
            try:
                os.rename(old_path, exe_path)
            except OSError:
                pass
        if os.path.exists(new_path):
            try:
                os.remove(new_path)
            except OSError:
                pass
        _set_update_state(status="error", error_message=_vi_error_text(err, 'update'))


# ===== CỬA SỔ APP CÒN MỞ KHÔNG (v1.10.8, Trum 30/09: "tắt app thì tự kill hết các tác vụ chạy ngầm") =====
# launch_app_window chờ chính tiến trình Chrome --app nó mở: đóng cửa sổ → tắt server. Nhưng có đường KHÔNG theo dõi được: Chrome
# "bàn giao" cửa sổ cho instance cũ đang sống (thoát < 5 s), máy không có Chrome/Edge (mở trình duyệt mặc định) — trước đây server
# chạy ngầm mãi. Nay mỗi trang app giữ 1 kết nối /api/presence (EventSource); ở các đường đó _watch_presence tắt server khi không
# còn trang nào giữ kết nối. Dùng kết nối giữ mở thay vì ping định kỳ: Chrome hãm hẹn giờ của cửa sổ thu nhỏ (ẩn > 5 phút còn
# 1 lần/phút) → ping trễ là tắt nhầm lúc người dùng chỉ thu nhỏ app.
_presence = {"n": 0, "since": time.time(), "seen": False}
_presence_lock = threading.Lock()
_PRESENCE_BEAT = 5   # giây — ghi 1 dòng giữ kết nối; trang đóng thì lần ghi sau hụt → Werkzeug đóng generator → finally


def _app_log(msg, *args):
    """1 dòng vào Downloads\\iPOS_Ledger_Studio\\logs\\datastudio.log (chung nhật ký xuất file) — mở/đóng trang, lý do tắt app."""
    try:
        if _export_log_path():
            _xlog.info("[app] " + msg, *args)
    except Exception:
        pass


@app.route("/api/presence")
def presence():
    def stream():
        with _presence_lock:
            _presence["n"] += 1
            _presence["seen"] = True
            n = _presence["n"]
        _app_log("trang mo (presence %d)", n)
        try:
            yield "retry: 2000\n\n"
            while True:
                time.sleep(_PRESENCE_BEAT)
                yield ": ping\n\n"
        finally:
            with _presence_lock:
                _presence["n"] -= 1
                _presence["since"] = time.time()
                n = _presence["n"]
            _app_log("trang dong (presence %d)", n)

    resp = app.response_class(stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


if __name__ == "__main__":
    # Dọn nền có retry: <exe>.old là image của bản cũ vừa khởi chạy mình, phải đợi nó thoát hẳn.
    threading.Thread(target=_cleanup_old_executables, kwargs={"retry_seconds": 60}, daemon=True).start()
    threading.Thread(target=_cleanup_orphan_exports, daemon=True).start()
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
        _app_log("tat app: %s", reason)
        # Đóng connection pool SQL
        try:
            with _pool_lock:
                for c in list(_conn_pool.values()):
                    try: c.close()
                    except: pass
                _conn_pool.clear()
        except Exception:
            pass
        _drop_live_spools()   # file tạm của job xuất đang chạy (job chết theo tiến trình)
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

    _PRESENCE_GRACE = 20   # giây không còn trang nào giữ /api/presence → tắt (F5 nối lại trong ~1 s)
    _PRESENCE_FIRST = 90   # giây chờ trang ĐẦU TIÊN (trình duyệt mặc định mở nguội có thể chậm)

    def _watch_presence(reason):
        """Đường không theo dõi được tiến trình cửa sổ: chặn luồng này, tắt server khi không còn trang app nào mở."""
        print(f"[launcher] {reason} -> tat server khi khong con trang app nao mo")
        _app_log("%s -> canh trang app qua /api/presence", reason)
        with _presence_lock:
            _presence["since"] = time.time()
        last = time.time()
        while True:
            time.sleep(2)
            now = time.time()
            if now - last > 15:   # máy vừa ngủ dậy / tiến trình bị treo: cho trang thời gian nối lại, đừng tắt ngay
                with _presence_lock:
                    _presence["since"] = now
            last = now
            if _update_in_progress:
                continue
            with _presence_lock:
                idle = _presence["n"] <= 0 and now - _presence["since"] > (_PRESENCE_GRACE if _presence["seen"] else _PRESENCE_FIRST)
            if idle:
                _shutdown_everything("Khong con trang app nao mo")
                return

    def launch_app_window():
        """Mở app dưới dạng cửa sổ standalone. Khi user đóng cửa sổ → tắt server."""
        global _app_window_proc
        if not _wait_port_ready("127.0.0.1", APP_PORT):
            webbrowser.open(APP_URL)
            _watch_presence("Khong cho duoc cong")   # không track được cửa sổ → canh các trang app đang mở
            return

        chromium = _find_chromium_browser()
        if not chromium:
            # Không có Chrome/Edge → fallback browser mặc định (không track được khi đóng)
            webbrowser.open(APP_URL)
            _watch_presence("Khong co Chrome/Edge")
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
            _app_window_proc = proc   # updater cần handle này để đóng cửa sổ khi thay EXE
        except Exception:
            webbrowser.open(APP_URL)
            _watch_presence("Khong mo duoc Chrome/Edge")
            return

        # Block thread này cho tới khi user đóng cửa sổ Chrome --app
        try:
            proc.wait()
        except Exception:
            pass

        # Đang thay EXE: cửa sổ do CHÍNH updater đóng, không phải user. Tắt server ở đây là giết tiến trình
        # trước khi nó kịp chạy bản mới → cập nhật xong không có gì mở lên.
        if _update_in_progress:
            print("[launcher] Cua so dong do dang cap nhat -> khong shutdown, de updater lo")
            return

        # ⚠️ BẪY ĐÃ TỪNG LÀM SERVER "CHẾT NGAY KHI VỪA LÊN" (phát hiện 12/08/2026):
        # Nếu ĐÃ có sẵn 1 Chrome đang dùng chung --user-data-dir này (cửa sổ app cũ chưa đóng
        # hẳn, hoặc process mồ côi còn sót), thì chrome.exe vừa spawn sẽ BÀN GIAO việc mở cửa sổ
        # cho instance cũ rồi TỰ THOÁT NGAY (<1s). proc.wait() trả về tức thì → hiểu nhầm là
        # "user đã đóng cửa sổ" → server taskkill chính nó → EXE thoát mã 1, mọi request sau đó
        # báo "Failed to fetch" dù code hoàn toàn đúng. Triệu chứng điển hình: vừa build xong,
        # chạy EXE là chết ngay, phải đóng hết Chrome mới chạy được.
        # => Thoát quá nhanh = bàn giao, KHÔNG phải user đóng cửa sổ. Giữ server chạy, nhưng từ v1.10.8 không chạy ngầm
        #    mãi: cửa sổ nằm ở instance cũ nên không chờ được tiến trình → canh các trang app qua /api/presence.
        if time.time() - _t_spawn < 5:
            _watch_presence("Chrome ban giao cho instance cu (thoat <5s)")
            return

        # User đã đóng cửa sổ → shutdown toàn bộ
        _shutdown_everything("Cua so app da bi dong")

    def _wait_port_free(port, timeout=6):
        """Đợi cổng được nhả. Sau khi tự cập nhật, bản mới khởi chạy lúc bản cũ còn vài trăm ms nữa mới thoát —
        bind ngay là OSError 10048 rồi rơi vào `finally` tự tắt: "cập nhật xong mở lên là tắt ngay".
        Hết giờ vẫn chạy tiếp (Werkzeug bind kèm SO_REUSEADDR vẫn cướp được cổng), chỉ chậm, không chặn."""
        end = time.time() + timeout
        while time.time() < end:
            s_test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s_test.bind(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.3)
            finally:
                try:
                    s_test.close()
                except Exception:
                    pass
        return False

    _wait_port_free(APP_PORT)

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
    # host=127.0.0.1: CHỈ nghe tại máy đang chạy, không mở cổng ra mạng LAN. Mỗi người chạy EXE trên
    # máy mình và app tự nói chuyện với chính máy đó, nên đổi từ 0.0.0.0 sang 127.0.0.1 không ảnh hưởng
    # ai — chỉ chặn máy khác gọi vào cổng 5050 của app này.
    try:
        app.run(host="127.0.0.1", port=APP_PORT, debug=False, use_reloader=False)
    finally:
        _shutdown_everything("Flask exited")
