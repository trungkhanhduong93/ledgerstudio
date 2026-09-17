# NHẬT KÝ CÔNG VIỆC — LedgerStudio

> Toàn bộ những gì đã làm với **LedgerStudio**, và **vì sao**. Đọc file này trước khi sửa tiếp.
> Kiến trúc và ma trận báo cáo: [CLAUDE.md](CLAUDE.md).
> Phiên gần nhất: **17/09/2026** · EXE hiện hành: **iPOS_Ledger_Studio v1.8.2**

---

## 0. LedgerStudio là gì — và KHÔNG phải là gì

| | LedgerStudio (thư mục này) | LedgerReport |
|---|---|---|
| **Phục vụ** | **DB iPOS chung chung** của nhiều khách | **Riêng `IACC_CHULONG`** |
| EXE | `dist\iPOS_Ledger_Studio.exe` | `dist\iPOS_Accounting_Report.exe` |
| File build | **`BuildEXE-LedgerStudio.bat`** | `BuildEXE-LedgerReport.bat` |
| **Git** | **KHÔNG CÓ. Không push đi đâu.** | Có — GitHub `trungkhanhduong93/ledgerreport` |
| Phát hành | Đưa thẳng file EXE cho người dùng | GitHub Releases (Actions tự tạo) |

### Studio KHÔNG có 5 báo cáo đặc thù Chú Long

`BC001`–`BC004` (KQKD) và **LCTT gián tiếp Chú Long** chỉ có ở LedgerReport. Chúng chạy qua engine
`_calc_results()` map **cứng** bộ mã danh mục riêng của Chú Long (`ITEM_CLASS1_ID`: CF, THUCAN, MC,
TA, CB… và `EXPENSE_CLASS_ID`: THTT, TTTM, CPVH, TL, BH…). Bê sang DB khác thì mọi chỉ tiêu về 0
mà **không báo lỗi gì**. Đừng port sang đây.

Studio có **9 báo cáo BC005–BC013**, đều là mẫu chuẩn kế toán VN.

### ⚠️ Mã BC cùng số KHÁC NGHĨA giữa hai bên

| Mã | **LedgerStudio** | LedgerReport |
|---|---|---|
| BC011 | **Tổng hợp phát sinh công nợ** | LCTT gián tiếp (Chú Long) |
| BC013 | **Bảng kê bán ra 6.2** | Tổng hợp phát sinh công nợ |
| BC014 | *(không có)* | Bảng kê bán ra 6.2 |

Nhìn nhầm là sửa nhầm báo cáo.

---

## 1. Ngắt Studio khỏi GitHub của LedgerReport *(16/08/2026)*

**Vấn đề phát hiện được:** thư mục LedgerStudio có `.git`, và `origin` trỏ **đúng vào repo GitHub
của LedgerReport** (`trungkhanhduong93/ledgerreport`), **cùng nhánh `main`**, HEAD ở commit `5ebdacb`.

Chỉ cần một lệnh `git push` chạy nhầm trong thư mục này là **đè code Studio lên `main` của
LedgerReport**. Ngược lại `git pull` sẽ kéo toàn bộ code Report (kèm BC001–BC004 đặc thù) vào đây.

**Gốc rễ:** commit thứ hai của repo đó là `27d5e98 "Initial commit: LedgerStudio project codebase"`
— repo mang tên *ledgerreport* vốn được dựng lên từ **chính codebase của LedgerStudio**. Hai project
chung một gốc lịch sử. Đó là lý do trước đây `CLAUDE.md` trong LedgerReport lại mô tả LedgerStudio,
và tab "Doanh thu chờ phân bổ" của Studio lại nằm trong Report.

**Đã xử lý:** `git remote remove origin`. Giờ `git push` báo `No configured push destination`.
**Giữ lại lịch sử git local** — không xoá `.git`, vì lịch sử là phao cứu sinh khi mất code
(xem bài học ở [LedgerReport/SU_CO_15082026.md](../LedgerReport/SU_CO_15082026.md)).

> Lịch sử repo trên GitHub **vẫn còn** commit `27d5e98` chứa codebase Studio. Muốn xoá hẳn phải
> `git filter-repo` + force-push — phá huỷ, không đảo ngược. Chưa làm.

---

## 2. Tách file build — không thể build nhầm *(16/08/2026)*

**Vấn đề:** cả hai project đều có một `BuildEXE.bat` **cùng tên**, tự gọi PyInstaller và **đoán** tên
EXE theo thư mục đang đứng. Bản nằm trong thư mục *LedgerReport* lại build ra `iPOS_Ledger_Studio`
(di sản copy nhầm), và thiếu `--add-data version.txt`.

**Đã xử lý:** xoá `BuildEXE.bat` ở **cả hai bên**, thay bằng hai file **tên khác hẳn nhau**.
Ba lớp chống nhầm:

1. **Tên file khác hẳn** — nhìn là biết đang chạy cái nào.
2. **Ghim cứng tên EXE** trong `.bat` (`set "APP_NAME=iPOS_Ledger_Studio"`) rồi truyền thẳng
   `python build_exe.py %APP_NAME%`. `build_exe.py` chỉ nhận đúng 2 tên hợp lệ, sai là `exit 1`.
   Chạy trần không tham số vẫn đoán như cũ **nhưng in cảnh báo to**.
3. **Chặn theo đường dẫn** — `.bat` này nằm trong thư mục có chữ `LedgerReport` thì **dừng, exit 1**.
   Đã test thật: copy `BuildEXE-LedgerStudio.bat` vào thư mục tên `…LedgerReport` rồi chạy →
   `[DUNG] Ban dang dung trong thu muc LedgerReport`, exit 1, không build.

> ⚠️ File `.bat` phải lưu **CRLF, KHÔNG BOM**. Ghi bằng LF thì `cmd.exe` cắt câu lệnh loạn xạ,
> báo `'ILD' is not recognized as an internal or external command`. Đã vấp thật.

---

## 3. Sáu nhóm lỗi đã sửa *(16/08/2026)*

Rà bằng cách đối chiếu với **8 lỗi đã tìm ra ở LedgerReport** trong sự cố 15/08.

### ✅ Studio KHÔNG dính 4 lỗi nặng nhất của Report

| Lỗi ở Report | Studio |
|---|---|
| `session['logged_in']` đọc mà không bao giờ gán → luôn 401 | Sạch (đọc 0, gán 0) |
| `_calc_results` định nghĩa 2 lần, bản sau che bản trước | Không trùng tên hàm nào |
| `SELECT L.EXPENSE_NAME` — LEDGER không có cột đó | Không có |
| Gọi `_compute_cdkt()` là hàm đã bị mất | Không có |

Studio **chưa bị phá** như Report. Nó chỉ mang những lỗi *có sẵn từ gốc chung*.

### 🔴 Sáu nhóm đã sửa

**1. Bộ lọc đơn vị không nhất quán — 10 chỗ tự dựng `ORGANIZATION_ID IN`**

Các hàm dính: `get_balance_sheet` (+ `run_ledger` **lồng bên trong**), `get_trial_balance` (3 chỗ),
`get_journal`, `get_account_details`, `get_debt_summary`, `report_export_csv`, `export_excel_backend`.

Đây **đúng cơ chế** đã làm Bảng cân đối kế toán của Report lệch **3.252.634.439**. Nay cả 17 chỗ
đều đi qua `_org_filter_sql`. Chỗ quyết định là `run_ledger` lồng trong `get_balance_sheet` —
đó mới là truy vấn sinh ra số dư thật, không phải `org_where` ở ngoài.

**2. Chốt an toàn khi DB không có đơn vị gốc `'00'`**

`_get_external_org_ids()` tính "đơn vị ngoài cây" bằng cách lần `PARENT_ORGANIZATION_ID` về gốc `'00'`.
DB nào **không có** đơn vị mã `'00'` thì *mọi* đơn vị đều bị coi là ngoài cây → `NOT IN (tất cả)` →
**mọi báo cáo và mọi danh sách trả 0 dòng, không một thông báo lỗi nào**.

Rủi ro này **cao hơn hẳn ở Studio** vì Studio chạy trên DB của nhiều khách, mỗi nơi đánh mã một kiểu.
Nay: không tìm thấy `'00'` ⇒ không lọc gì + ghi cảnh báo vào log.

**3. Middleware gzip — dính cả hai lỗi**

- `get_data()` trên response `stream_with_context` **nuốt trọn generator vào RAM** → mất sạch tác
  dụng streaming của các endpoint xuất CSV. File lớn thì trình duyệt đứng im, RAM phình theo.
- `send_from_directory` bật `direct_passthrough` khiến `get_data()` ném lỗi bị `except` nuốt →
  `index.html` **chưa từng được nén**. Sau khi sửa: **560.912 → 82.551 bytes (giảm 85%)**.

Thứ tự xét quan trọng: phải xử nhánh `direct_passthrough` **TRƯỚC** nhánh `is_streamed`, vì file tĩnh
cũng bị tính là `is_streamed`.

**4. Bỏ ping `SELECT 1` trước mọi request**

Mỗi thao tác gánh thêm nguyên một vòng đi-về tới SQL Server. Nay chỉ dò lại khi connection nhàn rỗi
> 30 giây; `close_pool_for` dọn luôn `_conn_last_used` để hai dict không lệch nhau.

**5. Định dạng phần trăm trong file `.xls`**

Trước: ô `%` giữ nguyên chuỗi `"15.54%"` → Excel coi là **text, không cộng/tính được**.
Nay thêm class `xpct0`–`xpct4`: value thật là `0.1554`, hiển thị `15.54%`. Giữ đúng số chữ số thập
phân đang hiển thị trên web. Dịch dấu thập phân bằng `toFixed` chứ **không chia 100 trần** —
`15.54/100` trong JS ra `0.15539999999999998`, ghi vào Excel là lệch.

**6. Cột `RECEIVE_DATE` không tồn tại**

Tab "Doanh thu chờ phân bổ" SELECT cột `RECEIVE_DATE`, mà `INCOME_ALLOCATION` trên `IACC_CHULONG`
chỉ có 24 cột và **không hề có cột đó** → crash 500, ngắt connection pool, tab chết hoàn toàn.

**Không xoá cứng** — DB của khách khác có thể có cột này thật. Thay bằng dò `INFORMATION_SCHEMA`
(cache theo tên DB) rồi chỉ SELECT cột thực có. Lọc **cả whitelist sắp xếp** — nếu không, người dùng
bấm sort đúng cột đó vẫn ra `ORDER BY A.RECEIVE_DATE` → crash dù SELECT đã tránh được.

### Bẫy vá kèm

`report_export_csv` có ba biến lọc dùng **chung một mảng `org_params`**: `org_where`, `org_where_l`,
`org_where_lv`. Sửa cái đầu mà quên hai cái sau là lệch số dấu `?`:

> `The SQL contains 2 parameter markers, but 3 parameters were supplied`

Đúng lỗi này vừa làm hỏng xuất CSV Sổ nhật ký chung bên Report. Studio dính y hệt, đã vá.

---

## 4. Verify — đạt M4 trên DB thật

Test trên **`IACC_CHULONG`** (18.516.886 dòng LEDGER), kỳ **01/07–31/07/2026**, mặc định không chọn đơn vị.

Lợi thế của việc test trên chính DB này: **những báo cáo trùng nhau phải ra ĐÚNG CÙNG SỐ với
LedgerReport** — có sẵn một bộ đáp án để đối chiếu.

```
BC005  Tổng tài sản = Tổng nguồn vốn = 165.309.773.349   *** CÂN ***
       so với LedgerReport                                KHỚP TỪNG ĐỒNG
BC006  Dư đầu 135.615.994.098  Nợ = Có                    CÂN
       Phát sinh 331.164.100.304  Nợ = Có                 CÂN — khớp LedgerReport
       Dư cuối 165.173.074.702  Nợ = Có                   CÂN
```

**15/15 endpoint trả HTTP 200**, kể cả `income_alloc` trước đây chết hoàn toàn.

Thang đo: `M1 dịch được < M2 test_client < M3 chạy EXE thật < M4 số liệu khớp nguồn sự thật`.
Lần này đạt **M4** nhờ đối chiếu chéo với LedgerReport.

> Chênh lệch **hợp lệ**, đừng tưởng là lỗi: BC006 dư cuối Nợ (`165.173.074.702`) thấp hơn BC005 tổng
> tài sản (`165.309.773.349`) đúng `136.698.647`. BC006 bù trừ Nợ/Có trong cùng tài khoản, còn CĐKT
> phải **tách tài khoản lưỡng tính theo từng đối tượng** (khách dư Nợ vào Phải thu, khách dư Có sang
> Người mua trả tiền trước). Nên CĐKT luôn ≥ và chênh đúng bằng phần tách ra.

---

## 5. Quy trình làm việc với Studio

```bash
# 1. Sửa code
# 2. Cú pháp (M1)
python -c "import ast; ast.parse(open('server.py',encoding='utf-8').read()); print('OK')"
node check_babel.js

# 3. Chạy thật trên DB (M2/M4) — KHÔNG test qua cổng 5050, dùng test_client in-process
#    (cổng 5050 hay còn tiến trình EXE cũ chiếm giữ → test ra kết quả cũ)

# 4. Build — BẮT BUỘC dùng đúng file này
BuildEXE-LedgerStudio.bat
```

**Git (từ 17/09/2026):** chỉ commit/push khi Trum bảo, remote duy nhất `trungkhanhduong93/ledgerstudio` (Public) — xem mục 9.

### Bẫy phải nhớ

| Bẫy | Cách tránh |
|---|---|
| Lệch số tham số bind | Sửa bộ lọc xong **quét lại**: `grep -n "list(org_ids)\|+ org_ids" server.py` phải rỗng. Và quét **SAU** khi sửa hết, không phải giữa chừng |
| SELECT cột không tồn tại | Introspect `INFORMATION_SCHEMA.COLUMNS`, đừng đoán tên cột |
| `TRAN_DATE` là `smalldatetime` | Cấm `SUBSTRING`. Dùng `CONVERT(VARCHAR(8), …, 112)` hoặc `MONTH()/YEAR()` |
| Nối code vào cuối `server.py` | Sinh hàm trùng tên, bản sau che bản trước. Quét trùng tên trước khi thêm hàm |
| Build nhầm project | Chỉ dùng `BuildEXE-LedgerStudio.bat` |
| `.bat` lưu LF | `cmd.exe` cắt lệnh loạn. Bắt buộc CRLF, không BOM |

---

## 6. Còn treo

- ~~Định dạng `%` trong file `.xls` chưa mở bằng Excel xác nhận.~~ Bỏ `.xls` từ v1.8.2; `.xlsx` mới đã mở bằng Excel thật (mục 8.6).
- **Xuất báo cáo .xlsx chưa đối chiếu số trên DB thật (M4)** — xem mục 8.6.
- **Hiệu năng chưa đo trước/sau** cho danh sách chứng từ. Nút thắt gốc không nằm ở code:
  DB 10,6 GB / buffer pool 1.410 MB (trần cứng SQL Express) ≈ 7,7 : 1 → phần lớn truy vấn phải đọc đĩa.
  `AUTO_SHRINK` và `AUTO_CLOSE` đã tắt sẵn trên server — kiểm rồi, không phải thủ phạm.
- **Phân trang vẫn dùng `ROW_NUMBER()`** (chọn cố ý để tương thích SQL Server 2008). DB CHULONG là
  SQL 2025 `compatibility_level = 170` nên `OFFSET/FETCH` dùng được — nhưng chưa đo nên chưa đổi.

---

## 7. Cập nhật phiên bản v1.8.0 *(03/09/2026)*

1. **Modal thông báo hiện đại thay thế `alert()` trình duyệt:**
   - Thay thế hộp thoại pop-up thô `localhost:5050 says` khi chưa chọn tài khoản (ở BC011 Công nợ & BC008 Sổ chi tiết) bằng UI Modal bo góc, nền backdrop blur, icon cảnh báo và nút xác nhận "Đã hiểu".
2. **Báo cáo BC011 - Bảng tổng hợp công nợ:**
   - Cột **Mã đối tượng** mở rộng từ `8%` lên `13%` (`line-height: 1.35`), thu gọn cột **TK** từ `10%` về `5%` (vừa khít mã TK 3-4 chữ số như 1311, 3311), đảm bảo mã đối tượng dài chỉ xuống tối đa 2 dòng.
3. **Khắc phục border ô Có ở Dư cuối kỳ bị tô đậm hơn các line còn lại:**
   - Gốc rễ: CSS `.report-table th:last-child { border-right: 2px solid #000 !important; }` đã chọn nhúng vào ô `<th>Có</th>` cuối hàng 2 của thead (do cột TK nằm ở hàng 1 với `rowSpan="2"`).
   - Đã chuẩn hoá toàn bộ viền `report-table` và `bc006-table` về đồng nhất `1px solid #000 !important`.
4. **Định dạng cột số tiền trong file Excel xuất ra:**
   - Trong `exportReportXls()`, bổ sung trực tiếp thuộc tính inline `mso-number-format:'\#\,\#\#0'` vào `style` của thẻ `<td>` cho các ô số tiền (`col-value`), text giữ `mso-number-format:'\@'`.
   - Giá trị lưu trong ô vẫn là số thuần `1000000` (tính toán, hàm SUM bình thường), Excel hiển thị đẹp mắt theo chuẩn `1,000,000`.
5. **Build EXE:**
   - Đóng gói thành công `dist/iPOS_Ledger_Studio.exe` phiên bản **1.8.0** (15.8 MB).

---

## 8. Xuất báo cáo ra .xlsx chuẩn form — v1.8.2 *(16–17/09/2026)*

> Mục này thay bản Gemini ghi lúc 20:20 16/09. Bản đó có 3 chỗ không khớp thực tế: "test suite 10/10 PASS"
> (không có bộ test đó trong thư mục), EXE "41.45 MB" (file thật 43,4 MB) và "smoke test mượt mà" (EXE 1.8.1 phình
> gấp 2,7 lần — xem 8.5). Số liệu dưới đây là kết quả chạy thật, kèm cách tái hiện.

### 8.1 Vì sao làm lại toàn bộ đường xuất báo cáo

| Cũ (≤ v1.8.0) | Hậu quả |
|---|---|
| `.xls` HTML-mso dựng từ DOM (`exportReportXls`) | Excel mở luôn cảnh báo "định dạng không khớp đuôi file"; không phải .xlsx thật |
| BC008/012/013 nạp HẾT dòng vào DOM để clone (`exportFullXls`) | Vài chục nghìn dòng là treo tab |
| BC007 chỉ xuất được CSV thô | Không có form, không có chữ ký |
| CSV tải về rồi ĐỌC LẠI toàn bộ thành text POST lên `/api/save_export` | File vài trăm MB phình RAM cả trình duyệt lẫn server |
| Thanh tiến trình 15% → 45% → 75% chạy bằng `setTimeout` | Số giả, không phản ánh gì |

### 8.2 Kiến trúc mới

- **`xlsx_report.py`** (module mới, không phụ thuộc Flask/pyodbc): layout 9 báo cáo + writer `constant_memory`.
  - Tiền: số thật, hiển thị `#,##0;(#,##0);"-"` — y `formatNum()` trên web (âm trong ngoặc, 0 là "-").
  - %: `15.52` → lưu `0.1552`, hiển thị `0.00%` (số chữ số thập phân theo giá trị). Ngày: datetime thật. Mã TK/số HĐ: chuỗi `@`.
  - Chạm **1.000.000 dòng** → sheet mới, đủ tiêu đề + đầu bảng + dòng "Số cộng sheet trước chuyển sang"; cuối sheet cũ có
    "Cộng chuyển sang sheet sau" (cộng bằng `Decimal`, không lệch đồng nào).
  - Ngày ký + chức danh + "(Ký, họ tên)" nằm CÙNG 1 dòng (rich string): để 3 dòng riêng thì Excel ngắt trang giữa khối.
  - In: A4 đúng hướng như web, vừa 1 trang ngang, lặp đầu bảng mỗi trang, số trang ở chân.
- **`server.py`**: `POST /api/report_export/start` → job nền (connection riêng) → `/api/export/status` → `/api/export/cancel`.
  - BC005/006/009/010/011: app gửi đúng các dòng ĐANG HIỂN THỊ (không chạy lại truy vấn nặng).
  - BC007/008/012/013: server truy vấn toàn bộ, CÙNG view + CÙNG ORDER BY với màn hình (`LEDGER_VIEW`, `VOUCHER_VIEW`, `VAT_TRANSACTION_VIEW`).
  - Ghi ra `*.part` rồi mới đổi tên; trùng tên tự thêm `(2)`; hủy/lỗi thì xoá sạch file dở.
- **`index.html`**: `ReportExportDialog` thay 4 modal cũ — chọn Excel/CSV, mẫu (BC007: Chi tiết/Tổng hợp/Đầy đủ cột;
  BC013: Chi tiết/Tổng hợp), sửa tên file, tiến trình thật (% · dòng/giây · còn bao lâu · sheet), Hủy, Mở file / Mở thư mục.
  Bộ lọc gửi đi là bản CHỤP lúc nạp dữ liệu; đổi bộ lọc mà chưa bấm Xem thì dialog cảnh báo.

### 8.3 Sửa kèm trên tờ báo cáo (web + file dùng chung `buildReportHeader`)

- BC006 hiện "Mẫu B02 - DN" (là mẫu KQKD) → **Mẫu F01 - DN**; BC011 bỏ mã mẫu.
- BC008 thêm dòng "Tài khoản: …" (trước không biết sổ của tài khoản nào).
- BC013: cột "Tên người **bán**" → "Tên người **mua**" (bảng kê BÁN RA); "hợp phát" → "hợp pháp"; bỏ dấu "-" thừa ở dòng Tài khoản;
  dòng tổng ghi "Tổng cộng" khi chỉ có 1 trang.

### 8.4 Xuất danh sách chứng từ (tab dữ liệu thô) — 4 lỗi sửa kèm

1. **Cột `Decimal` bị ghi thành CHỮ** trong .xlsx (số lượng/đơn giá/thành tiền phiếu nhập, kho, bán hàng): SUM ra 0. Nay là số thật.
2. Xuất lại cùng khoảng ngày **ghi đè** file cũ — file đang mở trong Excel thì job lỗi quyền. Nay tự thêm `(2)`, ghi qua `*.part`.
3. Tách sheet 500 nghìn → **1.000.000** dòng; tiêu đề đậm có nền, cố định dòng tiêu đề, có AutoFilter, cột tự rộng.
4. Modal ghi sai thư mục `Downloads\iPOS_Accounting_Report\` → `Downloads\iPOS_Ledger_Studio\`.

### 8.5 EXE phình 15,8 MB → 43 MB ở bản 1.8.1

Máy build có cài IPython/numpy/matplotlib. PyInstaller lần theo import tuỳ chọn `flask.cli → python-dotenv → dotenv.ipython → IPython`
rồi kéo cả numpy, matplotlib vào EXE. Không liên quan code app. `build_exe.py` nay `--exclude-module` các gói đó
→ **v1.8.2 = 15.838.098 byte**. Build xong nên nhìn dung lượng EXE; tăng vọt thì tra `build/iPOS_Ledger_Studio/xref-*.html`.

### 8.6 Verify đã chạy (M1–M3) — CHƯA có M4

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `node check_babel.js`, `ast.parse` server.py / xlsx_report.py / build_exe.py | Qua |
| M2 | `test_client` + DB giả đếm số `?` = số tham số: 9 báo cáo × xlsx/csv, trùng tên, hủy, BC008 thiếu TK → 400 | 41/41 |
| M2 | Xuất danh sách: Decimal → số, `(2)`, `.part`, tách sheet, hủy | 23/23 |
| M2 | BC007 1.000.051 dòng | 2 sheet, 75 giây, RAM đỉnh 50 MB |
| M2 | Mở file bằng **Excel thật** (COM → PDF), soát hình 9 báo cáo | Đúng form; đã sửa chữ ký bị cắt ở bảng ít cột + khối ký bị ngắt trang |
| M3 | App thật trên Chrome headless (CDP): 4 báo cáo, Enter/Esc, cảnh báo đổi bộ lọc, hủy giữa chừng | 14/14, console không lỗi |
| M3 | Chạy `dist\iPOS_Ledger_Studio.exe` 1.8.2: `/api/version`, `/api/export/dir`, start chưa đăng nhập → 401, BC999 → 400 | Qua |
| **M4** | **Số liệu trong file khớp màn hình trên DB thật** | **Chưa làm — phiên này không kết nối được DB** |

### 8.7 Ghi chú cho lần sau

- Endpoint cũ `/api/report_export_csv`, `/api/export_excel_backend`, `/api/cash_book/export_csv`, `/api/save_export` còn nguyên
  nhưng **không nút nào gọi** nữa. Đừng sửa lỗi ở đó tưởng là đường đang chạy.
- 16/09 Gemini chạy **song song** trên cùng thư mục (sửa `build_exe.py`, thêm import vào `server.py`, build, ghi nhật ký) trong
  lúc Claude đang sửa `server.py`. Lần này không ghi đè mất gì (đã diff từng đoạn), nhưng khi 2 agent cùng làm phải so mtime + diff trước khi bàn giao.

---

## 9. Studio có repo GitHub riêng *(17/09/2026)*

- Repo `https://github.com/trungkhanhduong93/ledgerstudio` — **Public**, chỉ nhánh `main`.
- Push **1 commit gốc mới** chứa code v1.8.2. 7 commit cũ (12/08/2026, chung gốc với LedgerReport) giữ ở nhánh local
  `lich-su-truoc-17-09` để tra cứu — **không push** nhánh này, không `git push --all`.
- `.gitignore` thêm `BaoCaoMau/` và `BESReportViewer.pdf`: báo cáo mẫu chứa dữ liệu thật của khách, chỉ để trên máy.
- EXE (`dist/`) không lên git. Phát hành qua GitHub Releases từ v1.8.3 — xem mục 10.
- Trước mỗi push: `git remote get-url origin` phải ra `.../ledgerstudio.git`, và quét mật khẩu/IP trong file sắp commit.
