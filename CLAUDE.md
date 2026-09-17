# 📘 CLAUDE.md / GEMINI.md — BỘ NGUYÊN TẮC LÀM VIỆC & KIẾN TRÚC TOÀN TẬP LEDGERSTUDIO

> 📌 **DÀNH CHO TẤT CẢ AGENT AI (Claude Code, Gemini, Antigravity, Cursor, Windsurf, ChatGPT):**
> File này là **NGUỒN SỰ THẬT DUY NHẤT (Single Source of Truth)** của dự án `LedgerStudio`. Khi được yêu cầu *"đọc toàn bộ file md hướng dẫn và kiến trúc"*, bạn **BẮT BUỘC** tuân thủ 100% các nguyên tắc, ma trận báo cáo, quy trình test/build và danh sách bẫy bug dưới đây trước khi thực hiện bất kỳ chỉnh sửa nào.
> **Dự án:** LedgerStudio (`iPOS Ledger Studio`)  
> 🔀 **GIT: repo riêng [`trungkhanhduong93/ledgerstudio`](https://github.com/trungkhanhduong93/ledgerstudio) — PUBLIC** (từ 17/09/2026, chỉ nhánh `main`).
> Chỉ commit/push khi Trum bảo. Trước mọi push chạy `git remote get-url origin` — phải ra `.../ledgerstudio.git`.
> Remote cũ từng trỏ nhầm repo **LedgerReport** (gỡ 16/08/2026): push nhầm là đè code Studio lên `main` của Report.
> Repo công khai → **cấm commit mật khẩu / IP server DB / file dữ liệu khách** (`BaoCaoMau/` đã `.gitignore`).
> Build vẫn chạy **`BuildEXE-LedgerStudio.bat`**, EXE nằm trong `dist` (không lên git). Phát hành qua **GitHub Releases** — app từ v1.8.3 tự cập nhật (mục 5, Bước 5).
> **Cập nhật gần nhất:** 17/09/2026

---

## 1. ⚡ CÂY QUYẾT ĐỊNH ƯU TIÊN & 8 NGUYÊN TẮC VÀNG LÀM VIỆC

### 1.1 Cây quyết định ưu tiên 3 giây
```
1. Yêu cầu trực tiếp của USER trong phiên hiện tại (ĐỘ ƯU TIÊN CAO NHẤT)
2. Quy định môi trường dự án (GEMINI.md / CLAUDE.md)
3. Sổ tay vận hành (iacc-agent-skills Lean Master Index & 7 Sub-Modules)
4. Skill / Tài liệu chuyên môn lẻ
5. Mặc định của Model (ĐỘ ƯU TIÊN THẤP NHẤT)
```

### 1.2 8 Nguyên tắc vàng vận hành
1. **Khóa ngữ cảnh:** Xác định chính xác project/stack trước khi code. Trong workspace `ACC PMKT/`: đang ở thư mục `LedgerStudio` thì **CHỈ sửa LedgerStudio**, cấm sửa nhầm sang `LedgerReport`.
2. **Code Targeted:** Xem file bằng `view_file` trước khi edit. Sửa đúng vị trí, tuyệt đối không rewrite cả file lớn.
3. **Verify 4 Mức (M1 ➔ M4):**
   - **M1 (Compile):** Cú pháp Python (`ast.parse`) + JSX (`@babel/parser`).
   - **M2 (Test Repo):** Chạy `test_client` Flask in-process.
   - **M3 (Chạy thật):** Khởi chạy server / build EXE thật.
   - **M4 (Khớp nguồn sự thật):** Số liệu báo cáo khớp 100% với form gốc sổ sách kế toán.
4. **Rà 14 điểm mù:** Kiểm tra checklist điểm mù theo stack (Flask, React/Babel, SQL Server, EXE build) trước khi bàn giao.
5. **Git có kiểm soát:** chỉ commit/push khi Trum bảo, chỉ lên `origin` = `trungkhanhduong93/ledgerstudio` (Public — quét mật khẩu/IP trước khi push). Sửa xong vẫn chạy `BuildEXE-LedgerStudio.bat`, EXE ra thẳng `dist/iPOS_Ledger_Studio.exe`.
6. **Cập nhật tài liệu LIVE:** Chỉ cập nhật file `.md` bản LIVE (`GEMINI.md` / `CLAUDE.md` / `KIEN_TRUC_TOAN_TAP.md`).
7. **Báo cáo trung thực:** Trình bày rõ ràng: `🎯 Mục tiêu` ➔ `✅ Đã sửa` ➔ `🧪 Verify` ➔ `📦 Git` ➔ `🔍 Điểm mù` ➔ `📝 Docs`.
8. **Phát hành:** GitHub Releases của repo `ledgerstudio` — tag `vX.Y.Z` trùng `version.txt` nhúng trong EXE, asset tên đúng `iPOS_Ledger_Studio.exe`. Máy chạy từ v1.8.3 trở lên tự thấy banner "Cập nhật ngay". Repo phải để **Public**.

---

## 2. 🏗️ KIẾN TRÚC TOÀN TẬP DỰ ÁN

### 2.1 Tổng quan Công nghệ (Tech Stack)
- **Backend:** Python 3.12 + Flask + PyODBC (Kết nối SQL Server 2008-2025). Đóng gói trong [server.py](file:///d:/IACC%20HCM/iPOS%20ACC/ACC%20PMKT/LedgerStudio/server.py).
- **Frontend:** Single-File HTML [index.html](file:///d:/IACC%20HCM/iPOS%20ACC/ACC%20PMKT/LedgerStudio/index.html) (~530KB). Sử dụng React + Babel Standalone (biên dịch JSX trực tiếp trong trình duyệt) + Vanilla CSS/Tailwind (CDN).
- **Virtual Scroll:** Hook `useVirtualScroll` tự tạo cho các tab dữ liệu thô (xử lý mượt hàng trăm nghìn dòng).
- **Đóng gói EXE:** PyInstaller one-file, no-console thông qua script [build_exe.py](file:///d:/IACC%20HCM/iPOS%20ACC/ACC%20PMKT/LedgerStudio/build_exe.py). Output: `dist/iPOS_Ledger_Studio.exe`.

### 2.2 Ma trận Báo cáo & Phân nhánh 2 App

| Mã BC | Tên Báo Cáo | Endpoint API | Nguồn dữ liệu DB | Đã hỗ trợ ở |
|---|---|---|---|---|
| **BC005** | Bảng cân đối kế toán (TT200) | `/api/balance_sheet` | `BALANCE_VIEW` + `LEDGER_VIEW` | LedgerStudio & LedgerReport |
| **BC006** | Bảng cân đối phát sinh | `/api/trial_balance` | `BALANCE_VIEW` + `LEDGER` | LedgerStudio & LedgerReport |
| **BC007** | Sổ nhật ký chung (S03a-DN) | `/api/journal` | `LEDGER_VIEW` ⋈ `DM_ORGANIZATION` | LedgerStudio & LedgerReport |
| **BC008** | Sổ chi tiết tài khoản | `/api/account_details` | `BALANCE_VIEW` + `LEDGER_VIEW` | LedgerStudio & LedgerReport |
| **BC009** | LCTT trực tiếp (B03-DN) | `/api/cash_flow` | `LEDGER` theo TK đối ứng | LedgerStudio & LedgerReport |
| **BC010** | LCTT gián tiếp (B03-DN) | `/api/cash_flow` | `LEDGER` theo TK đối ứng | LedgerStudio & LedgerReport |
| **BC011** | **TH phát sinh công nợ (Studio)** | `/api/debt_summary` | `BALANCE_VIEW` + `LEDGER` (Group by `PR_DETAIL_ID, ACCOUNT_ID`) | **LedgerStudio** *(ở Report là BC013)* |
| **BC012** | **Sổ tiền mặt & tiền ngân hàng (Sổ quỹ)** | `/api/cash_book` | `VOUCHER_VIEW` (Định khoản kép, Cache Flat) | **LedgerStudio & LedgerReport** |
| **BC013** | **Bảng kê bán ra (6.2-GTGT)** | `/api/vat_sales_report` | `VAT_TRANSACTION_VIEW` (`DEBIT_CREDIT='CRD'`) | **LedgerStudio** |

> ⚠️ **Chú ý phân nhánh mã BC:** BC011 ở Studio là **TH phát sinh công nợ**, trong khi ở LedgerReport TH phát sinh công nợ là **BC013**. Khi làm việc ở Studio, luôn kiểm tra đúng mã `BC011` cho công nợ và `BC013` cho Bảng kê bán ra 6.2-GTGT.

---

## 3. 📺 MO TẢ CHI TIẾT TỪNG MÀN HÌNH & TÍNH NĂNG

### 3.1 Màn hình Đăng nhập (Login Modal)
- **Tính năng:** Nhập cấu hình máy chủ SQL Server (`Server`, `Database`, `User`, `Password`, `Driver`).
- **Xử lý Backend:** API `POST /api/login` thực hiện `_make_conn()`, thiết lập `session['db_config']`. Tự động nhận diện danh sách Driver SQL Server (ưu tiên `ODBC Driver 17 for SQL Server`).
- **Ghi nhớ:** Lưu cấu hình vào `localStorage` giúp đăng nhập nhanh lần sau.

### 3.2 Các Màn hình Dữ liệu thô (Data Tabs)
1. **Chứng từ tổng hợp (Tab LEDGER):**
   - **Tính năng:** Xem toàn bộ sổ cái kế toán (43 cột).
   - **Công nghệ:** Virtual Scroll cuộn mượt. Cho phép sắp xếp (Sort), tìm kiếm cột, lọc khoảng ngày, lọc đơn vị.
   - **Xuất dữ liệu:** Nút "Xuất Excel" ➔ Mode "1 file" xuất CSV stream server-side qua `/api/ledger/stream_csv` (không giới hạn dòng, lưu vào `Downloads\iPOS_Ledger_Studio\`).
2. **Chứng từ mua hàng (Tab PURCHASE):** 40 cột, tích hợp Virtual Scroll, hỗ trợ filter & xuất CSV.
3. **Chứng từ kho (Tab WAREHOUSE):** 41 cột, virtual scroll, filter theo kho/hàng hóa.
4. **Chứng từ bán hàng (Tab SALE):**
   - 44 cột dữ liệu. Đã bổ sung cột `ACCOUNT_ID_PR` (TK công nợ, màu cyan đậm), `PAYMENT_METHOD_NAME`, `EXTRA_NAME_2`, `INCOME_AMOUNT`, `VAT_INCOME_AMOUNT`, `COMMENTS`.
   - Virtual scroll 44 cột đồng bộ hoàn hảo giữa Header, Search Row, Row Render và Footer summary.
5. **Chứng từ tiền (Tab VOUCHER):** 35 cột, nguồn từ `VOUCHER` ⋈ `VOUCHER_DETAIL`, hỗ trợ phân trang SQL Server (`OFFSET/FETCH`).
6. **Doanh thu chờ phân bổ (Tab INCOME_ALLOC):** Sử dụng CTE SQL nâng cao, xuất CSV stream 27 cột qua `/api/income_alloc/stream_csv`.

### 3.3 Màn hình Báo cáo Kế toán (ReportTab)
Tất cả các báo cáo hiển thị dưới dạng tờ **A4/A4 Ngang (`.report-paper`)**:
- **Xuất Excel/CSV (mọi báo cáo, từ v1.8.2):** nút Excel mở `ReportExportDialog` → `POST /api/report_export/start` → job nền ghi `.xlsx` chuẩn form bằng `xlsx_report.py` (hoặc CSV thô) vào `Downloads\iPOS_Ledger_Studio\`, poll `/api/export/status` (tiến trình thật, Hủy được) → xong có nút Mở file / Mở thư mục. Số lưu giá trị thật hiển thị `#,##0;(#,##0);"-"`, % lưu 0.1552 hiển thị 15.52%, tự tách sheet ở 1.000.000 dòng kèm dòng "Cộng chuyển sang sheet sau". Khối tiêu đề màn hình và file dùng chung `buildReportHeader`.
- **BC005 - Bảng Cân Đối Kế Toán (TT200):** Cấu trúc chuẩn Thông tư 200/2014, tự động tính tổng tài sản & nguồn vốn.
- **BC006 - Bảng Cân Đối Phát Sinh:** Dư đầu kỳ, phát sinh Nợ/Có trong kỳ, dư cuối kỳ theo từng tài khoản.
- **BC007 - Sổ Nhật Ký Chung (S03a-DN):**
  - Hỗ trợ 2 chế độ xem trên Web: **Chi tiết** (13 cột) & **Tổng hợp** (10 cột - ẩn 3 cột Đơn vị, Tên đơn vị, Ngày ghi sổ).
  - Phân trang server-side 1.000 dòng/trang với bộ điều hướng **`PageJumper`** (gõ số trang + Enter).
  - Xuất Excel 3 mẫu: **Chi tiết** / **Tổng hợp** (như bảng đang xem) / **Đầy đủ cột** (Công việc, Đối tượng, Ghi chú). Server tự truy vấn toàn bộ `LEDGER_VIEW` (không phụ thuộc trang đang xem).
- **BC008 - Sổ Chi Tiết Tài Khoản:**
  - Hỗ trợ lọc đa tài khoản (ví dụ `111,112`), phân trang 1.000 dòng/trang.
  - Xuất Excel: server tự truy vấn toàn bộ (số dư đầu kỳ + phát sinh + số dư cuối kỳ), tiêu đề có dòng Tài khoản.
- **BC009 & BC010 - LCTT Trực Tiếp & Gián Tiếp (B03-DN):** Tự động bóc tách dòng tiền theo tài khoản đối ứng.
- **BC011 - Bảng Tổng Hợp Phát Sinh Công Nợ (Studio):**
  - Gộp theo cặp `(PR_DETAIL_ID, ACCOUNT_ID)`. Có **cột TK** ở cuối bảng.
  - Định dạng A4 Ngang, tự động tính dư net lưỡng tính cho từng đối tượng công nợ.
- **BC012 - Sổ Tiền Mặt & Tiền Ngân Hàng (Sổ Quỹ):**
  - Truy vấn từ `VOUCHER_VIEW`, phân trang 10.000 dòng/trang.
  - Tích hợp bộ nhớ đệm Flat Cache (`_cashbook_flat_cached`) giúp chuyển trang tức thì.
- **BC013 - Bảng Kê Bán Ra (Mẫu 6.2-GTGT):**
  - Nguồn `VAT_TRANSACTION_VIEW` (`DEBIT_CREDIT='CRD'`). Hỗ trợ 2 chế độ xem: **Chi tiết** và **Tổng hợp**.
  - Áp dụng `content-visibility: auto` và `Intl.NumberFormat` giúp render mượt mà 0% CPU lag.
  - Xuất Excel 2 mẫu Chi tiết / Tổng hợp, thuế suất lưu dạng % thật (10% = 0.1), 3 dòng tổng dưới bảng là ô số.

### 3.4 Tự cập nhật (từ v1.8.3)
- Mở app 1 giây → `GET /api/check_update` gọi `api.github.com/repos/trungkhanhduong93/ledgerstudio/releases/latest` (không đăng nhập, timeout 3s), so `tag_name` với `version.txt`. Lỗi mạng / chưa có release → im lặng.
- Có bản mới → banner cam trên màn hình đăng nhập và màn hình chính (`AutoUpdateBanner`). Bấm "Cập nhật ngay" → `POST /api/apply_update` → poll `/api/update_progress` (`AutoUpdateModal`).
- Server (`_download_and_swap`): tải asset `iPOS_Ledger_Studio.exe` vào `<exe>.new`, kiểm dung lượng + SHA-256 (trường `digest` GitHub trả kèm asset) → đổi tên exe đang chạy thành `<exe>.old` → đặt bản mới vào tên cũ → đóng cửa sổ Chrome app → chạy bản mới (env đã gỡ biến `_PYI_*`) → thoát. Bản mới dọn `<exe>.old` (thử lại tới 60s).
- Chạy từ source (`python server.py`) chỉ kiểm tra được bản mới, bấm cập nhật trả 400.

---

## 4. 🐛 TỔNG HỢP BẪY BUG THỰC TẾ & CÁCH KHẮC PHỤC (PITFALLS)

### Bẫy 1: "Ghost Server" trên Port 5050 khi Test Backend
- **Triệu chứng:** Sửa code trong `server.py` nhưng chạy `curl` hoặc test web vẫn ra kết quả của code cũ.
- **Nguyên nhân:** Một tiến trình `python.exe` hoặc `iPOS_Ledger_Studio.exe` cũ vẫn đang chạy ngầm chiếm giữ port 5050.
- **Cách khắc phục:** **Luôn test backend bằng Flask `test_client` in-process** không qua port:
  ```python
  import server
  c = server.app.test_client()
  c.post('/api/login', json={...})
  res = c.get('/api/cash_book?...').get_json()
  ```

### Bẫy 2: Lệch Thứ Tự Tham Số SQL Bind (Params Mismatch)
- **Triệu chứng:** SQL query đúng nhưng API trả về 0 dòng dữ liệu.
- **Nguyên nhân:** Bộ lọc đơn vị `_org_filter_sql` (mặc định `col NOT IN (<externals>)`) được chèn vào mệnh đề WHERE trước các bộ lọc khác, nhưng mảng `params` lại được `append()` ở cuối cùng.
- **Cách khắc phục:** Mảng `params` truyền vào PyODBC **phải nối đúng theo thứ tự xuất hiện của dấu `?` trong chuỗi SQL**.

### Bẫy 3: Cột `TRAN_DATE` kiểu `smalldatetime`
- **Triệu chứng:** SQL Server ném lỗi **Error 8180 / 8116**.
- **Nguyên nhân:** Dùng hàm `SUBSTRING(TRAN_DATE, ...)` trên cột kiểu `smalldatetime`.
- **Cách khắc phục:** Dùng `CONVERT(VARCHAR(8), TRAN_DATE, 112)` hoặc `MONTH()`, `YEAR()`. Khi truyền tham số ngày từ Python, luôn format `.strftime('%Y%m%d')`.

### Bẫy 4: Sự cố Công cụ tự động chèn `WITH (NOLOCK)` (Lỗi SQL 8180)
- **Triệu chứng:** Alert "Incorrect syntax near the keyword 'with'".
- **Nguyên nhân:** Tool tự động chèn `WITH (NOLOCK)` làm tách tên Alias (vd `PD2` ➔ `PD WITH (NOLOCK)2`) hoặc nhân đôi hint.
- **Cách khắc phục:** Sử dụng script Regex 3 lượt trong Python để ghép lại Alias và loại bỏ hint thừa.

### Bẫy 5: Truy vấn Cột không tồn tại trên View
- **Triệu chứng:** API crash 500 và làm ngắt Connection Pool (`HY000`).
- **Cách khắc phục:** Luôn introspect schema (`INFORMATION_SCHEMA.COLUMNS`) trước khi SELECT các cột mở rộng (ví dụ trong `SALE_VIEW`).

### Bẫy 6: Xuất Excel Báo Cáo Phân Trang bị Thiếu Dòng / Lệch Kỳ
- **Triệu chứng:** File BC007/BC008/BC012/BC013 chỉ có dòng của trang đang xem; hoặc tiêu đề ghi Tháng 8 mà số liệu là Tháng 7.
- **Cách khắc phục (từ v1.8.2):** báo cáo phân trang KHÔNG xuất từ DOM — server tự truy vấn toàn bộ trong `_rx_plan` (cùng view + cùng ORDER BY với màn hình). App gửi bộ lọc CHỤP lúc nạp dữ liệu (`viewSnapRef`), không phải bộ lọc đang gõ dở; lệch thì dialog cảnh báo. `page_size=0` ở các endpoint xem vẫn giữ (chặn chia cho 0).

### Bẫy 7: Lọc Đa Tài Khoản Trả 0 Dòng
- **Triệu chứng:** Nhập `111,112` thì báo cáo trả về bảng rỗng.
- **Nguyên nhân:** Dùng SQL `ACCOUNT_ID LIKE '111,112%'`.
- **Cách khắc phục:** Dùng helper `_acc_like_sql("111,112", "ACCOUNT_ID")` để sinh chuỗi SQL `(ACCOUNT_ID LIKE '111%' OR ACCOUNT_ID LIKE '112%')`.

### Bẫy 8: xlsxwriter `constant_memory` — ghi lùi dòng là MẤT DỮ LIỆU IM LẶNG
- **Triệu chứng:** File .xlsx thiếu ô/thiếu chữ ở đầu bảng, không báo lỗi gì.
- **Nguyên nhân:** `constant_memory` ghi xong dòng r là xả ra đĩa; mọi lệnh ghi vào dòng < dòng hiện tại bị bỏ qua. `merge_range` gộp 2 dòng (rowspan) ghi ô trống xuống dòng dưới TRƯỚC khi dòng trên ghi xong.
- **Cách khắc phục:** ghi tay từng ô theo thứ tự dòng rồi mới khai báo vùng gộp (`_write_table_header` trong `xlsx_report.py`). `set_row` phải gọi trước khi ghi ô của dòng đó. (Hàm `.xls` HTML-mso cũ `exportReportXls` đã gỡ từ v1.8.2.)

### Bẫy 9: Icon vô hình do dùng Tên Icon không tồn tại
- **Triệu chứng:** Nút bấm hoặc Modal không hiển thị Icon.
- **Nguyên nhân:** Khai báo `<Icon name="..."/>` với tên không có trong `const icons` của `index.html` (v1.8.2 có 29 icon, đã thêm `x`, `folder-open`, `external-link`, `clock`, `layers`, `hard-drive`, `rotate-ccw`, `zap`, `rows`; vẫn KHÔNG có `list`, `folder`).
- **Cách khắc phục:** Kiểm tra hằng `const icons` trước khi dùng, hoặc dùng trực tiếp ký tự Unicode (như `✕`).

### Bẫy 10: Tự động khóa file EXE khi đang mở app
- **Triệu chứng:** `build_exe.py` báo SUCCESS nhưng file `.exe` trong `dist/` không thay đổi.
- **Nguyên nhân:** File `iPOS_Ledger_Studio.exe` đang chạy ngầm nên PyInstaller không thể ghi đè.
- **Cách khắc phục:** Tắt tất cả tiến trình `iPOS_Ledger_Studio.exe` trong Task Manager trước khi chạy build.


### Bẫy 11: EXE phình to vì gói cài sẵn trên máy build
- **Triệu chứng:** `dist/iPOS_Ledger_Studio.exe` từ 15,8 MB lên 43 MB (v1.8.1), mở app chậm hơn vì onefile phải giải nén.
- **Nguyên nhân:** PyInstaller lần theo import tuỳ chọn: `flask.cli` → `python-dotenv` → `dotenv.ipython` → IPython → numpy/matplotlib (máy build có cài các gói này cho việc khác).
- **Cách khắc phục:** `build_exe.py` đã `--exclude-module` IPython, matplotlib, matplotlib_inline, numpy, pandas, PIL. Build xong luôn nhìn dung lượng EXE; tăng vọt thì tra `build/iPOS_Ledger_Studio/xref-*.html` xem ai kéo gói vào.

### Bẫy 12: pyodbc trả `Decimal` — không phải `int/float`
- **Triệu chứng:** File .xlsx xuất danh sách chứng từ có cột số lượng/đơn giá/thành tiền là CHỮ: SUM ra 0, ô có tam giác xanh.
- **Nguyên nhân:** kiểm `isinstance(v, (int, float))` bỏ sót `Decimal` (cột money/decimal của SQL Server).
- **Cách khắc phục:** coi `Decimal` là số (`_write_xlsx_to_disk`, `xlsx_report._to_float`). Cộng dồn tổng thì cộng bằng `Decimal` rồi mới đổi float khi ghi.

### Bẫy 13: Tự cập nhật im lặng không chạy / thay nhầm file
- **Repo Private** → API trả 404 cho EXE (không đăng nhập) → không máy nào thấy bản mới, KHÔNG báo lỗi. Repo phải Public.
- **Asset sai tên** (chỉ có `.zip`, hoặc đổi tên EXE) → `has_update=False` im lặng. Updater chỉ nhận đúng `iPOS_Ledger_Studio.exe`, cố ý không lấy "file .exe đầu tiên".
- **Tag lệch version nhúng trong EXE** (tag `v1.8.4` nhưng EXE build ra 1.8.3) → máy cập nhật xong vẫn thấy "có bản mới", bấm lại mãi. Tag lấy ĐÚNG từ `version.txt` sau khi build.
- **Env PyInstaller**: spawn bản mới mà không gỡ `_PYI_*` → bootloader báo "parent process has different executable", bản mới không lên (bẫy LedgerReport 28/08/2026) → `_child_env_without_pyi`.
- **Dọn file**: chỉ xoá `<tên exe>.old/.new`. Bản LedgerReport xoá mọi `*.old/*.new/*.tmp_dl` trong thư mục chứa EXE — EXE để ở Downloads là mất file của người dùng.

---

## 5. 🛠️ QUY TRÌNH DEV, TEST & BUILD EXE CHUẨN

### Bước 1: Kiểm tra Cú pháp (Syntax Check)
```bash
# Kiểm tra cú pháp Python
python -c "import ast; ast.parse(open('server.py', encoding='utf-8').read()); print('PYTHON_SYNTAX_OK')"
```

### Bước 2: Test Backend qua Flask `test_client`
```python
python -c "
import server
c = server.app.test_client()
c.post('/api/login', json={'server':'<SERVER>','database':'IACC_CHULONG','user':'<USER>','password':'<PASSWORD>','driver':'ODBC Driver 17 for SQL Server'})
d = c.get('/api/cash_book?from_date=01/01/2026&to_date=31/01/2026&acc_ids=111&page=1').get_json()
print('PAGINATION:', d['pagination'])
"
```

### Bước 3: Build File Thực Thi EXE
```bash
# Đóng tất cả tiến trình đang chạy
taskkill /F /IM iPOS_Ledger_Studio.exe /T 2>nul

# Chạy build script tự động tăng version
python build_exe.py
```

### Bước 4: Kiểm tra File Output
- Verify mtime + dung lượng (~15,8 MB) của `dist/iPOS_Ledger_Studio.exe`; chạy thử `/api/version` ra đúng `version.txt`.

### Bước 5: Phát hành bản cập nhật (chỉ khi Trum bảo)
```bash
# 1. Đẩy mã nguồn đúng bản vừa build
git remote get-url origin          # phải ra .../ledgerstudio.git
git add -A && git commit -m "vX.Y.Z: ..." && git push origin main
# 2. Release: tag = version.txt, asset tên ĐÚNG iPOS_Ledger_Studio.exe (+ .zip cho người tải tay)
gh release create vX.Y.Z dist/iPOS_Ledger_Studio.exe dist/iPOS_Ledger_Studio.zip --repo trungkhanhduong93/ledgerstudio --target main --title "iPOS Ledger Studio vX.Y.Z" --notes-file notes.md
```
- Máy đang chạy bản ≥ v1.8.3 thấy banner ở lần mở app kế tiếp. Máy còn bản ≤ v1.8.2 (chưa có updater) phải tải tay 1 lần.

---

> 🔴 **CẤM:** push lên remote nào khác `trungkhanhduong93/ledgerstudio` · push nhánh local `lich-su-truoc-17-09` hoặc `git push --all` · `push --force` / viết lại lịch sử khi Trum chưa bảo · commit mật khẩu, IP server DB, file dữ liệu khách.
