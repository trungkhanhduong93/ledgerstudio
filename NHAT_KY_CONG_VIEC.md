# NHẬT KÝ CÔNG VIỆC — LedgerStudio

> Toàn bộ những gì đã làm với **LedgerStudio**, và **vì sao**. Đọc file này trước khi sửa tiếp.
> Kiến trúc và ma trận báo cáo: [CLAUDE.md](CLAUDE.md).
> Phiên gần nhất: **28/09/2026** · EXE build mới nhất: **iPOS_Ledger_Studio v1.10.5** (đã phát hành 28/09, mục 29) — tên hiển thị DataStudio · v1.9.6–1.9.9 do Gemini làm, ghi ở GEMINI.md

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

---

## 10. Tự cập nhật qua GitHub Releases — v1.8.3 *(17/09/2026)*

### 10.1 Làm gì

- Port từ LedgerReport: `/api/check_update`, `/api/apply_update`, `/api/update_progress` (`server.py`, ngay trước `__main__`)
  + `useAutoUpdate` / `AutoUpdateBanner` / `AutoUpdateModal` (`index.html`, hiện ở màn hình đăng nhập và màn hình chính).
- Sửa 5 chỗ so với bản Report:
  1. Kiểm dung lượng + SHA-256 (`digest` GitHub trả kèm asset) **trước** khi thay EXE. Report chỉ kiểm ≥ 5 MB.
  2. Đổi tên lần 2 lỗi → trả EXE cũ về tên cũ. Report để máy mất luôn file app.
  3. Chỉ dọn `<tên exe>.old/.new`. Report xoá **mọi** `*.old/*.new/*.tmp_dl` trong thư mục chứa EXE — EXE để ở Downloads là
     mất file của người dùng. **Lỗi này vẫn còn bên LedgerReport** (Trum dặn không đụng Report).
  4. Chỉ nhận asset đúng tên `iPOS_Ledger_Studio.exe`; Report lấy file `.exe` đầu tiên.
  5. Không tải khi tag không mới hơn bản đang chạy.
- Release đầu tiên `v1.8.3` → commit `fd4626a`, asset `iPOS_Ledger_Studio.exe` 15.850.547 byte + `iPOS_Ledger_Studio.zip`.

### 10.2 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `ast.parse` + `node check_babel.js` | Qua |
| M2 | `test_client` + mô phỏng EXE đóng gói: check_update 7 ca, apply 3 ca, thay file 19 ca (SHA sai, tải thiếu, < 5 MB, tag không mới hơn, sai tên asset, không có digest, đổi tên lỗi, dọn file) | 29/29 |
| M2 | Test xuất báo cáo + xuất danh sách của mục 8 | Vẫn ALL PASS |
| M3 | EXE 1.8.3: `/api/version`; `/api/check_update` khi chưa có release (GitHub 404 → im lặng) | Qua |
| M3 | **Cập nhật thật:** EXE thử v1.8.2 (cùng mã nguồn) chạy ở thư mục tạm → banner "Đã có phiên bản v1.8.3" → bấm bằng Chrome headless → tải 15,1 MB từ GitHub → thay file, đóng cửa sổ cũ, mở bản mới | v1.8.3 lên sau 21 giây (tính từ lúc bấm), PID mới, đúng 1 cửa sổ app, `.old` đã dọn, SHA-256 file = asset GitHub, bản mới `has_update=false` |

### 10.3 Lưu ý

- Máy đang chạy ≤ v1.8.2 chưa có updater → phải tải tay v1.8.3 **một lần**.
- API GitHub không đăng nhập giới hạn 60 lần/giờ mỗi IP. Văn phòng đông máy chung 1 IP mở app liên tục có thể bị chặn tạm → banner không hiện (im lặng).
- EXE để trong thư mục không có quyền ghi (Program Files) → đổi tên thất bại, modal báo lỗi, app cũ vẫn chạy.
- Tên hiển thị "iPOS Accounting Report" (có từ lúc tách khỏi Report) đã đổi thành "iPOS Ledger Studio" ở v1.8.4 — xem 10.4.

### 10.4 v1.8.4 — đổi tên hiển thị + lần tự cập nhật thật đầu tiên giữa 2 bản phát hành

- `index.html`: 10 chỗ "iPOS Accounting Report" → "iPOS Ledger Studio" (`<title>`, 2 meta, `APP_NAME` màn hình đăng nhập, chân 6 tờ báo cáo). `RunReport.bat`: tiêu đề cửa sổ.
- Release `v1.8.4` → commit `37ee151`, asset EXE 15.848.080 byte.
- **Test cập nhật thật:** chạy đúng file EXE của release v1.8.3 (SHA-256 = asset GitHub) → banner "Đã có phiên bản v1.8.4" → bấm → v1.8.4 lên sau 17 giây, thư mục chỉ còn 1 file EXE, SHA-256 = asset v1.8.4, đúng 1 cửa sổ app, màn hình đăng nhập mới ghi "iPOS Ledger Studio V1.8.4", không còn banner.

---

## 11. Vá 4 lỗ bảo mật cấu hình — v1.8.5 *(17/09/2026)*

Rà bảo mật EXE (test tấn công thật): **không có** SQL injection (query tham số hoá, ORDER BY whitelist),
**không** path traversal (`/../..` → 404), `open_file`/`open_folder` chặn ra ngoài thư mục xuất bằng `realpath`,
endpoint dữ liệu đòi phiên. 4 lỗ đều do **để cấu hình mặc định**, đã vá:

| Lỗ | Trước | Sau (v1.8.5) |
|---|---|---|
| Khóa ký cookie | `app.secret_key = 'IACC_SECRET_SUPREME_2026'` ghi cứng, lộ trên repo Public → giả được cookie | `_load_or_create_secret_key()` sinh ngẫu nhiên 32 byte, lưu `Downloads\iPOS_Ledger_Studio\.session_key` (mỗi máy 1 khóa, không lên git). Đổi khóa ⇒ đăng nhập lại 1 lần |
| CORS | `supports_credentials=True` phản chiếu MỌI origin → web lạ đọc được kết quả | `origins=[localhost:5050, 127.0.0.1:5050]` |
| Bind | `0.0.0.0` → cả LAN gọi cổng 5050 được | `127.0.0.1` (cả `app.run` lẫn `_wait_port_free`). Mỗi người chạy EXE máy mình, app tự nói chuyện với máy đó nên không ảnh hưởng ai |
| Hành động nhạy cảm không xác thực | `/api/apply_update`, `/api/install_driver` gọi từ đâu cũng được | `_is_local_request()` chặn origin ngoài localhost. KHÔNG bắt đăng nhập (để nút "Cập nhật ngay" ở màn hình đăng nhập vẫn chạy) |

- **Bối cảnh giảm nhẹ:** SQL Server chỉ vào được qua VPN công ty, nên mật khẩu lộ một mình không đủ khai thác.
- **Cố ý KHÔNG làm:** bỏ mật khẩu khỏi session cookie (Flask ký chứ không mã hoá, password base64 đọc ngược được). Sửa triệt để phải đổi sâu cách giữ phiên + server restart là mất session. Với VPN + khóa đã đổi, rủi ro còn lại chấp nhận được. Nếu sau này cần: giữ `db_config` server-side theo `sid`, cookie chỉ mang `sid`.
- **Chưa làm:** ký số EXE (SmartScreen vẫn cảnh báo "nhà phát hành không rõ"); SHA-256 khi tự cập nhật chỉ chống file hỏng, không chống tài khoản GitHub bị chiếm → bật 2FA cho tài khoản.

### 11.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M2 | 15 ca bảo mật in-process: khóa ngẫu nhiên/bền, CORS chặn evil + cho localhost, `_is_local_request` 4 ca, apply_update/install_driver evil → 403, endpoint dữ liệu vẫn 401, check_update vẫn 200 | 15/15 |
| M2 | `t_update` 29/29, `t_server`/`t_list` ALL PASS (không phá gì) | Qua |
| M3 | EXE 1.8.5: chỉ `LISTEN 127.0.0.1:5050`; gọi qua IP LAN `192.168.1.16:5050` → không kết nối; evil origin → không ACAO / apply_update 403; localhost origin được phép; `.session_key` đã tạo | Qua |
| M3 | Cập nhật thật EXE release v1.8.4 → v1.8.5: 17 giây, 1 file EXE, SHA khớp asset, bản mới bind 127.0.0.1, màn hình đăng nhập lên bình thường | Qua |

---

## 12. Đợt 0 nâng cấp giao diện: EXE dùng bản dịch sẵn — v1.8.6 *(27/09/2026)*

Bối cảnh: Trum chốt nâng giao diện theo hướng "Sổ cái tĩnh" (nền sáng, một màu nhấn xanh iPOS `#0068AC`, Inter 3 độ đậm,
bảng kẻ mảnh), làm theo đợt, **hiệu năng trước**. Đợt 0 chỉ đổi cách đóng gói — màn hình và logic giữ nguyên.

**Nguyên nhân chậm (đo, không đoán):**
- Babel standalone dịch 544 KB JSX **mỗi lần mở app**, với preset mặc định `react + env` (ra ES5): 9,3 s trong Node.
- Tailwind Play CDN (`cdn.tailwindcss.com` 3.4.17) gắn MutationObserver lên toàn trang: mỗi lần virtual scroll thay dòng,
  nó `querySelectorAll("[class]")` quét class cả DOM rồi dịch lại CSS.
- React/Babel/xlsx/font tải từ 5 host ngoài → mất mạng là trắng màn.

**Đã làm:**
- `webbuild/` — `package.json` ghim đúng bản trình duyệt đang dùng; `build.js` ghi `build_web/`: `app.js` (Babel cùng options
  `buildBabelOptions()` của standalone), `app.css` (Tailwind, config đọc từ dòng `tailwind.config = …` trong index.html, chèn cuối
  `<head>` = chỗ bản CDN `document.head.append`), `vendor/` (React 18.3.1, ReactDOM, xlsx 0.18.5 `defer`, font Inter v20 7 subset).
  Thẻ CDN trong index.html lệch mẫu → dừng build. Dọn nội dung `build_web/` chứ không xoá thư mục (terminal đứng trong đó → EPERM).
- `build_exe.py` — gọi build web TRƯỚC khi tăng version; nhúng `build_web/` thay `index.html`; thiếu Node → báo lỗi dừng.
- `server.py` — `vendor/` trả `Cache-Control: public, max-age=31536000, immutable` (tên file có số phiên bản); `mimetypes` thêm `font/woff2`.
- `.gitignore` thêm `build_web/`. `index.html` KHÔNG đổi một byte.

**Cố ý KHÔNG làm:** đổi preset Babel sang cú pháp mới (nguy cơ lỗi TDZ ẩn); lazy-load xlsx theo nút bấm (phải sửa code gọi — dùng
`defer` là đủ); bỏ blur/`transition-all` (đổi hình ảnh → để các đợt giao diện sau).

### 12.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `ast.parse` server.py + build_exe.py; `new Function(app.js)` | OK |
| M2 | test_client đứng trong `build_web/`: `/`, `app.js`, `app.css`, vendor, font → 200; vendor `immutable`, còn lại `no-store`; font `font/woff2`; JS/CSS có gzip | Qua |
| M3 | puppeteer, API giả, so computed style bản nguồn vs `build_web/` trên 5 màn (đăng nhập 42, sổ cái 3.000 dòng 3.043, cuộn giữa bảng 4.830, dropdown Loại CT mở 4.871, tab Báo cáo 636 phần tử × 70 thuộc tính + toạ độ) | **0 khác biệt** |
| M3 | Build EXE thật v1.8.6 (16,4 MB, cũ 15,8 MB): file EXE trả về trùng SHA-1 với `build_web/`; không request ra ngoài; React 18.3.1, không còn Babel/Tailwind runtime, xlsx nạp, 9 font Inter loaded, `/api/version` = 1.8.6 | Qua |
| Đo | Vẽ xong màn đăng nhập, cache ấm: 7,6–9,7 s → 0,14–0,28 s (máy dev); CPU chậm ×4: 36–38 s → 0,5–0,9 s | ~40× |
| Đo | 80 bước cuộn bảng 3.000 dòng: thời gian JS 1.161 → 584 ms (×4: 4.641 → 2.630 ms); tổng khung hình chỉ nhanh ~13% vì layout bảng 34 cột (1,2 s / ×4: 5,1 s) không đổi | Điểm nghẽn kế tiếp: layout bảng |

Chưa verify với DB thật (máy agent không có tài khoản SQL) — màn sau đăng nhập kiểm bằng API giả. Trum mở EXE v1.8.6, đăng nhập
DB thật, xem vài tab + xuất 1 file Excel là đủ M4 cho đợt này (logic không đổi).

**Đợt tiếp theo:** Đợt 1 — token màu/chữ + khung (thanh bên trái, thanh trạng thái, đầu trang). Nhớ sửa CSS `@media print` (đang ẩn
theo vị trí `#root > div > div:first-child`, `.shrink-0`) cùng đợt, và chụp so bản in PDF.

---

## 13. Đợt 1: khung app mới + tên hiển thị DataStudio — v1.8.7 *(27/09/2026)*

Trum chốt: tên hiển thị **DataStudio** (bỏ "Data-Report" vì gần LedgerReport); chỉ đổi phần hiển thị — file EXE, repo,
thư mục xuất giữ tên cũ; giữ logo ô vuông cam; ảnh sóc được đưa lên repo (đợt màn đăng nhập).

**Đã làm (`index.html` trừ khi ghi khác):**
- Thanh bên `AppSidebar`: 7 tab dữ liệu (`DOC_TABS`) + 9 báo cáo (`REPORT_TYPES`, xếp theo mã) + Tải lại danh mục + Đăng xuất;
  thu gọn 56px, nhớ theo máy (`localStorage` bọc try). Không animate bề ngang (bảng 34 cột bên cạnh sẽ reflow từng khung hình).
- `AppPageHeader` (tên + mã/mẫu báo cáo), `AppStatusBar` (kết nối · CSDL · số bản ghi · kỳ · version). Gỡ thanh đen trên cùng
  và `DocumentTabDropdown`.
- `pickReport()`: chọn báo cáo ở thanh bên cùng luật dropdown "Mẫu báo cáo" (có `reportData` mà đổi mẫu → hỏi xác nhận).
- Token: `tailwind.config` thêm `ink/line/canvas/wash/tint/rail/brand/ok/warn/bad`; CSS `ds-*` + biến `--ds-*`. Icon thêm
  `receipt, wallet, shopping-cart, package, panel-left, refresh-cw`; `Icon` nhận `stroke` (mặc định 2.5 như cũ).
- 8 hàng lọc thêm `flex-wrap` — khung mới làm nút "Xuất Excel" tràn mép phải 86 px ở màn 1366–1440 (bản cũ vốn đã tràn 1–36 px).
- CSS in: `#root > div > div:first-child:not(.app-shell)` + ẩn `.app-sidebar, .app-pagehead, .app-statusbar` (Bẫy 15).
- Đổi tên: title/meta/`APP_NAME`/6 chân bảng/hộp thông báo; `manifest.json`; `xlsx_report.py` author/comments;
  `build_exe.py` `DISPLAY_NAME` → FileDescription/ProductName = DataStudio (OriginalFilename vẫn `iPOS_Ledger_Studio.exe`).
- `webbuild/build.js`: đọc khối `tailwind.config` nhiều dòng bằng đếm ngoặc (regex 1 dòng cũ sẽ gãy).

### 13.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `check_babel.js`; build web; `new Function(app.js)` | OK |
| M3 | puppeteer API giả, so nội dung tab bản HEAD (v1.8.6) vs mới — bỏ width/height vì khung hẹp hơn: sổ cái 1.379 phần tử (25 dòng đầu), BC006 201 phần tử | Chỉ lệch lề `auto` căn giữa + vị trí cụm nút xuống dòng; style còn lại **0 khác biệt** |
| M3 | Bản nguồn vs `build_web` (tính cả toạ độ) | BC006 0 khác biệt; sổ cái chỉ lệch tổng chiều cao bảng ảo (bản nguồn đo sai dòng — ghi ở Bẫy 14) |
| M3 | Chức năng: 7 tab + 9 báo cáo từ thanh bên; hộp xác nhận: không dữ liệu → không hỏi, có dữ liệu → hỏi, Hủy giữ BC005, Xác nhận sang BC006; thu gọn 56 px + tải lại vẫn thu; đăng xuất về màn đăng nhập; không lỗi trang | Qua (cả bản nguồn lẫn build) |
| M3 | Bản in (emulate print + `page.pdf`): 2 trang, cùng danh sách phần tử hiện (+2 div bọc), không lọt khung; PDF lệch đúng 8 byte = độ dài tên trong tiêu đề | Qua |
| M3 | Tràn ngang thanh lọc 8 tab × 1366/1440/1920 px × thanh bên mở/thu | Hết tràn (bản cũ tràn ở 1366/1440) |
| M3 | EXE thật 1.8.7 (16,4 MB): file trả về trùng SHA-1 `build_web`; title + h1 đăng nhập "DataStudio"; Properties: FileDescription/ProductName DataStudio, OriginalFilename iPOS_Ledger_Studio.exe; không request ra ngoài | Qua |

Chưa verify với DB thật. Ở màn 1366×768 thanh lọc sổ cái thành 2 dòng, bảng còn ~10 dòng nhìn thấy — Đợt 2 (bộ lọc dạng chip,
nút lên đầu trang) sẽ trả lại 1 dòng.

**Đợt tiếp theo:** Đợt 2 — bộ lọc: chip 32px có nhãn bên trong, gộp Kỳ + ngày, "Bộ lọc khác", nút Truy vấn/Xuất lên đầu trang,
bỏ dropdown "Mẫu báo cáo" trùng thanh bên.

---

## 14. Đợt 2: thanh lọc dạng chip — v1.8.8 *(27/09/2026)*

**Đã làm (`index.html`, chỉ giao diện):**
- CSS `ds-chip / ds-btn / ds-btn-pri / ds-btn-ghost / ds-input / ds-seg / ds-pop / ds-opt / ds-check / ds-cell / ds-meta / ds-badge / ds-slot`.
- 7 component lọc dùng chung đổi phần vẽ, props + handler giữ nguyên: `PeriodDropdown` (+ `from`/`to`, nhãn "Tháng 1/2026",
  "Quý 2/2026", "Năm 2026", "Tùy ý"), `IOSDatePicker` (`if (disabled) return null` đặt sau mọi hook; lịch đổi sang xanh iPOS,
  font Inter), `PremiumDropdown` (nút "Xong" thay "XÁC NHẬN"), `PageSizeDropdown`, `FilterToggleButton`, `IssueReceiveDropdown`,
  `ExportButton`. Gỡ `ReportTypeDropdown` (thanh bên đã thay).
- 8 thanh lọc: bỏ khung bọc bề ngang cố định (`w-64/w-32/w-40` → `ds-slot`), ô Số chứng từ thành `ds-input`, nhóm nút trạng thái
  tab DT chờ phân bổ + Chi tiết/Tổng hợp BC007/BC013 thành `ds-seg`, hàng "Bộ lọc khác" thành `flex-wrap`. Thanh lọc giữ class
  `bg-white border-b` (CSS in ẩn theo cặp này).
- **Cố ý KHÔNG** đưa nút Truy vấn lên đầu trang như dự kiến ban đầu: chip gọn nên hàng lọc đã vừa 1 dòng ở màn 1366 px;
  đưa lên đầu trang phải dùng portal cho 8 tab — rủi ro không đáng.

### 14.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `check_babel.js`, build web | OK |
| M3 | Bấm CÙNG 9 kịch bản lọc trên bản v1.8.7 và v1.8.8 (nguồn + build), so URL API: sổ cái (Loại CT 2 mục, Đơn vị, Tài khoản ở Bộ lọc khác, 1.000 dòng, Quý 2), kỳ Tùy ý chọn ngày 5 → 20, bán hàng gõ số CT + Enter, kho Nhập/Xuất + số CT hàng 2, DT chờ phân bổ 2 nhóm nút, BC012, BC007 Tổng hợp, BC013, BC006 | **9/9 trùng khớp** |
| M3 | PDF gọi `window.print`, Excel mở hộp xuất; không lỗi trang | Qua |
| M3 | Phần dưới thanh lọc: sổ cái 1.285 phần tử, BC006 137 phần tử — v1.8.7 vs v1.8.8 | 0 khác biệt style |
| M3 | Bản in BC006: 2 trang, PDF trùng từng byte (245.784) giữa v1.8.7 / v1.8.8 / build; không chip/nút nào lọt vào | Qua |
| M3 | Tràn ngang 8 tab × 1366/1440/1920 × thanh bên mở/thu | Không tràn; sổ cái 1 dòng ở 1366 |
| M3 | EXE thật 1.8.8: file trùng SHA-1 `build_web`, title DataStudio, không request ra ngoài | Qua |

**Lỗi CÓ SẴN phát hiện khi kiểm (chưa sửa — đợt giao diện không đụng logic):** ô "Số chứng từ" của BC012 gọi
`onToggleFilter('tran_no', e.target.value)` — hàm bật/tắt phần tử MẢNG. Gõ "PC1" thành `['P','PC','P,PC1']` → gửi
`tran_no=P,PC,P,PC1`. Sửa đúng: `setFilters(p => ({ ...p, tran_no: e.target.value }))` — cần Trum duyệt + kiểm server
`/api/cash_book` hiểu `tran_no` là chuỗi. BC013 bấm "Tổng hợp" khi chưa có dữ liệu không gọi API (cả 2 bản như nhau — có thể cố ý).

**Đợt tiếp theo:** Đợt 3 — 6 bảng dữ liệu: đầu cột chữ thường, số mực đen canh phải tabular-nums, Nợ/Có cùng màu, dòng 30 px
(tuỳ chọn 26/36), ghim cột đầu, gom nhóm + tìm theo cột ẩn sau 2 nút icon, bỏ overlay mờ khi tải; xử lý layout bảng khi cuộn.

---

## 15. Đợt 3: bảng dữ liệu + cuộn mượt + sửa BC012 — v1.8.9 *(27/09/2026)*

**Sửa lỗi BC012 (Trum duyệt):** ô "Số chứng từ" gọi `onToggleFilter('tran_no', …)` — hàm bật/tắt phần tử MẢNG — gõ "PC1"
thành `['P','PC','P,PC1']`, gửi `tran_no=P,PC,P,PC1`. Nay `setFilters(p => ({ ...p, tran_no: v }))`. Server `/api/cash_book`
vốn lọc `TRAN_NO LIKE %...%` theo chuỗi. Các tab khác có gửi kèm `tran_no` nhưng server không đọc → không ảnh hưởng.
Kiểm: gõ "PC 0902-01" → gửi đúng chuỗi đó; xoá trắng → gửi rỗng.

**Giao diện bảng (`index.html`):** class `ds-grid` cho 7 bảng + CSS đè kiểu cũ trong ô (xem CLAUDE.md mục 3.0) thay vì sửa
~250 ô của 7 component dòng. Dòng nhóm `ds-grp-0/1`, vùng gom nhóm gọn (viền đứt, chip + nút ×), lớp phủ lúc tải bỏ blur +
vòng quay 48 px → vạch 2 px + nhãn nhỏ (vẫn chặn bấm), chân phân trang gọn, bỏ nhãn tiếng Anh "... Detail View", `PageJumper`
đổi giao diện (dùng chung cả phân trang báo cáo). 5 đầu cột Title Case → chữ thường ("Số chứng từ", "Tên đơn vị",
"Mã đối tượng", "TK ngân hàng", "TK đích").

**Cố ý KHÔNG làm:** ẩn hàng tìm theo cột / vùng gom nhóm sau nút icon (giữ hiện nhưng gọn — ẩn là mất tính năng người dùng
đang quen); ghim cột đầu (dòng nhóm dùng `colSpan` → dính trái lệch); tuỳ chọn mật độ dòng 26/30/36; tô đỏ số âm (cần logic
trong ô). Bảng kho/tồn kho giữ dòng thấp như cũ (~21 px, ô không có padding dọc).

**Hiệu năng cuộn — nguyên nhân đo được:** `useVirtualScroll` gọi trong `App`; mỗi sự kiện cuộn `setScrollTop` → CẢ App vẽ lại.
Đã thử và LOẠI (đo không nhanh hơn): `table-layout: fixed` (chậm hơn ~20%), bỏ blur đầu bảng, `content-visibility` cho `tr`.
Sửa: chỉ đổi state khi cuộn đủ 10 dòng + listener cuộn gắn lại khi khung cuộn đổi (CLAUDE.md Bẫy 16).

### 15.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | `check_babel.js`, build web | OK |
| M3 | Chữ trong 25 dòng đầu + URL API: v1.8.8 vs v1.8.9 (nguồn + build) qua tải, sắp xếp "Số chứng từ" 2 lần, tìm cột Diễn giải "số 12", gom nhóm theo Tài khoản (kéo-thả giả lập), thu nhóm | **5/5 trùng**, API trùng, không lỗi trang |
| M3 | Độ phủ bảng ảo: cuộn đều xuống 17 px/bước, lên 23 px/bước, 8 lần nhảy xa, chạm đáy, về đầu — 932 khung | 0 lần hở (build chạy 8 lần, 1 lần hở trước khi sửa gắn listener, sau đó 5/5 đạt); đáy = dòng 3.000 |
| M3 | Đổi tab rồi quay lại sổ cái, cuộn tới 30.000 px | 3/3 đạt (cả bản cũ) |
| Đo | Cuộn touchpad 600 bước × 20 px, cùng bản nguồn: JS 5.708 → 649 ms, layout 3.797 → 476 ms; CPU ×4: 74 s → 12,4 s, khung giật 599 → 78/600. EXE: máy thường 0/600 khung giật | ~6–10× |
| M3 | BC006 dưới thanh lọc 0 khác biệt; PDF BC006 trùng từng byte v1.8.7/8/9 | Qua |
| M3 | EXE thật 1.8.9: file trùng SHA-1 `build_web`, không request ra ngoài, title DataStudio | Qua |

Chưa verify với DB thật.

**Đợt tiếp theo:** Đợt 4 — khung báo cáo (nền canvas, thanh zoom, các thanh phân trang/tổng trong khu báo cáo; nội dung tờ
A4 KHÔNG đụng), rồi hộp thoại (xuất Excel, thông báo), cuối cùng màn đăng nhập DataStudio + sóc.

## 16. Đợt 4: khung báo cáo + zoom — v1.9.0 *(27/09/2026)*

**Làm gì (`index.html`, chỉ khung quanh tờ A4):**
- Nền khu báo cáo `bg-slate-200 p-4` → `ds-desk` (#E9EDF2, `scrollbar-gutter: stable`). Tờ `.report-paper`: lề 30 → 20px,
  bóng `0 20px 60px` → bóng nhẹ, viền mảnh, bỏ `transition: all 0.3s cubic-bezier(…1.56…)` (kiểu nảy, animate cả bề ngang).
- Component mới `ReportBar` = thanh dưới (`.app-reportbar`, kiểu `ds-pager` như bảng dữ liệu): trái `PageJumper` + số dòng +
  "A4 ngang/dọc"; phải lên đầu · xuống cuối · − % + · "Vừa khung". Gỡ 2 nút tròn `fixed bottom-10 right-10` và viên phân
  trang `fixed left-1/2` (canh giữa CỬA SỔ nên lệch sang phải phần báo cáo khi có thanh bên 216px; nổi trên lớp đang tải
  nên bấm được trong lúc tải). Số dòng giờ hiện cả khi chỉ 1 trang, BC012 cũng có (trước chỉ BC007/008/013 khi >1 trang).
- Zoom: `transform: scale` + khung `.ds-papersizer` (CLAUDE.md Bẫy 17). Mức 50/67/75/80/90/100/110/125/150%, bấm số % về
  100%, "Vừa khung" mặc định (chỉ thu nhỏ, không phóng quá 100%). Nhớ qua `localStorage['ds_report_zoom']`.
- Lớp "Đang kết xuất báo cáo" ở `App` (phủ cả thanh lọc, blur 4px, hộp tròn 40px bo) → `ds-loading` trong ReportTab, dưới
  thanh lọc: vạch 2px + nhãn nhỏ, vẫn chặn bấm tờ + thanh dưới. Thanh lọc (z-900) vẫn bấm được như trước.
- Sửa lỗi hình có từ bản đầu: icon `chevron-right` = `m9 18 6-6 6-6` (đường chéo "⁄") → `m9 18 6-6-6-6`. Ảnh hưởng nút
  Trang sau của mọi bảng + báo cáo, nút tháng sau trong lịch.

**Đã thử và LOẠI:** CSS `zoom` (đơn giản hơn, nhưng BC012 10.000 dòng mất 4,3–5 s mỗi lần bấm vì tính lại style + layout
90.000 ô; `content-visibility` trên `tr` không cứu được vì dòng bảng không nhận layout containment).

### 16.1 Verify (API giả, puppeteer, build v1.8.9 vs build v1.9.0)

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | build web (Babel 7.29.7 + Tailwind) | OK |
| M3 | Nội dung tờ: computed style + vị trí tương đối so với tờ, BC006 (124 phần tử) + BC007 1.000 dòng (763 phần tử, 60 dòng đầu), 1440 px | **0 khác biệt** |
| M3 | URL API BC007 tải + bấm Trang sau | Trùng (`page=1`, `page=2`) |
| M3 | Bản in BC006 (`emulateMediaType('print')` + `page.pdf`): v1.8.9 / v1.9.0 / v1.9.0 đang zoom 75% | 2 trang; luồng nội dung giải nén trùng cả 3 (khác giờ tạo + 1 nút cấu trúc cho thẻ bọc) |
| M3 | 1366 px, thanh bên mở, BC006 ngang | "Vừa khung" 98%, tờ 1100 px, cuộn ngang 0 (v1.8.9: 5 px) |
| M3 | + → 100%, − − → 80%, tải lại trang → vẫn 80%; "Vừa khung" → 98%; thu thanh bên → 100%, mở lại → 98%; sang BC005 (dọc) → 100% | Đúng cả |
| M3 | Khoảng trắng dưới tờ khi thu nhỏ (80%, 98%) | 20–21 px = lề dưới, không dư |
| M3 | Xuống cuối / Lên đầu (BC007 1.000 dòng) | 34.016/34.017 px → 0 |
| M3 | Lớp đang tải (API trả chậm 1,5 s) | Vạch 2px ngay dưới thanh lọc (87 = 87 px), nhãn hiện, thanh dưới bị chặn, không blur, tắt khi xong |
| Đo | Bấm zoom trên BC012 10.000 dòng/trang | CSS zoom 4,3–5 s → scale 0,8–1,1 s |
| Đo | Nạp BC012 10.000 dòng, 3 vòng luân phiên | Trung vị: v1.8.9 5,30 s (1366) / 5,30 s (1440); v1.9.0 5,50 s (98%) / 5,36 s (100%) / 5,42 s (1440) — trong mức nhiễu |
| M3 | Bảng dữ liệu sổ cái (tải/sắp xếp/tìm cột/gom nhóm/thu nhóm) v1.8.9 vs v1.9.0 | 5/5 trùng, API trùng |
| M3 | EXE thật 1.9.0: `/api/version` = 1.9.0, `app.js` trùng SHA-1 `build_web`, không request ra ngoài, màn đăng nhập 246–671 ms | Qua |

Chưa verify với DB thật. Lỗi 401 ở `/api/metadata` trước khi đăng nhập là bình thường (có từ trước).

**Đợt tiếp theo:** hộp thoại (xuất Excel `ReportExportDialog`, thông báo, xác nhận chuyển mẫu), rồi màn đăng nhập DataStudio + sóc.

## 17. Đợt 5: hộp thoại — v1.9.1 *(27/09/2026)*

**Làm gì (`index.html`):** CSS khung hộp thoại dùng chung (CLAUDE.md mục 3.0) rồi làm lại từng hộp, props/handler giữ nguyên
(đoạn onClick dài của hộp cài driver và hộp chuyển mẫu được CẮT từ khối cũ bằng script rồi dán lại, không gõ lại).

| Hộp thoại | Trước | Sau |
|---|---|---|
| Xuất báo cáo `ReportExportDialog` | bo 28px, đầu gradient lục, vòng tròn % + thanh sọc chạy, nút lục/trời/chàm, chữ IN HOA | khung 580px, thẻ chọn `ds-choice`, số % + thanh 6px, các bước chấm tròn, 3 ô số liệu, nút chính xanh iPOS |
| Đang xuất / Đã xuất (tab dữ liệu) | vòng quay 48px; thanh 100% giả trang trí | icon quay nhỏ + thanh thật; bỏ thanh 100% giả, giữ đường dẫn; icon "Mở folder" đúng (trước là icon file) |
| Menu Xuất Excel (tab dữ liệu) | ô màu XLSX/CSV/ORG, chữ đậm | dòng menu `ds-menuitem` + nhãn `ds-fmt` |
| Chuyển mẫu báo cáo | bo 32px, nền kính mờ, nút IN HOA | hộp cảnh báo nhỏ, Hủy / Xác nhận |
| Thông báo `showNotice` | + dòng phụ "Hệ thống DataStudio" | bỏ dòng phụ; bấm nền vẫn đóng |
| Cập nhật (đang tải / lỗi) | icon nhảy, thanh cam→chàm, ô xanh nhấp nháy | thanh xanh iPOS (xong: xanh lục), ghi chú tĩnh |
| Banner bản mới | gradient cam→chàm, chấm ping | nền xanh nhạt, nút Cập nhật ngay |
| Cài ODBC driver (màn đăng nhập) | 2 nút xếp dọc full ngang | chân hộp: Bỏ qua · Cài đặt driver ngay |
| Mất kết nối (script thường) | nền tối 92% + emoji ⚠️ + chữ IN HOA | hộp trắng giống các hộp khác, style inline (chạy trước React/Tailwind) |

**Cố ý KHÔNG làm:** 2 hộp chết (`exportConfirm`, `exportNoticeModal`) — để nguyên, ghi vào CLAUDE.md Bẫy 18. Tách state mở
hộp xuất khỏi ReportTab để khỏi vẽ lại tờ (~0,45 s trên BC012 10.000 dòng) — sẽ làm file xuất lấy snapshot bộ lọc cũ (Bẫy 18).
`alert()` gốc trình duyệt (lỗi xuất, cài driver) — đổi là đụng luồng xử lý. Chữ "Đang xuất Excel" cả khi chọn CSV — giữ chữ cũ.

**Build:** `webbuild/build.js` ghim Babel `compact: true` (CLAUDE.md Bẫy 18) — app.js 438 KB.

### 17.1 Verify (API giả, puppeteer, build v1.9.0 vs build v1.9.1)

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | build web | OK |
| M3 | Xuất BC006: mở → CSV → Excel → Enter → đang ghi → xong → Mở file | Body `/api/report_export/start` + `/api/open_file` + chuỗi poll **trùng** |
| M3 | Xuất lỗi → Thử lại → xuất → Hủy xuất → đã hủy → Esc | API trùng (kể cả `/api/export/cancel`), trạng thái trùng |
| M3 | BC007 chọn mẫu Tổng hợp → tên file `…_TongHop_…` | Trùng |
| M3 | Tab sổ cái: menu Xuất Excel (3 dòng, chữ trùng) → XLSX → đang xuất → đã xuất → Mở folder → Đóng | API trùng (count, stream_csv, 3 lần poll, open_folder) |
| M3 | Chuyển mẫu BC005 (có dữ liệu) → BC006: Hủy giữ BC005, Xác nhận sang BC006 | Trùng |
| M3 | Thông báo BC008 thiếu TK: Đã hiểu đóng; bấm nền đóng | Trùng |
| M3 | Cập nhật: banner → Cập nhật ngay → 42% (6,9/16,5 MB) → lỗi → Đóng | `/api/apply_update` trùng, trạng thái trùng |
| M3 | Màn đăng nhập thiếu driver → Cài đặt (lỗi, alert) → vẫn mở → Bỏ qua | `/api/install_driver` + nội dung alert trùng |
| M3 | Màn Mất kết nối | Chữ giữ nguyên (trừ tiêu đề thường hoá), nút Thử lại |
| Đo | Mở hộp xuất trên BC012 10.000 dòng | 0,49–0,55 s → 0,44–0,47 s (phần lớn là vẽ lại tờ — Bẫy 18) |
| Đo | Khung hình 3 s lúc hộp xuất đang chạy trên BC012 | Cả hai bản 0 khung giật (headless) — bỏ blur không tạo khác biệt đo được ở đây |
| M3 | Tờ báo cáo BC006 + BC007 so v1.8.9; PDF BC006 (kể cả zoom 75%); bảng sổ cái 5 thao tác | 0 khác biệt / trùng / 5/5 trùng |
| M3 | EXE thật 1.9.1: `/api/version`, `app.js` trùng SHA-1 `build_web`, không request ra ngoài | Qua |

Chưa verify với DB thật.

**Dọn sau Đợt 5 (27/09/2026, có trong EXE 1.9.2):** xoá 2 hộp thoại chết `exportConfirm` ("Xuất dữ liệu lớn") và `exportNoticeModal` ("Xuất Excel thành công!" ở màn đăng nhập) + state + prop `onExportSuccess` của ReportTab. Kiểm: build web qua; bộ kiểm hộp thoại (xuất báo cáo, lỗi/hủy, xuất tab dữ liệu, chuyển mẫu, thông báo, cập nhật, driver) 39/39 mục + API 5 luồng trùng bản trước khi xoá. app.js 438 → 431 KB.

**Đợt tiếp theo (cuối):** màn đăng nhập DataStudio — chia đôi, trái nền giấy sổ cái + sóc (ảnh đã tách nền), phải form.

## 18. Đợt 6 (cuối): màn đăng nhập — v1.9.2 *(27/09/2026)*

**Làm gì:** màn đăng nhập theo mockup đã duyệt (`Desktop\IVT\present IVT\SOC\DataReport-mockup.html`, bấm "Đăng nhập"),
đổi tên Data-Report → DataStudio, "6 phân hệ" → số thật từ `DOC_TABS` (7), "9 báo cáo TT200" → "9 báo cáo kế toán" (BC011–BC013
không phải mẫu TT200), "Chứng từ tháng 9" → "Chứng từ trong kỳ". Bỏ dòng "ODBC Driver 17 for SQL Server" dưới nút (mockup có):
app không biết driver nào sẽ dùng — `loginData.driver` luôn là `"SQL Server"`, hiện tên driver khác là nói sai.
- `index.html`: CSS `ds-login-*`, 5 icon mới, state `showPw`, JSX màn đăng nhập (khối hộp cài driver cắt từ bản cũ dán lại).
  Gỡ CSS `.glass-login`, `.login-input` (kính mờ blur 20px) không còn ai dùng.
- `assets/soc-it.webp` (77 KB, lên repo Public theo Trum duyệt 27/09), `webbuild/build.js`, `build_exe.py`, `server.py` — Bẫy 19.

**Ảnh sóc — cách tạo lại (bóng đổ vẽ sẵn):**
```python
from PIL import Image, ImageFilter
png = Image.open(r'...\SOC\soc IT - tach nen.png').convert('RGBA')
src = png.resize((900, round(png.height * 900 / png.width)), Image.LANCZOS)   # 900×1292
W, H = src.size; s = 505 / H; off = round(18 / s); sigma = 11 / s            # = drop-shadow(0 18px 22px) ở cỡ 505px
PX, PT = 84, 40
canvas = Image.new('RGBA', (W + 2 * PX, H + PT), (0, 0, 0, 0))
sh = Image.new('L', canvas.size, 0); sh.paste(src.getchannel('A'), (PX, PT + off))
sh = sh.filter(ImageFilter.GaussianBlur(sigma)).point(lambda v: int(v * 0.18))
shadow = Image.new('RGBA', canvas.size, (13, 48, 80, 0)); shadow.putalpha(sh)
canvas = Image.alpha_composite(canvas, shadow); canvas.alpha_composite(src, (PX, PT))
canvas.save('assets/soc-it.webp', 'WEBP', quality=80, method=6)
```

### 18.1 Verify (API giả, puppeteer)

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | build web; `python -c "import server"` + test_client `GET /assets/soc-it.webp` | OK · 200 `image/webp` 77 KB |
| M3 | v1.9.1 vs v1.9.2 vs bản nguồn CDN: 4 ô (giá trị nhớ từ localStorage, type, required, placeholder), gõ mật khẩu sai → lỗi 18456 hiện trong form, sửa → Kết nối → vào app, body 2 lần `/api/login`, localStorage sau đăng nhập, lỗi trang | **Trùng cả 6 mục** |
| M3 | Nút con mắt: hiện → `text`, ẩn → `password`, focus vẫn ở ô mật khẩu | Đúng |
| M3 | 1366×697 · 1440×900 · 1920×1009 · 820×700 | Không cuộn ngang, form vừa màn, thẻ số liệu không đè chữ; 820 ẩn nửa trái |
| M3 | Banner bản mới trên màn đăng nhập → Cập nhật ngay | `/api/apply_update`, hộp cập nhật hiện |
| M3 | Thiếu driver → hộp cài driver | Hiện đúng |
| M3 | Hộp thoại (9 luồng Đợt 5) v1.9.1 vs v1.9.2 | 39/39 trùng, API trùng |
| Đo | FCP màn đăng nhập (headless, 8 vòng luân phiên, bỏ vòng đầu): v1.9.1 276–280 · có `drop-shadow` 344 · bỏ filter 308 · bóng vẽ sẵn 324 · bỏ cả nửa trái 308 ms | Nửa trái còn tốn ~16 ms |
| M3 | EXE thật 1.9.2: `/api/version`, `/assets/soc-it.webp` 200 `image/webp`, ảnh `complete` 1068×1332, `app.js` trùng SHA-1, không request ra ngoài, vẽ màn 188–269 ms (sau lần mở đầu) | Qua |

Chưa verify với DB thật (đăng nhập thật, driver thật trên máy khách).

## 19. Phát hành v1.9.2 + test cập nhật thật từ v1.8.5 *(27/09/2026)*

**QA trước push (skill pre-push-qa):** phán quyết 🟡 VÀNG — không phát hiện lỗi; vàng vì chưa kiểm với DB thật. Đã rà: diff
14 file (server.py chỉ thêm kiểu `.webp`, updater không đổi); 15 handler cũ không còn nguyên văn đều là phần cố ý gỡ/thay (dropdown
mẫu báo cáo/tab → thanh bên, nút tròn nổi → thanh dưới, ô Số chứng từ BC012 đã sửa, 2 hộp chết); không có hook sau `return` sớm
(App, IOSDatePicker); quét secret: không IP, chuỗi kết nối, token (khớp duy nhất là handler `password: e.target.value`); EXE build
sau lần sửa source cuối. Chạy lại cả bộ kiểm trên bản build cuối: bảng 5/5, tờ báo cáo 0 khác biệt, PDF trùng, hộp thoại 39/39,
đăng nhập 6/6, py_compile + test_client OK.

**Phát hành:** commit `f2f887c` push `main` → `gh release create v1.9.2` (tiêu đề "DataStudio v1.9.2 (iPOS Ledger Studio)"),
asset `iPOS_Ledger_Studio.exe` 16.525.495 byte + `.zip` tạo lại từ EXE mới (zip trong `dist/` còn là bản v1.8.5 — CLAUDE.md Bước 5).
API công khai `releases/latest` trả `v1.9.2`, digest exe = SHA-256 file đã build.

**Test cập nhật thật (máy khách giả lập):** tải đúng EXE release v1.8.5 (digest khớp GitHub) vào thư mục tạm → chạy → `/api/check_update`:
`has_update=true, latest=v1.9.2` → bấm "Cập nhật ngay" trên giao diện v1.8.5 (puppeteer) → tải 0 → 100% trong 12 s → server cũ thoát
→ bản mới lên, `/api/version` = 1.9.2 sau 33 s kể từ lúc bấm → thư mục chỉ còn 1 file `iPOS_Ledger_Studio.exe` (`.old` đã tự dọn),
SHA-256 = asset v1.9.2; trang chủ title DataStudio, ảnh sóc 200. Máy 1.8.3/1.8.4 dùng cùng updater (không đổi từ 1.8.3) nên cùng kết quả;
máy ≤ 1.8.2 phải tải tay.

Chưa làm: kiểm với DB thật sau cập nhật (đăng nhập thật, xem báo cáo thật).

## 20. v1.9.3: tốc độ tab sổ cái + bộ lọc nâng cao *(27/09/2026)*

**Trum báo:** truy vấn ~2 triệu dòng mất gần 15 giây. Trả lời theo mặc định Trum duyệt: màn = tab sổ cái; trước giờ vẫn chậm;
làm đo + song song + OFFSET trong 1 bản; không tạo index.

**Đo trước khi sửa (API giả, 0 ms SQL):** sổ cái 10.000 dòng — trình duyệt đọc JSON 0,1 s + vẽ 0,2 s (bản 1.9.2 nhanh hơn 1.8.6:
0,83–0,86 s so với 1,03–1,23 s tính cả phần giả lập); trang BC007 1.000 dòng vẽ 0,75 s. → 15 s nằm ở server/SQL.

**Sửa (`server.py` `get_ledger` + pool, `index.html` `loadData` sổ cái + thanh trạng thái):** xem CLAUDE.md Bẫy 20.

**Thử dựng DB 2,5 triệu dòng để đo — LOẠI:** tạo `LS_PERF_TEST` trên SQL Express máy dev (nhân `TRUNGDEMO.dbo.LEDGER` × 170),
kẹt ở tạo khoá chính: chờ cấp bộ nhớ `RESOURCE_SEMAPHORE` 19 phút — máy chỉ còn 0,4–1,1 GB RAM trống (13,8 GB), SQL tự co còn
132 MB. Đã dừng và xoá DB (SQL Express còn đúng 6 DB như trước).

**Bộ lọc nâng cao (Trum gửi hình mẫu giữa chừng):** `FilterConfigurator` + CSS `ds-afp-*`, `ds-switch`; script tách ô lọc cũ của
7 tab (hàng chính sau ô ngày + hàng "Bộ lọc khác") thành `items`, gỡ `FilterToggleButton`, `filtersExpanded`, 7 `*Row2Count`.

### 20.1 Verify

| Mức | Kiểm | Kết quả |
|---|---|---|
| M1 | py_compile server.py; build web | OK |
| M3 SQL thật | SQL Server 2016 Express, DB demo TRUNGDEMO (compat 100), CHỈ SELECT, 2024–2026 = 176 dòng; so bản mới với `server.py` HEAD (1.9.2) qua test_client, vá `_make_conn` sang Windows auth | **8/8 nhóm đạt** |
| | 1 trang chứa hết: tổng dòng, tổng Nợ/Có, tập dòng, thứ tự TRAN_DATE DESC + TRAN_NO; mode `offset+parallel` | trùng |
| | Phân trang 50 dòng × 4 trang: chuỗi khoá từng trang + hợp 4 trang | trùng |
| | Gửi known_total ở trang 1 + sắp xếp AMOUNT desc | không đếm lại, tổng đúng số gửi, chuỗi số tiền trùng |
| | Tìm theo tên đối tượng (nhánh JOIN); lọc TK 1* | trùng |
| | Không mở được kết nối phụ / kết nối phụ lỗi giữa chừng | tự đếm tuần tự, bỏ kết nối hỏng, tổng đúng |
| | gzip ghi `gzip;dur`; đăng xuất đóng kết nối phụ (1 → 0); giả SQL 2008 → `rownum` | đúng |
| M3 giao diện | Panel lọc sổ cái 1366px: lưới 6 ô, cấu hình 8 dòng, chọn TK trong panel → badge 1, bật 2 ô → 4 ô ngoài + 4 công tắc khoá, kéo "Đơn vị" lên đầu → thanh lọc đổi thứ tự, tải lại trang vẫn giữ, Xoá tất cả 1 → 0, Esc / bấm ngoài đóng, Lọc gửi `acc_ids=111` không kèm known_total | đạt |
| | 7 tab: số ô lưới/cấu hình 6/8 · 6/8 · 5/7 · 6/8 · 8/10 · 6/8 · 3/4, panel nằm trong màn | đạt, không lỗi trang |
| | Sắp xếp → gửi known_total; Truy vấn → không; Trang sau → gửi | đúng |
| | Thanh trạng thái (Server-Timing giả 6,1 s đếm ‖ 7,2 s trang) | "SQL 7,2 s" (lấy khâu lâu hơn), tooltip đủ khâu |
| M3 hồi quy | Bảng sổ cái 5 thao tác vs Đợt 3: dữ liệu trùng; URL trùng khi bỏ `known_*` (khác duy nhất: sắp xếp giờ gửi kèm tổng cũ) · hộp thoại 39/39 · đăng nhập 6/6 · tờ báo cáo 0 khác biệt | đạt |
| M3 EXE | 1.9.3: `/api/version`, app.js trùng SHA-1 build_web, `/api/ledger` chưa đăng nhập vẫn 401 | đạt |

**Chưa làm được:** đo tốc độ trên DB thật 2 triệu dòng — chờ Trum chạy 1.9.3 và gửi số ở thanh trạng thái (rê chuột để xem đủ).

## 21. Phát hành v1.9.3 + test cập nhật thật từ v1.9.2 *(27/09/2026)*

**QA trước push (skill pre-push-qa):** 🟡 VÀNG — không phát hiện lỗi; vàng vì chưa đo tốc độ trên DB thật. Rà: `get_connection`
giữ chữ ký, `close_pool_for` đóng thêm kết nối phụ; tham số `OFFSET ? … FETCH NEXT ?` đúng thứ tự `[offset, page_size]`; luồng
đếm không đọc `session` (count_sql/count_params chụp sẵn); `countKey` tính TRƯỚC khi gắn `order_by` → sắp xếp vẫn dùng lại tổng;
hook mới trong App nằm trước `return` sớm; `page < 1` không xảy ra (PageJumper kẹp ≥ 1; `page_size = 0` bản cũ cũng lỗi chia 0).
Quét secret: không IP, mật khẩu, token. EXE (18:07) build sau lần sửa source cuối (18:00). Chạy lại `t_ledger.py` trên SQL thật: 8/8.

**Phát hành:** commit `091f7cf` push `main` → `gh release create v1.9.3`, asset `iPOS_Ledger_Studio.exe` 16.532.842 byte + `.zip`
tạo lại từ EXE mới. API công khai `releases/latest` trả `v1.9.3`, digest exe = SHA-256 file đã build.

**Test cập nhật thật:** tải EXE release v1.9.2 (digest khớp GitHub) vào thư mục tạm → chạy → `/api/check_update`: `has_update=true,
latest=v1.9.3` → bấm "Cập nhật ngay" trên giao diện v1.9.2 (puppeteer) → tải 0 → 100% trong 8 s → server cũ thoát → `/api/version`
= 1.9.3 sau 16 s kể từ lúc bấm → thư mục còn 1 file `iPOS_Ledger_Studio.exe`, SHA-256 = asset v1.9.3; trang chủ title DataStudio,
`/api/ledger` chưa đăng nhập 401, `check_update` hết báo bản mới. Đã tắt EXE test + cửa sổ app của nó.

**Commit lỗi (PowerShell 5.1):** `git commit -m @'…'@` có dấu `"` trong message → PowerShell tách thành nhiều đối số, git báo
`pathspec … did not match`, KHÔNG commit. Viết message ra file rồi `git commit -F <file>`.

## 22. v1.9.4: kéo thanh cuộn mượt + tiêu đề bảng lọt chữ + cột mã dropdown *(27/09/2026)*

**Trum báo (sau khi dùng 1.9.3):** (1) cuộn thấy khe hở giữa hàng tiêu đề và hàng lọc của bảng; (2) truy vấn nhanh hơn rồi nhưng
lướt nhiều dòng giật, nhất là kéo thanh cuộn — không theo kịp chuột; (3) dropdown "Loại CT" không thẳng cột mã / tên.

**Nguyên nhân + sửa:** CLAUDE.md Bẫy 16 (mục kéo thanh cuộn) và Bẫy 22.
- (1) Chrome vẽ sai `thead` dính khi bảng dùng viền gộp → chữ dòng dưới lọt lên hàng ô tìm. Chuyển 7 bảng sang viền tách.
- (2) Mỗi khung hình kéo thanh cuộn vẽ lại ~130 dòng × 34 cột + cả App, và vẽ sau khi khung hình đã hiện. Tách `VirtualRows`,
  chế độ kéo nhanh (overscan 8 + `flushSync` + dùng lại `<tr>`), giữ sẵn `Intl.NumberFormat`.
- (3) Ô mã chỉ có `min-width: 34px` → đo mã dài nhất, đặt chung bề rộng.

### 22.1 Verify (API giả, headless, 1366×768)

| Kiểm | Trước (1.9.3) | Sau |
|---|---|---|
| Kéo 10.000 dòng 1.500 px/khung, CPU ×1 (`drag.js`) | 89 ms/khung, 10–12 khung hở | 16 ms/khung, 0 khung hở |
| Như trên, 6.000 px/khung | 134 ms, 104/104 khung hở | 15 ms, 0 |
| CPU ×4, 1.500 / 6.000 px/khung | 286 / 336 ms | 78 / 68 ms |
| Mỗi khung khi kéo: dòng đầu nhìn thấy đúng số thứ tự + Số CT, dãy liên tục (`verify8.js`) | 218/221 khung không có dòng | 221/221 đúng; dừng 150 ms → về 121 dòng |
| Cuộn con lăn 600 × 20 px (`wheel8.js`) CPU ×1 / ×4: JS | 268 / 1.020 ms, giật ×4: 72/600 | 168 / 638 ms, giật ×4: 24/600 |
| Chụp đầu bảng khi cuộn 333 px (`gap2.js`, `verify8.js`) | chữ dòng 11 lọt lên hàng ô tìm | kín |
| 7 bảng chưa cuộn (`tables8.js`): toạ độ cột, cao dòng/tiêu đề, chữ 25 dòng | — | trùng (cột cuối tab tiền −0,5 px, chân bảng +0,5 px) |
| Dropdown Loại CT 8 mã dài ngắn (PC … PXKDC): vị trí chữ tên | 2 vị trí | 1 vị trí, không mã nào bị cắt; gõ tìm vẫn thẳng |
| Tải / sắp xếp / tìm theo cột / gom nhóm / thu nhóm (`verify3d.js`) + URL API | — | khớp 5/5, API trùng |
| Kéo nhanh khi gom nhóm theo TK (`dgroup8.js`) | — | về đầu giống trước khi kéo, thu nhóm đúng, không lỗi |
| Panel lọc nâng cao (`verify7.js`), bản nguồn CDN (`verify8.js after`) | — | đạt như cũ; bản nguồn đạt cả 3 mục |
| EXE 1.9.4: `/api/version`, app.js phục vụ = build_web (SHA-256), có `VirtualRows`/`flushSync`/`--ds-code-w`, `/api/ledger` chưa đăng nhập 401 | — | đạt |

Viền tách không làm nhanh/chậm hơn (đo riêng: trong mức nhiễu). Chưa đo trên máy Trum với dữ liệu thật.

### 22.2 Phát hành + test cập nhật thật từ v1.9.3

**QA trước push:** 🟢 — diff đúng phạm vi 3 lỗi Trum báo, không secret/debug. Trước khi commit sửa ngày ghi nhầm "28/09/2026" trong
4 comment → build lại EXE (đặt tạm `version.txt` = 1.9.3 để `build_exe.py` tăng đúng lên 1.9.4, không đốt 1.9.5); chạy lại
`verify8.js` trên bản build cuối (dropdown 1 vị trí, kéo 221/221 khung đúng) + EXE phục vụ đúng app.js, `/api/ledger` 401.

**Phát hành:** commit `71e8295` push `main` → `gh release create v1.9.4`, asset `iPOS_Ledger_Studio.exe` 16.532.666 byte + `.zip`
tạo lại từ EXE mới. API công khai `releases/latest` trả `v1.9.4`, digest exe/zip = SHA-256 file local.

**Test cập nhật thật:** EXE release v1.9.3 (SHA khớp asset) → `check_update`: có v1.9.4 → bấm "Cập nhật ngay" trên giao diện
v1.9.3 → tải 100% trong 8 s → bản 1.9.4 lên sau 16 s kể từ lúc bấm → thư mục còn 1 file, SHA = asset v1.9.4, hết báo bản mới,
`/api/ledger` chưa đăng nhập 401. Đã tắt EXE test + cửa sổ app.

---

## 23. v1.9.5: đăng nhập báo bật VPN + chờ tối đa 8 s + bỏ tên Thông tư 200 *(27/09/2026)*

**Yêu cầu Trum:** đăng nhập báo `08001 … [DBNETLIB] SQL Server does not exist or access denied … ConnectionOpen (Connect())` là do
chưa bật VPN công ty → dịch ra, bảo người dùng bật VPN; rút thời gian chờ; bỏ chữ "Thông tư 200", ghi "thông tư mới nhất".

**Đã sửa (`server.py`, `index.html`):**
- `_login_error_message`: 08001 / HYT00 / quá giờ chờ → *Không kết nối được máy chủ "X" — máy chưa vào mạng công ty. Hãy bật VPN
  công ty rồi đăng nhập lại. Đã bật VPN mà vẫn lỗi thì kiểm tra lại tên máy chủ.* Lỗi khác giữ nguyên văn. Loại 08001 có chữ `SSL`
  (ODBC Driver 18 báo lỗi chứng chỉ cùng mã).
- `_make_conn_capped` (chỉ `/api/login` dùng): driver "SQL Server" bỏ qua `timeout=5` → nối trong luồng riêng, `join(8)`, quá giờ
  thì `TimeoutError`; luồng chạy nốt, lỡ nối được thì tự `close()`. 5 chỗ khác gọi `_make_conn` giữ nguyên.
- Màn đăng nhập: "lập báo cáo theo Thông tư 200." → "… theo thông tư mới nhất.". Đây là chỗ DUY NHẤT người dùng thấy tên thông tư;
  còn 3 comment code (server.py BC005/BC009, index.html mã mẫu F01) + `temp.jsx` (file cũ không dùng) — giữ nguyên.

**Verify (driver "SQL Server", test_client + EXE 1.9.5):**

| Ca | Trước | Sau |
|---|---|---|
| Tên máy chủ sai (DNS) | 11,2 s, lỗi ODBC tiếng Anh | 8,0 s, câu bật VPN |
| IP không tới được (IP nội bộ giả) | 47,7 s, lỗi ODBC | 8,0 s (EXE qua giao diện: 8,1 s), câu bật VPN |
| Sai mật khẩu (`localhost\SQLEXPRESS`) | 28000 nguyên văn | giữ nguyên, 0,0 s |
| Đăng nhập đúng (vá Windows auth) | — | HTTP 200, `/api/metadata` 200 |
| Kết nối tới muộn (giả lập 1,5 s, chờ 0,5 s) | — | `TimeoutError` sau 0,5 s, kết nối muộn `closed = True` |

**Phát hành:** QA 🟢 (không IP/mật khẩu trong diff). Build lại với `version.txt` đặt tạm 1.9.4 → EXE 1.9.5 16.536.251 byte.
Commit `8235ccd` push `main` → `gh release create v1.9.5` (+ zip tạo lại). API `releases/latest` = `v1.9.5`, digest exe
`d3b8b044…` / zip `82e75bfd…` = SHA-256 local.

**Test cập nhật thật:** EXE release v1.9.4 (SHA khớp asset) → `check_update` có v1.9.5 → bấm "Cập nhật ngay" → tải 100% trong
8,3 s → server cũ thoát ở 9,8 s → 1.9.5 lên ngay sau đó → thư mục còn 1 file, SHA = asset v1.9.5, `has_update=False`. Đã tắt EXE test.

## 24. v1.10.0: đổi chỗ + ẩn/hiện cột 8 bảng dữ liệu, xuất Excel "Như đang xem", đổi tên 2 cột doanh thu *(28/09/2026)*

**Yêu cầu Trum:** (1) di chuyển cột trong danh sách chứng từ, (2) cấu hình ẩn/hiện cột — cả hai lưu theo máy; (3) tab bán hàng đổi
tên `INCOME_AMOUNT` = "Doanh thu 511", `VAT_INCOME_AMOUNT` = "Doanh thu trước thuế". Chốt thêm: áp cả 8 tab nhóm Dữ liệu; kéo được
ngay trên tiêu đề lẫn trong bảng cấu hình; tên mới áp cả file xuất; **thêm lựa chọn xuất Excel theo bố cục đang xem**.

**Đã sửa:**
- `index.html`: 8 bảng chuyển sang khai báo cột `*_GRID` + `GridHead`/`GridRow`/`GridGroupRow`/`GridFoot`/`useColLayout`/
  `ColumnConfigurator` (CLAUDE.md Bẫy 23). Gỡ 11 component dòng cũ + `PR_DETAIL_TYPE_MAP` chuyển lên cấp trên cùng.
  `SortableHeader` nhận thêm `colId`/`onColMove`. Menu Xuất Excel thêm "Cột xuất: Đầy đủ / Như đang xem". Icon mới `columns`.
- `server.py`: `_pick_export_cols` + `_tran_name_map` + `TRAN_NAME_EXPORT_COL`; 8 endpoint `stream_csv` nhận `cols`; đổi tên 2 cột
  trong `SALE_CSV_COLS`.
- Sửa kèm (lỗi có sẵn): dòng gom nhóm tab bán hàng đặt tổng tiền dưới cột "Số lượng" → nay dưới "Tổng TT"; "Tách sheet theo đơn vị"
  của Danh mục đối tượng ra file `DanhMucDoiTuong_xlsx` không đuôi → `DanhMucDoiTuong.xlsx` (trùng tên bản server).
- Đổi so với phương án đã chốt: nút "Cột" đặt ở **chân bảng** thay vì thanh lọc — đo thấy thanh lọc rớt 2 hàng (bảng dưới).

**Verify** (bộ kiểm ở scratchpad phiên 28/09 — puppeteer-core + Chrome thật, API giả qua request interception, bản dịch sẵn
`build_web` HEAD 1.9.9 dựng lại từ `git archive` so với bản mới):

| Mức | Nội dung | Kết quả |
|---|---|---|
| M1 | `ast.parse` server.py · `webbuild/build.js` (Babel 7.29.7) | đạt; app.js 494.649 → 462.932 byte, app.css không đổi (29.140 byte) |
| M3 bố cục mặc định | 8 bảng × (thường + gom nhóm ORGANIZATION_ID) ở 1366 và 1440 px, mọi phần tử trong `table.ds-grid` × 37 thuộc tính computed style + toạ độ | sổ cái, tiền, nhập kho, kho, tồn kho, đối tượng: **0 khác biệt**; DT chờ phân bổ: chỉ `cursor: move` ở 4 tiêu đề thường; bán hàng: chỉ 2 tiêu đề đổi tên (cột rộng thêm 25,5 px → cột sau dời), con trỏ kéo 7 tiêu đề, dòng nhóm đặt tổng đúng cột |
| M3 thanh lọc | 8 tab × 1366/1440/1920 × thanh bên mở/thu | nút ở chân bảng: bề rộng cần trùng 1.9.9 mọi cấu hình. (Lần đầu đặt trên thanh lọc: +87 px, 6 tab rớt 2 hàng → dời) |
| M3 thao tác | 42 ca: kéo tiêu đề trước/sau (vạch xanh, không sót `data-drop`), 44 cặp nhãn–giá trị giữ nguyên, tiêu đề/hàng tìm/ô/dòng tổng/dòng nhóm thẳng cột, cột cuối mất viền phải, ẩn cột → 42/43 + xoá ô tìm, kéo trong bảng "Cột", mở lại app giữ bố cục, Khôi phục xoá khoá localStorage, sổ cái Nợ/Có tách xa vẫn thẳng cột, tiêu đề thường kéo được, còn 1 cột thì khoá công tắc, xuất XLSX/CSV gửi `cols` đúng thứ tự, Đầy đủ không gửi, tách sheet 4 sheet × 42 cột đúng thứ tự + tên mới | **42/42 đạt**, không lỗi JS |
| M3 tốc độ | bán hàng + sổ cái 10.000 dòng, 3 vòng xen kẽ, JS vẽ dòng mỗi bước cuộn | bán hàng 12,30 → 12,40 ms (300 px), 29,2 → 29,3 ms (1.500 px); sổ cái 11,5 → 11,4 / 25,8 → 27,0 ms — bằng nhau |
| M3 SQL thật | TRUNGDEMO (Windows auth, CHỈ SELECT), 2024–2026, server HEAD vs mới qua test_client, `_export_dir` trỏ scratchpad, chặn `kill_process_on_port` lúc import | không gửi cols: 8/8 danh sách trùng tiêu đề + tập dòng + cỡ file (bán hàng khác đúng 2 tên cột); có cols: tiêu đề đúng thứ tự, tập dòng = bản đầy đủ chiếu lên đúng khoá, "Tên chứng từ" lấy từ danh mục (trống đúng như màn hình với mã NKHO không active); xlsx có cols đúng tiêu đề; khoá lạ/trùng bỏ qua, toàn khoá lạ → xuất đủ |
| M3 EXE | `python build_exe.py` → 1.10.0, 16.550.684 byte | `/api/version` 1.10.0, app.js trùng SHA-1 `build_web`, không còn CDN Babel, `/api/ledger` chưa đăng nhập 401; đã tắt EXE + cửa sổ Chrome |

- Thứ tự các dòng trùng khoá sắp xếp (cùng ngày + số CT) khác nhau giữa 2 lần chạy cùng câu SQL — có sẵn từ trước (Bẫy 20), so file
  phải so theo tập dòng.
- **Chưa làm:** chạy với DB thật của khách; kéo thả bằng chuột thật (bộ kiểm dùng sự kiện kéo giả lập trong Chrome chạy ngầm).

**QA trước push (skill pre-push-qa):** 🟡 VÀNG — không phát hiện lỗi chặn push; vàng vì 2 mục "chưa làm" trên. Đã rà: diff 7 file
(843 dòng thêm); `origin/main` vẫn là `809e6c0` (Gemini không đẩy thêm); EXE build 13:17 sau lần sửa nguồn cuối (index.html 12:57,
server.py 12:31); không mất handler nào khi gỡ 11 component dòng (chỉ còn `toggleExpand` dòng nhóm + `title` địa chỉ — đều giữ);
mọi cột trên màn hình có khoá trong cả `*_EXPORT_COLS` lẫn `*_CSV_COLS` (script so 8 bảng); 8 `ExportButton` đều có trong
`gridLays`; quét secret dòng thêm (IP, chuỗi kết nối, từ khoá mật khẩu, token, email — chỉ in vị trí + độ dài, đã tự thử trên
chuỗi mẫu): 0 khớp; `py_compile` đạt. Ghi nhận nhỏ, không sửa: dòng gợi ý "N cột đang hiện" trong menu xuất đếm khoá xuất —
Danh mục đối tượng ra 16 (cột "Loại đối tượng" xuất 2 cột mã + tên) trong khi bảng hiện 15.

**Phát hành (Trum bảo 28/09):** commit `8a5ac51` push `main` → `gh release create v1.10.0` (tiêu đề "DataStudio v1.10.0 (iPOS Ledger
Studio)", target SHA đầy đủ), asset `iPOS_Ledger_Studio.exe` 16.550.684 byte + `.zip` tạo lại từ EXE (zip trong `dist/` còn là bản
27/09). API công khai `releases/latest` trả `v1.10.0`, digest exe = SHA-256 file build `3fdb44b6…86d3`.

**Test cập nhật thật:** EXE release v1.9.9 (SHA = asset `88ce1537…b54a`) chạy ở thư mục tạm → `check_update`: `has_update=true`,
`latest=v1.10.0` (so bộ số: 1.10.0 > 1.9.9) → hộp bắt buộc cập nhật hiện "v1.9.9 → v1.10.0 · DataStudio v1.10.0 · 15.8 MB" → bấm
"Cập nhật ngay" (puppeteer) → tải 100% trong ~3 s → server cũ thoát → 1.10.0 lên sau 6,3 s kể từ lúc bấm → thư mục còn 1 file,
SHA = asset v1.10.0, bản mới `has_update=False`. Đã tắt EXE test + 9 tiến trình Chrome của cửa sổ app, cổng 5050 đã nhả.

## 25. v1.10.1: ô tìm theo cột cho mọi cột chữ/mã + tooltip ghi ô lọc tới đâu *(28/09/2026)*

**Yêu cầu Trum (kèm ảnh tab bán hàng):** trừ cột tiền, các cột còn lại chưa có ô lọc thì thêm, ở mọi màn danh sách. Trum chốt:
6 cột bán hàng (Trả, Mã HTTT, Hình thức TT, Mã nguồn, Nguồn đơn, Ghi chú) bấm Truy vấn thì lọc SQL cả kỳ; tab khác chỉ lọc các dòng
đang tải (như ô cùng tab); **thêm tooltip ghi chú**; không thêm ô cho cột số (số lượng, thuế %, tỷ lệ); cột cờ khớp theo chữ đang
hiện; DT chờ phân bổ thêm hàng ô lọc (đầu bảng 34 → 69 px); phát hành luôn.

**Đã sửa:**
- `index.html`: `search: 1` (chỉ lọc trang) / `search: 2` (Truy vấn lọc SQL) cho mọi cột; `sv` (chữ để lọc cột cờ), `sh` (gợi ý);
  tooltip `colSearchTitle`; `gridSearchText` + `grid.byId`. Thêm ô: bán hàng 6, DT chờ phân bổ 19 (state `incomeAllocColSearch`,
  `incomeAllocFlatData`, ẩn cột xoá chữ lọc), kho 1 (N/X), tồn kho 4 (Ngày, ĐVT, ĐVT nguyên, Đã duyệt), danh mục 1 (Trạng thái).
  `buildSaleQuery` gửi `s_pay_id`, `s_pay_name`, `s_src_id`, `s_src_name`, `s_comments` (≥ 2 ký tự), `s_return`. Menu xuất ghi số
  cột đang hiện trên bảng (trước đếm khoá xuất: Danh mục đối tượng 16 thay vì 15).
- `server.py` `_build_sale_where`: 6 tham số trên (Bẫy 23) + `_like_literal`.
- Rà lại toàn bộ ô cũ để tooltip nói đúng: 5 ô gửi tham số mà server không đọc (tab tiền: Tên đơn vị, Đối tượng, Đối tượng đối ứng;
  nhập kho + kho: Ngày CT) → ghi "chỉ lọc trang". Chưa sửa cho chúng lọc SQL (ngoài yêu cầu).

**Verify:**

| Mức | Nội dung | Kết quả |
|---|---|---|
| M1 | `ast.parse` server.py · `webbuild/build.js` | đạt; app.js 462.932 → 466.564 byte |
| M3 giao diện | `search.js` (puppeteer, API giả, bản dịch sẵn) 8 tab: cột nào có ô, tooltip từng loại, lọc đúng dòng, cột cờ, tham số gửi khi Truy vấn/xuất, ẩn cột đang lọc, menu xuất; hàng tiêu đề so v1.10.0 (dựng lại từ commit, app.js trùng SHA-1 bản phát hành) | **86/86**; tiêu đề trùng vị trí/rộng/cao 8 tab, đầu bảng giữ 69 px (trừ DT chờ phân bổ 34 → 69) |
| M3 bố cục cột | `behave.js` 42 ca của v1.10.0 | 42/42 |
| M3 SQL thật | TRUNGDEMO (CHỈ SELECT) 2018–2026, 3.011 dòng bán hàng: mỗi tham số so với tự lọc bản không lọc theo luật màn hình | **24/24** (mã, tên HTTT/nguồn, ghi chú, trả, chữ không có, dấu `'`, `_` `%` là chữ, kết hợp, xuất CSV cùng lọc = 193 dòng như màn hình) |
| M3 EXE | `build_exe.py` → 1.10.1, 16.552.768 byte | `/api/version` 1.10.1, app.js trùng SHA-1 `build_web`, `/api/ledger` chưa đăng nhập 401 |

- Lần build đầu báo SUCCESS mà EXE không đổi: Trum đang mở `dist\iPOS_Ledger_Studio.exe` (Bẫy 10) nhưng `version.txt` đã nhảy 1.10.1
  → trả `version.txt`/`version_info.txt` về 1.10.0, Trum đồng ý tắt app, build lại ra đúng 1.10.1.
- `/icon.svg` 404 ở lần tải đầu (cả v1.10.0): index.html trỏ `/icon.svg` mà `build_web` không có — có sẵn, chưa sửa.

**QA trước push (pre-push-qa):** 🟡 — không lỗi chặn; vàng vì chưa chạy DB thật của khách. `origin/main` vẫn `3155e8d`; code sửa
(index.html 16:21, server.py 16:28) trước lúc build EXE 16:45; 273 dòng thêm: không secret, không log debug/TODO.

**Phát hành (Trum bảo "phát hành luôn"):** commit `11449f2` push `main` → `gh release create v1.10.1` (exe 16.552.768 byte + zip tạo
lại). API công khai trả `v1.10.1`, digest exe = SHA-256 file build `ff275d11…dcd2d`.

**Test cập nhật thật:** EXE release v1.10.0 (SHA = asset) ở thư mục tạm → hộp bắt buộc cập nhật "v1.10.0 → v1.10.1" → bấm → 1.10.1
lên sau 4,7 s, thư mục còn 1 file, SHA = asset, bản mới `has_update=False`. Đã tắt EXE test + 9 tiến trình Chrome.

## 26. v1.10.2: ô lọc cột số + lọc "bắt đầu bằng" cho cột số, cột mã/tài khoản, ô Tài khoản trên thanh lọc *(28/09/2026)*

**Yêu cầu Trum:** cho lọc cả số lượng, tỷ lệ %, tiền; gõ 145 thì ra các số BẮT ĐẦU bằng 145, không lấy 145 nằm giữa; sửa luôn logic đó
ở ô bộ lọc tài khoản trên thanh lọc và dòng lọc ở các cột. Trum chốt: sổ cái/bán hàng/tiền/nhập kho/kho/tồn kho bấm Truy vấn lọc SQL
toàn bộ (DT chờ phân bổ chỉ lọc trang); so theo số đang hiện (tiền làm tròn tới đồng); số âm gõ `-`; ô "Số tiền" tab tiền đổi sang
bắt đầu bằng; dòng lọc cột: **mọi cột mã + tài khoản** bắt đầu bằng (cột tên giữ "chứa"); thanh lọc: **chỉ ô Tài khoản**; phát luôn.

**Đã sửa:**
- `index.html`: `q: 'num'` 32 cột số (có ô lọc), `q: 'pre'` 101 cột mã; `gridMatch` thay `gridSearchText` ở 8 bộ lọc; `gridNumParams` gửi
  `n_<ID>` (sổ cái: tải + xuất; bán hàng, tiền, tồn kho: `build…Query`; nhập kho, kho: CẢ `build…Query` lẫn `load…Data` — 2 bản danh sách
  tham số, so 21/21 khoá trùng nhau); tooltip thêm luật so; `PremiumDropdown codePrefix` cho 6 ô tài khoản.
- `server.py`: `_num_prefix_where` + `LEDGER/SALE/PURCHASE/WAREHOUSE/WAREHOUSE_BALANCE/VOUCHER_NUM_SEARCH` gắn cuối 6 hàm `_build_…_where`;
  bán hàng: Doanh thu 511 / trước thuế là cột phụ → DB không có thì 1=0. `import re` lên đầu file.
- **Lỗi bắt được trước khi build:** `_NUM_PREFIX_RE = re.compile(...)` chạy lúc nạp module (dòng 699) mà `import re` nằm ở dòng 6487 →
  `NameError`, EXE sẽ sập ngay khi mở. `ast.parse` đạt nên không thấy; lộ ra khi bài kiểm SQL `import server`. CLAUDE.md Bước 1 đã ghi.

**Verify:**

| Mức | Nội dung | Kết quả |
|---|---|---|
| M1 | `ast.parse` + `import server` thật · `webbuild/build.js` | đạt; app.js 466.564 → 470.159 byte |
| M3 giao diện | `num.js` (API giả): cột số gõ chuỗi có dòng khớp đầu VÀ dòng chứa ở giữa → chỉ ra dòng bắt đầu bằng (gõ kèm dấu phẩy), gửi `n_<ID>` bỏ dấu phẩy, thuế % gõ `10`/`10%`, gõ chữ vào cột số → 0 dòng, cột mã `id-12` → 0 còn `item_id-12` → 11, cột tên vẫn "chứa", xuất file mang `n_`, ô Tài khoản: 111 → 111/1111/1112 (không 3111), 511 → không 1511/3511, gõ chữ vẫn tìm tên, DT chờ phân bổ không gửi `n_` | **52/52** |
| M3 giao diện | `search.js`: mọi cột có ô (trừ #), tooltip, hàng tiêu đề trùng v1.10.0 (ô mới không nong cột) · `behave.js` | 86/87 (1 = `/icon.svg` 404 có sẵn) · 42/42 |
| M3 SQL thật | TRUNGDEMO (CHỈ SELECT): 6 tab 176–3.011 dòng × 27 cột số × ~6 chuỗi (1–4 chữ số, `-`, có dấu `.`, chữ) — server so với tự tính số đang hiện như trình duyệt | **156/156**; bài lọc bán hàng v1.10.1 vẫn đạt |
| M3 EXE | `build_exe.py` → 1.10.2, 16.556.895 byte | `/api/version` 1.10.2, app.js trùng SHA-1 `build_web`, `/api/ledger` chưa đăng nhập 401 |

- So tập dòng phải bỏ trường `RowNum` (số thứ tự do câu phân trang ROW_NUMBER sinh ra, đổi theo bộ lọc).
- Còn lệch lý thuyết, chưa gặp trong dữ liệu: số âm đúng .5 (JS `Math.round(-1.5)` = -1, SQL `ROUND` = -2); giá trị nhị phân sát ranh .xx5.

**QA trước push (pre-push-qa):** 🟡 — không lỗi chặn; vàng vì chưa chạy DB thật của khách. `origin/main` vẫn `c19f636`; code sửa
(index.html 17:23, server.py 17:26) trước lúc build 17:29; 293 dòng thêm: không secret (15 chỗ khớp mẫu "host,port" đều là số ví dụ
dạng 1,450), không log debug/TODO.

**Phát hành (Trum bảo "phát luôn"):** commit `df1ea8a` → `gh release create v1.10.2` (exe 16.556.895 byte + zip tạo lại). API công khai
trả `v1.10.2`, digest exe = SHA-256 file build `85205943…c382b`.

**Test cập nhật thật:** EXE v1.10.1 (SHA = asset) → hộp bắt buộc cập nhật → bấm → 1.10.2 lên sau 9,4 s, còn 1 file, SHA = asset, bản mới
`has_update=False`. Đã tắt EXE test + Chrome.

## 27. v1.10.3: mọi dòng cùng chiều cao (hết trắng bảng / giật khi kéo thanh cuộn) + dòng tổng đủ cột + cột Địa chỉ bán hàng *(28/09/2026)*

**Yêu cầu Trum:** (1) lọc ở dòng lọc cột rồi lướt danh sách thì giật; (2) kéo thanh cuộn, buông chuột thì bảng tự chạy vèo xuống
cuối; (3) cột số lượng/tiền nào cũng có tổng ở dòng cuối; (4) thêm cột Địa chỉ ở chứng từ bán hàng — Trum chốt lấy
`SALE_VIEW.ADDRESS` (địa chỉ trên chứng từ), không phải địa chỉ trong danh mục đối tượng. Chốt mục (3): cộng toàn bộ truy vấn như
cũ; ô lọc loại bớt dòng trên trang thì cộng đúng các dòng đang hiện; dòng gom nhóm giữ nguyên. "phát hành".

**Tìm nguyên nhân (1)(2):** bài thử API giả 10.000 dòng (kéo thanh cuộn bằng chuột giả lập, CPU ×1/×4/×6, DPR 1/1,25/1,5,
có/không lọc) KHÔNG tái hiện: dữ liệu giả có gạch nối ở MỌI ô ("pr_detail-12") → mọi ô xuống dòng như nhau → mọi dòng 39px đều.
Video Trum (Snagit, tab bán hàng 44.223 dòng, lọc Tên kho "online") cho thấy: cột Mã ĐT (w-24, không nowrap) có mã
"KL-CRM.CALCENTER" xuống 2 dòng → dòng 39px xen dòng 31px; lúc kéo có đoạn bảng trắng, chỉ còn 1–2 dòng trên cùng. Đo chiều cao dòng
8 tab với dữ liệu kiểu thật (`pt/heights.js`): tab nào cũng lệch — 21px (ô Diễn giải `py-1.5` trống), 39px (mã có gạch nối), 57–111px
(tên dài ở cột không nowrap), 23,5px (nhãn nhóm đối tượng). Bảng ảo đặt dòng theo 1 chiều cao → sai vị trí.

**Đã sửa:**
- `index.html` CSS `.ds-grid tbody td { white-space: nowrap }`; `gridCell` vẽ `'\u00a0'` cho ô trống; nhãn nhóm đối tượng
  `leading-[18px] align-top`; `useVirtualScroll` đo chiều cao chỉ trên dòng thường (bỏ `.ds-grp`). Đã thử `td:empty::after` thay
  cho `'\u00a0'`: chậm thêm 3–11 ms mỗi bước cuộn → bỏ.
- `VirtualRows`: tiêu đề cột giữ `min-width` = bề rộng lớn nhất đã thấy (chỉ rộng thêm), đổi `data` thì thả.
- Dòng tổng: `grid.foot` + `footCells` + `gridFilter`/`footRowSums`/`footShownLabel` (7 tab); `GridFoot` đặt nhãn vào đoạn cột trống
  dài nhất khi ô tổng bị kéo lên sát đầu; tab tồn kho thực tế thêm dòng tổng + `known_sums`.
- `server.py`: bán hàng SUM `INCOME_AMOUNT`/`VAT_INCOME_AMOUNT` chỉ khi SALE_VIEW có cột; nhập kho SUM `PURCHASE_COST`; tồn kho
  thực tế COUNT + SUM `ISNULL(QUANTITY/QUANTITY_ADJ,0)` + dùng lại `known_sums`; `s_address` → `S.ADDRESS LIKE '%x%'` (`_like_literal`).
- Cột Địa chỉ: `SALE_GRID` sau Tên đối tượng, `search: 2`, sắp xếp `ADDRESS` (đã có trong whitelist), `truncate max-w-[280px]` + `title`.

**Verify:**

| Mức | Nội dung | Kết quả |
|---|---|---|
| M1 | `ast.parse` + `import server` thật · `webbuild/build.js` | đạt |
| M3 chiều cao | `heights.js`: 8 tab × dữ liệu kiểu thật (mã gạch nối, ô trống, emoji, tên dài) | trước: 8/8 tab lệch 2–5 mức · sau: 8/8 đều (31px; kho/tồn kho/danh mục 21px) |
| M3 kéo thanh cuộn | `realistic.js`: bán hàng 10.000 dòng kiểu video, kéo con trượt bằng chuột, có/không lọc "online", CPU ×1/×4 | v1.10.2: trắng tới 100%, scrollHeight 117 giá trị, trôi 230px · mới: trắng 0%, scrollHeight cố định, trôi ≤ 1px |
| M3 giật | `jitter.js`: 250 bước × 240px, dòng mốc phải đi đúng khoảng cuộn | v1.10.2 giật dọc 77–129 bước (tới 216px), xô ngang 14–26 · mới 0 giật dọc (bán hàng, sổ cái, tiền, kho), xô ngang 4–7 |
| M3 tốc độ | `perf4.js` so v1.10.2, 3 vòng xen kẽ, trung vị | cuộn 300px/bước: +2–3 ms (~10%); kéo nhanh 1.500px: trong độ nhiễu (v1.10.2 tự dao động 31–56 ms) |
| M3 giao diện | `foot.js` (dòng tổng 7 tab: số server, đứng đúng cột, lọc bớt dòng → cộng dòng đang hiện, gõ không loại dòng → giữ tổng server; cột Địa chỉ: vị trí, tooltip, chứa, `_` là chữ, `title`, gửi `s_address`) · `num.js` · `behave.js` | **47/47** · 52/52 · 42/42 (3 kỳ vọng sửa: 43/44 cột, nhãn tổng sang đoạn trống) |
| M3 giao diện | `search.js` so tiêu đề v1.10.0 | 82/87: `/icon.svg` 404 có sẵn; bán hàng thêm cột; 3 tab cột rộng thêm 7–13px (dữ liệu giả có gạch nối nay không xuống dòng) |
| M3 SQL thật | `test_v1103_db.py` TRUNGDEMO (CHỈ SELECT): tổng mới = cộng tay, trang 2 `known_sums`, giả lập DB thiếu cột Doanh thu 511, `s_address` 9 chuỗi (có `%`, `_`) = lọc tay, sắp xếp ADDRESS | **24/24**; `test_num_db.py` 156/156, `test_sale_search_db.py` đạt |

- Thay đổi nhìn thấy: cột có chữ dài hơn bề ngang giờ rộng ra thay vì xuống dòng (vd Mã ĐT ở đoạn có "KL-CRM.CALCENTER").
- Chưa tái hiện 1:1 cảnh "tự chạy tới cuối trang" (máy dev chỉ thấy trôi 230px); nguyên nhân khả dĩ nhất — scrollHeight đổi liên tục
  khi chiều cao dòng đo lại — đã hết. Cần Trum thử trên máy thật sau khi cập nhật.

**QA trước push (pre-push-qa):** 🟡 — không lỗi chặn; vàng vì chưa chạy DB thật của khách. `origin/main` vẫn `267d542`; 256 dòng thêm:
không secret, không log/TODO. Bắt được khi soát diff: `'\u00a0'` viết qua công cụ Edit/heredoc thành KÝ TỰ NBSP thật (vô hình) ở
index.html + CLAUDE.md + GEMINI.md → đổi lại dạng mã `\u00a0` (dựng dấu `\` bằng `chr(92)`: heredoc của công cụ nuốt 1 dấu `\`).

**Phát hành (Trum bảo "phát hành", "tự làm tới cuối đi"):** `build_exe.py` → 1.10.3, 16.559.112 byte; EXE ở thư mục tạm: `/api/version`
1.10.3, `app.js` trùng SHA-1 `build_web`, `/api/ledger` chưa đăng nhập 401. Commit `ca38d21` → `gh release create v1.10.3` (exe +
zip tạo lại 16.345.476 byte). API công khai trả `v1.10.3`, digest exe = SHA-256 file build `1277930d…3fa63`.

**Test cập nhật thật:** EXE v1.10.2 (SHA = asset) → hộp bắt buộc cập nhật → bấm → 1.10.3 lên sau 6,9 s, còn 1 file, SHA = asset, bản mới
`has_update=False`. Đã tắt EXE test + Chrome.

## 28. v1.10.4: thanh bên 2 thẻ Dữ liệu | Báo cáo, hiệu ứng Tải lại danh mục, ẩn Tồn kho thực tế, đổi 2 tên *(28/09/2026)*

**Yêu cầu Trum:** (1) ẩn bảng tồn kho thực tế; (2) làm lại hiệu ứng khi bấm "Tải lại danh mục" xong cho đẹp hơn; (3) thanh bên có 2
thẻ nhỏ Dữ liệu và Báo cáo, bấm thẻ nào hiện danh sách của thẻ đó; (4) đổi tên "Chứng từ bán hàng" → "Chứng từ xuất - bán hàng",
"Chứng từ nhập kho" → "Chứng từ nhập - mua hàng".

**Đã sửa (chỉ `index.html`, server không đổi):**
- (1) Comment dòng `warehouse_balance` trong `DOC_TABS` — code tab + API giữ nguyên. Màn đăng nhập tự ghi "7 phân hệ chứng từ" (đếm `DOC_TABS`).
- (4) `DOC_TABS` + `NAV_DOC_META` (thanh bên + đầu trang). Tên file xuất GIỮ `ChungTuBanHang_` / `PhieuNhapKho_` (tên file ASCII,
  Trum chỉ yêu cầu tên hiển thị). Đo: 2 tên mới vừa thanh bên 216px, không bị cắt "…".
- (3) `AppSidebar` thành component có state `sec`: `.ds-navtabs` (2 nút, `role="tablist"`) + `.ds-navlist` (`key={sec}` → hiệu ứng
  hiện 0,16 s). Bấm thẻ chỉ đổi danh sách; trang đang mở ở thẻ kia → chấm xanh `has-page`; trang đổi nhóm → thẻ theo. Không nhớ thẻ
  qua localStorage (activeTab cũng không nhớ). Gỡ `ds-group`.
- (2) `refreshing` (bool) → `metaRefresh` (`busy/ok/err`); nút đổi dạng (xoay → nền xanh lá + ✓ tự vẽ → về thường) + `MetaToast` cạnh
  nút có số danh mục vừa nạp + thời gian. Trước: thêm class Tailwind `bg-emerald-500/20 text-emerald-400` (xanh nhạt trên nền sáng,
  gần như không thấy) và lỗi thì im lặng — nay lỗi server hiện nguyên văn, mất mạng hiện câu tiếng Việt, danh mục cũ giữ nguyên.

**Verify (M3 giao diện, API giả, bản dịch sẵn `build_web`):**

| Bài | Kết quả |
|---|---|
| `pt/sidebar.js` (mới): 2 thẻ, 7 mục + tên mới, không mục nào bị cắt, bấm thẻ không đổi trang, chấm `has-page`, chọn báo cáo / tab dữ liệu thì thẻ theo, thu gọn 56px không tràn, tải lại: đang tải (xoay, khoá, không mờ) → xong (nền xanh, ✓ vẽ xong, thẻ báo đúng số, cách thanh bên + thanh trạng thái 12px, tự tắt 3,6 s) → lỗi 500 (nguyên văn, danh mục cũ còn) → mất mạng + thu gọn (câu dễ hiểu, thẻ dời theo) → bấm 3 lần lúc đang tải = 1 lần gọi → in không có thẻ báo | 30/30 |
| `behave.js` / `foot.js` / `num.js` / `heights.js` | 42/42 · 41/41 · 48/48 · 7/7 tab đều (bỏ tab tồn kho khỏi bài vì đã ẩn) |
| `search.js` so v1.10.2 | 75/80 — 5 trượt là khác biệt đã biết của v1.10.3 (cột Địa chỉ, cột rộng thêm do nowrap) + `/icon.svg` 404 có sẵn |

- Bộ kiểm: `harness.js` thêm `page.__delay` / `__fail` / `__abort` theo đường dẫn API (trễ / trả 500 / cắt kết nối); `gotoTab`
  nhận cả tên tab cũ (so bản ≤ v1.10.3). `page.setOfflineMode` KHÔNG làm fetch lỗi khi đang chặn request (API giả vẫn trả lời).

**Phát hành (Trum bảo "phát hành"):** QA 🟢; tắt EXE `dist` đang mở (khoá file khi build — Bẫy 10); `build_exe.py` → 1.10.4, 16.563.151 byte;
EXE ở thư mục tạm: `/api/version` 1.10.4, `app.js`/`app.css`/`index.html` trùng `build_web`, `/api/ledger` chưa đăng nhập 401;
`/api/metadata` + refresh trên TRUNGDEMO đủ 5 mảng (265 TK · 6 ĐV · 103 ĐT · 4.397 HH · 9 kho). Commit `c08768a` → Release v1.10.4, digest
exe = SHA-256 build `0886151c…8122a`. Test cập nhật thật 1.10.3 → 1.10.4: Trum ngắt giữa chừng để báo lỗi chớp menu Xuất Excel — KHÔNG chạy.

## 29. v1.10.5: hộp "Cập nhật ngay" liệt kê nội dung từng bản + sửa chớp nháy menu Xuất Excel *(28/09/2026)*

**Yêu cầu Trum:** (1) menu Xuất Excel: bấm qua lại "Đầy đủ" / "Như đang xem" thì nút chuyển (pill) và bảng chọn chớp nháy; (2) hộp "Cập nhật
ngay" phải ghi từ bản nào lên bản mới nhất + gạch đầu dòng tóm tắt nội dung qua các phiên bản; "sửa xong phát hành luôn".

**(1) Nguyên nhân:** `ExportButton` khai báo TRONG thân App → mỗi lần App vẽ lại là một kiểu component mới → React gỡ + lắp lại cả nút lẫn
menu; `chooseExportCols` đổi state của App → vẽ lại → menu lắp lại, hiệu ứng `ds-pop-in` chạy lại = chớp. Đo (`pt/expflicker.js`, 3 tab ×
4 lần bấm): v1.10.4 phần tử menu/nút bị thay mới, `animationstart` 2–4 lần → sửa: `ExportButton` ra cấp trên cùng, App truyền
`{...exportBtn}` (8 chỗ gọi) → cùng phần tử, 0 lần; lựa chọn + localStorage, bấm ra ngoài đóng, mở lại nhớ lựa chọn, xuất "Như đang xem"
gửi `cols=`: 26/26.

**(2) Làm:** `server.py` `_fetch_release_list` / `_md_plain` / `_short_item` / `_release_summary` / `_changes_between`; `/api/check_update` thêm
`changes`, `changes_more` (chỉ gọi danh sách khi có bản mới; lỗi → rỗng, không ảnh hưởng báo bản mới). `ForceUpdateModal`: "Gồm N bản cập
nhật" + khung "Nội dung cập nhật" (mỗi bản: số bản, ngày, tóm tắt, gạch đầu dòng), không có `changes` → hộp y hệt cũ.
- Giới hạn đã báo Trum: hộp là code của bản đang cài → máy ≤ v1.10.4 lên v1.10.5 vẫn thấy hộp cũ (chỉ có dòng "Bản phát hành" = tên release).
  Tên release v1.10.5 đặt "Thanh bên 2 thẻ, sửa Xuất Excel" (31 ký tự): thử tên 76 / 46 ký tự trên hộp cũ → nhãn "Bản phát hành" gãy 3 / 2 dòng.

**Verify:**

| Bài | Kết quả |
|---|---|
| `test_changes.py`: `_release_summary` trên ghi chú thật 17 release (3 kiểu viết) | đủ ý, bỏ mục Cập nhật/Cài đặt (v1.8.3 "### Cài đặt" lọt 3 dòng ở lần chạy đầu → đã thêm) |
| `test_check_update.py`: `/api/check_update` với GitHub thật, giả máy ở 1.10.3 / 1.10.2 / 1.9.5 / 1.10.4 + ca lỗi (danh sách lỗi, 16 bản, nháp/thử nghiệm, ghi chú rỗng, > 6 dòng) | 17/17 |
| `pt/updmodal.js` (dữ liệu = check_update thật + v1.10.5 dựng từ ghi chú): 1366×768 và 1920×1080, 2 bản và 10 bản, hộp nằm trọn màn hình, danh sách tự cuộn; không `changes` → so từng phần tử với hộp v1.10.4 | 36/36 (33 phần tử trùng) |
| `sidebar` / `expflicker` / `behave` / `foot` / `num` / `heights` | 30/30 · 26/26 · 42/42 · 41/41 · 48/48 · 7/7 tab đều |
| EXE thư mục tạm | `/api/version` 1.10.5, 3 file giao diện trùng `build_web`, `/api/check_update` trong EXE gọi GitHub được, 401 |

**Phát hành:** commit `5251d87` → Release v1.10.5 (exe 16.567.021 byte, digest = SHA-256 build `640d6770…8f090`; zip tạo lại). Sau phát
hành: `/api/check_update` thật — máy 1.10.3 thấy [v1.10.5, v1.10.4], máy 1.10.4 thấy [v1.10.5], máy 1.10.5 không có cập nhật.
- Test cập nhật thật (EXE cũ bấm "Cập nhật ngay") KHÔNG chạy ở v1.10.4 lẫn v1.10.5 (Trum ngắt lần chạy ở v1.10.4). Code tải/thay EXE
  không đổi trong cả loạt v1.10.x; test thật đạt ở 4 lần phát hành v1.10.0–v1.10.3 (CLAUDE.md đầu file).
