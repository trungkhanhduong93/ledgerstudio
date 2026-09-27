# 📘 CLAUDE.md / GEMINI.md — BỘ NGUYÊN TẮC LÀM VIỆC & KIẾN TRÚC TOÀN TẬP LEDGERSTUDIO

> 📌 **DÀNH CHO TẤT CẢ AGENT AI (Claude Code, Gemini, Antigravity, Cursor, Windsurf, ChatGPT):**
> File này là **NGUỒN SỰ THẬT DUY NHẤT (Single Source of Truth)** của dự án `LedgerStudio`. Khi được yêu cầu *"đọc toàn bộ file md hướng dẫn và kiến trúc"*, bạn **BẮT BUỘC** tuân thủ 100% các nguyên tắc, ma trận báo cáo, quy trình test/build và danh sách bẫy bug dưới đây trước khi thực hiện bất kỳ chỉnh sửa nào.
> **Dự án:** LedgerStudio — tên hiển thị **`DataStudio`** từ v1.8.7 (trước: `iPOS Ledger Studio`). Tên FILE vẫn `iPOS_Ledger_Studio.exe`, repo `ledgerstudio`, thư mục xuất `Downloads\iPOS_Ledger_Studio\` — đổi tên file là gãy tự cập nhật (Bẫy 13).  
> 🔀 **GIT: repo riêng [`trungkhanhduong93/ledgerstudio`](https://github.com/trungkhanhduong93/ledgerstudio) — PUBLIC** (từ 17/09/2026, chỉ nhánh `main`).
> Chỉ commit/push khi Trum bảo. Trước mọi push chạy `git remote get-url origin` — phải ra `.../ledgerstudio.git`.
> Remote cũ từng trỏ nhầm repo **LedgerReport** (gỡ 16/08/2026): push nhầm là đè code Studio lên `main` của Report.
> Repo công khai → **cấm commit mật khẩu / IP server DB / file dữ liệu khách** (`BaoCaoMau/` đã `.gitignore`).
> Build vẫn chạy **`BuildEXE-LedgerStudio.bat`**, EXE nằm trong `dist` (không lên git). Phát hành qua **GitHub Releases** — app từ v1.8.3 tự cập nhật (mục 5, Bước 5).
> **Cập nhật gần nhất:** 27/09/2026 (v1.9.3 CHƯA phát hành: tốc độ tab sổ cái — Bẫy 20; bộ lọc nâng cao — Bẫy 21 · **v1.9.2 đã phát hành** — Release mới nhất; test cập nhật thật từ v1.8.5 · v1.9.2: màn đăng nhập — mục 3.1, Bẫy 19 · v1.9.1: hộp thoại — mục 3.0, Bẫy 18 · v1.9.0: khung báo cáo + zoom — mục 3.0, Bẫy 17 · v1.8.9: bảng dữ liệu + cuộn mượt — mục 3.0, Bẫy 16 · v1.8.8: thanh lọc chip · v1.8.7: khung + tên DataStudio — Bẫy 15 · v1.8.6: giao diện dịch sẵn — Bẫy 14)

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
  - **Từ v1.8.6 (27/09/2026) EXE KHÔNG nhúng index.html gốc.** `build_exe.py` gọi [webbuild/build.js](file:///d:/IACC%20HCM/iPOS%20ACC/ACC%20PMKT/LedgerStudio/webbuild/build.js) ghi ra `build_web/`: JSX dịch sẵn thành `app.js` (đúng Babel 7.29.7 + preset `react, env` như trình duyệt), Tailwind 3.4.17 build ra `app.css`, React/ReactDOM/xlsx/font Inter vào `build_web/vendor/`. EXE mở không cần internet; vẽ màn đăng nhập 7,6 s → 0,2 s (máy dev), 36 s → 0,5 s (CPU chậm ×4).
  - `index.html` gốc vẫn là **bản nguồn duy nhất để sửa**; `python server.py` vẫn chạy nó qua CDN + Babel như cũ.
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

### 3.0 Khung app — hướng "Sổ cái tĩnh" (từ v1.8.7, Đợt 1 nâng cấp giao diện)
- **Thanh bên trái** `AppSidebar` (216px, nút thu gọn còn 56px — nhớ qua `localStorage['ds_sidebar_collapsed']`): nhóm *Dữ liệu* (7 tab từ `DOC_TABS`) + nhóm *Báo cáo* (9 mẫu từ `REPORT_TYPES`, xếp theo mã) + *Tải lại danh mục* (`id="btn-refresh-meta"`, `refreshMeta` tô xanh nút này) + *Đăng xuất*. Tên ngắn/icon ở `NAV_DOC_META`, `NAV_REPORT_META` — thêm tab/báo cáo vào `DOC_TABS`/`REPORT_TYPES` là tự hiện.
- Chọn báo cáo ở thanh bên đi qua `pickReport()` — **cùng luật với dropdown "Mẫu báo cáo"**: đang có `reportData` mà đổi mẫu → hộp "Chuyển mẫu báo cáo?".
- **Đầu trang** `AppPageHeader` (tên tab/báo cáo + mã, mẫu) · **Thanh trạng thái** `AppStatusBar` 26px (kết nối, CSDL, số bản ghi sổ cái, kỳ, version). Thay thanh đen trên cùng + `DocumentTabDropdown` (đã gỡ).
- CSS khung: class `ds-*` trong `<style>` đầu `index.html`, biến `--ds-*`. Token màu cho các đợt sau: `tailwind.config` (`ink`, `line`, `canvas`, `wash`, `tint`, `rail`, `brand`, `ok/warn/bad`) — hai nơi giữ khớp nhau. Xanh iPOS `#0068AC` là màu nhấn duy nhất; cam `#FF9D3D` chỉ ở logo.
- **Thanh lọc (v1.8.8, Đợt 2):** chip 32px nhãn nằm trong (`ds-chip`, `.ds-k`), nút `ds-btn`/`ds-btn-pri`, popup `ds-pop` + dòng chọn `ds-opt`, ô nhập `ds-input`, nút chuyển `ds-seg`. Component dùng chung đã đổi giao diện, GIỮ nguyên props/handler: `PeriodDropdown` (nhận thêm `from`/`to` để hiện "Kỳ Tháng 1/2026 · 01/01 – 31/01"), `IOSDatePicker` (ẩn hẳn khi `disabled` = ngoài kỳ Tùy ý — bọc trong `.ds-slot`, `:empty` tự ẩn), `PremiumDropdown`, `PageSizeDropdown`, `FilterToggleButton` ("Bộ lọc khác" + số), `IssueReceiveDropdown`, `ExportButton`. Thứ tự hàng lọc: bộ lọc … Bộ lọc khác | (phải) Hiển thị · N dòng · Xuất Excel · **Truy vấn** (nút chính ngoài cùng). Tab báo cáo: Xuất Excel · PDF · **Xem báo cáo**; đã gỡ `ReportTypeDropdown` (chọn mẫu ở thanh bên).
- **Bộ lọc nâng cao (v1.9.3):** nút "Bộ lọc khác" mở panel `FilterConfigurator` (thay hàng lọc thứ 2 xổ xuống): lưới các ô lọc đang ẩn · Xoá tất cả · "Cấu hình tham số lọc" (công tắc chọn tối đa 4 ô hiện ngoài thanh lọc, kéo đổi thứ tự, nhớ theo tab) · Đóng / Lọc. Áp cho cả 7 tab dữ liệu; mặc định giữ đúng bố cục cũ. Chi tiết: Bẫy 21.
- Hàng lọc có `flex-wrap`: thiếu chỗ thì tự xuống dòng thay vì tràn mép phải (đo 8 tab × 1366/1440/1920 px, thanh bên mở/thu: không tràn, sổ cái 1 dòng ở 1366).
- **Bảng dữ liệu (v1.8.9, Đợt 3):** 7 bảng có class `ds-grid`; CSS trong `<style>` đè kiểu cũ trong ô (`font-black`/`font-bold` → mực đậm vừa, `italic` → mực phụ, mọi chữ xanh/đỏ/teal/chàm → mực, `font-mono` → Inter tabular-nums) — KHÔNG sửa từng ô của 7 component dòng. Nợ/Có cùng màu. Đầu cột chữ thường (`thead th` 11.5px, nền `wash`, không blur), hàng tìm theo cột `ds-search-row` + ô `ds-colsearch`, dòng nhóm `ds-grp-0/1` (nền xám nhạt thay chàm đặc), vùng gom nhóm `ds-groupzone` + chip `ds-gchip` (nút × thay icon ổ khoá), lúc tải `ds-loading` (vạch 2px + nhãn, vẫn chặn bấm, bỏ blur), chân `ds-pager`, `PageJumper` dùng chung đổi giao diện. Thêm cột mới vào bảng thì cứ dùng class cũ (`font-black`, `italic`…) — CSS tự đổi.
- **Khung báo cáo (v1.9.0, Đợt 4):** nền bàn `ds-desk` (#E9EDF2), tờ giấy bóng nhẹ + viền mảnh, lề 20px (bỏ `transition: all` kiểu nảy). Thanh dưới `ReportBar` (`.app-reportbar`, cùng kiểu `ds-pager`): bên trái `PageJumper` (BC007/BC008/BC013/BC012 khi >1 trang) · số dòng · A4 ngang/dọc; bên phải lên đầu · xuống cuối · zoom − % + · **Vừa khung** (mặc định). Thay 2 nút tròn nổi góc phải + viên phân trang nổi canh giữa CỬA SỔ (lệch khi có thanh bên). Lớp "đang kết xuất" chuyển từ App vào ReportTab, nằm dưới thanh lọc (`ds-loading`, bỏ blur 4px + hộp tròn to). Zoom: Bẫy 17. Nội dung tờ A4 KHÔNG đổi (so 887 phần tử BC006 + BC007 với v1.8.9: 0 khác biệt).
- **Hộp thoại (v1.9.1, Đợt 5):** khung dùng chung `ds-scrim` (nền tối 42%, KHÔNG blur) + `ds-dialog` (440px, `is-wide` 580px; hiện 0,16 s, bỏ kiểu nảy 0,4 s) + `ds-dlg-head` / `ds-dlg-body` / `ds-dlg-foot` (chân nền `wash`, nút phải: phụ `ds-btn` → chính `ds-btn-pri`). Icon trạng thái `ds-dlg-ic` (`is-ok`/`is-warn`/`is-bad`, `is-lg` cho màn kết quả). Thành phần: `ds-choice` + `ds-radio` (thẻ chọn), `ds-filename`, `ds-checks`, `ds-note` (`is-warn`/`is-info`/`is-bad`), `ds-progress` (`is-busy` = vô định), `ds-steps`, `ds-stat`, `ds-path`, `ds-tag`, `ds-kbd`, `ds-menuitem` + `ds-fmt` (menu Xuất Excel tab dữ liệu), `ds-updbar` (banner bản mới — xanh nhạt, trước là cam→chàm: cam chỉ ở logo). Đã làm lại 9 hộp đang dùng: xuất báo cáo (4 bước), đang xuất/đã xuất của tab dữ liệu, chuyển mẫu báo cáo, thông báo `showNotice`, cập nhật (đang tải/lỗi), cài ODBC driver (màn đăng nhập) + màn "Mất kết nối" (script thường, style inline). Handler giữ nguyên — đoạn onClick dài được cắt từ khối cũ dán lại. Nút chính mọi hộp = xanh iPOS (trước: xanh lục, chàm, xanh trời lẫn lộn). Thêm hộp thoại mới thì dùng khung này.
- **Màn đăng nhập (v1.9.2, Đợt 6 — đợt cuối):** xem mục 3.1. Đủ 6 đợt nâng cấp giao diện. Tài sản thiết kế + mockup: `Desktop\IVT\present IVT\SOC\` (ngoài repo; ảnh dùng trong app đã chép vào `assets/`).

### 3.1 Màn hình Đăng nhập (Login Modal)
- **Giao diện (v1.9.2):** chia đôi `ds-login` (CSS `ds-login-*` trong `<style>`): trái `ds-login-art` = giấy sổ cái kẻ dòng + tiêu đề + 3 nhãn (số phân hệ/báo cáo lấy từ `DOC_TABS.length`, `REPORT_TYPES.length`) + sóc IACC `assets/soc-it.webp` + 2 thẻ số liệu MINH HOẠ (số cố định, không lấy từ CSDL); phải `ds-login-side` = banner bản mới (nếu có) + form + chân (© năm hiện tại, `appVersion`). Cửa sổ dưới 900px ẩn nửa trái. Cỡ sóc `--soc-h: min(505px, 60vh)` để màn 1366×768 không đè chữ. Ảnh: Bẫy 19.
- **Form giữ nguyên logic:** `onSubmit={handleLogin}`, 4 ô gắn `loginData` (`required`, placeholder `sa` / `••••••••` như cũ), nhãn tiếng Việt Máy chủ · Cơ sở dữ liệu · Tài khoản · Mật khẩu. Thêm DUY NHẤT state hiển thị `showPw` (nút con mắt đổi `type` ô mật khẩu; `onMouseDown` chặn mất focus). `loginData.driver` vẫn mặc định `"SQL Server"` — form không có ô chọn driver (`driverOptions`/`driverDropdownOpen` khai báo nhưng không dùng). Hộp cài driver chỉ hiện khi `check_odbc_driver()` trả False — hiện luôn trả True.
- **Tính năng:** Nhập cấu hình máy chủ SQL Server (`Server`, `Database`, `User`, `Password`, `Driver`).
- **Xử lý Backend:** API `POST /api/login` thực hiện `_make_conn()`, thiết lập `session['db_config']`. Tự động nhận diện danh sách Driver SQL Server (ưu tiên `ODBC Driver 17 for SQL Server`).
- **Ghi nhớ:** Lưu cấu hình vào `localStorage` giúp đăng nhập nhanh lần sau.

### 3.2 Các Màn hình Dữ liệu thô (Data Tabs)
1. **Chứng từ tổng hợp (Tab LEDGER):**
   - **Tính năng:** Xem toàn bộ sổ cái kế toán (43 cột).
   - **Công nghệ:** Virtual Scroll cuộn mượt. Cho phép sắp xếp (Sort), tìm kiếm cột, lọc khoảng ngày, lọc đơn vị.
   - **Tốc độ (v1.9.3):** đếm tổng song song với lấy trang (kết nối phụ), dùng lại tổng khi chỉ đổi trang/sắp xếp, OFFSET/FETCH khi SQL ≥ 2012; thanh trạng thái hiện thời gian từng khâu của lần Truy vấn gần nhất. Chi tiết: Bẫy 20.
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
- **Yêu cầu của Trum (17/09/2026):** bấm "Cập nhật ngay" xong KHÔNG giữ bản cũ — tự xoá EXE cũ và tự mở ngay EXE bản mới, thư mục chỉ còn 1 file `iPOS_Ledger_Studio.exe`. Đừng thêm cơ chế giữ bản sao lưu. Windows còn khoá `<exe>.old` quá 60 giây thì lần mở app sau dọn tiếp.

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
- **Nguyên nhân:** Khai báo `<Icon name="..."/>` với tên không có trong `const icons` của `index.html` (v1.8.2 có 29 icon, đã thêm `x`, `folder-open`, `external-link`, `clock`, `layers`, `hard-drive`, `rotate-ccw`, `zap`, `rows`; v1.8.7 thêm `receipt`, `wallet`, `shopping-cart`, `package`, `panel-left`, `refresh-cw` → 35; v1.9.0 thêm `minus`, `plus` → 37 và sửa `chevron-right` vẽ sai thành đường chéo "⁄" từ bản đầu (nút Trang sau); v1.9.2 thêm `server`, `user`, `eye`, `eye-off`, `arrow-right` → 42; v1.9.3 thêm `grip` (tay nắm kéo) → 43; vẫn KHÔNG có `list`, `folder`). `Icon` nhận `stroke` (mặc định 2.5).
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

### Bẫy 14: Bản EXE là bản DỊCH SẴN — không phải index.html gốc (từ v1.8.6)
- **Test `python server.py` chỉ chứng minh bản nguồn.** EXE chạy `build_web/` (JSX đã dịch, Tailwind CSS tĩnh). Sửa giao diện xong phải build lại mới có trong EXE.
- **Thêm/đổi thẻ CDN trong `<head>` của index.html** (thư viện mới, đổi bản React/Babel/xlsx) → `webbuild/build.js` DỪNG BUILD kèm `[LOI webbuild]`. Cố ý: không để lọt ra EXE bản nửa CDN nửa dịch sẵn. Thêm thư viện thì sửa `webbuild/package.json` + `build.js` cho khớp.
- **Không đổi preset Babel sang cú pháp mới** để app.js "nhẹ hơn": trình duyệt đang dịch `react + env` ra ES5 (`let/const` → `var`). Chỗ nào lỡ dùng biến trước khi khai báo đang chạy nhờ vậy; bỏ `env` là có thể văng lỗi TDZ.
- **Test bản dịch sẵn không cần build EXE:** đứng trong `build_web/` rồi import server (`resource_path('.')` = thư mục hiện tại):
  `cd build_web && python -c "import sys; sys.path.insert(0,'..'); import server; c=server.app.test_client(); print(c.get('/app.js').status_code)"`
- **Máy build cần Node.js 18+** (có sẵn v24). Lần đầu `build_exe.py` tự `npm ci` trong `webbuild/` (cần mạng).
- Chứng minh "màn hình không đổi" (27/09/2026): puppeteer mở cả 2 bản với API giả, so computed style ~13.000 phần tử × 70 thuộc tính trên 5 màn (đăng nhập, sổ cái 3.000 dòng, cuộn, dropdown, báo cáo) → **0 khác biệt**.
- **Bản nguồn (CDN) có thể đo sai chiều cao dòng bảng ảo:** Tailwind CDN chèn CSS SAU lượt vẽ đầu, `useVirtualScroll` đo dòng lúc chưa có CSS rồi ngừng đo sau 12 lần → tổng chiều cao lệch (đo được 19,8 px/dòng thay vì 29,5). Bản EXE có CSS từ đầu nên không dính. Thấy bảng "trắng dưới đáy" khi chạy `python server.py` thì kiểm lại trên EXE trước khi sửa.

### Bẫy 16: Bảng ảo — vẽ lại cả App theo từng pixel cuộn / listener cuộn gắn hụt (sửa v1.8.9)
- `useVirtualScroll` được gọi trong `App` (7 bảng) → mỗi `setScrollTop` là **cả App** vẽ lại (thanh lọc, dropdown, `ExportButton` khai báo trong App bị gỡ-lắp lại). Trước v1.8.9 mỗi sự kiện cuộn đều `setScrollTop` → cuộn touchpad 600 bước × 20 px: JS 5,7 s, layout 3,8 s; CPU ×4: 74 s, 599/600 khung giật.
- Nay chỉ đổi state khi cuộn đủ **10 dòng** (`setScrollTop(prev => …)` trả `prev` = React bỏ qua); overscan 50 dòng mỗi phía nên màn hình luôn phủ kín (kiểm 932 khung: 0 lần hở). JS còn 0,65 s, CPU ×4 còn 12,4 s. **Đừng giảm overscan xuống dưới ~20 dòng** nếu giữ bước 10 dòng.
- Listener cuộn trước đây gắn trong `useEffect(…, [containerRef.current])` — deps đọc lúc RENDER, khung vừa mount thì ref còn null → chỉ gắn ở lần vẽ lại SAU; không có lần đó (hoặc khung gắn lại) là bảng đứng im, trắng dưới đáy (bắt được 1/4 lần chạy thử, không tái hiện được có chủ đích). Nay effect chạy sau mỗi render, so phần tử trong `boundRef`, khác thì gỡ cũ gắn mới.
- `table-layout: fixed`, bỏ blur đầu bảng, `content-visibility` cho dòng: đã đo — **không** nhanh hơn (fixed còn chậm hơn ~20%). Đừng thử lại.

### Bẫy 15: CSS in (`@media print`) ẩn theo VỊ TRÍ phần tử — đổi khung là in ra trang trắng
- Luật cũ `#root > div > div:first-child { display:none }` nhắm thanh đen trên cùng. Khung mới đặt `.app-shell` (chứa toàn bộ app) làm con đầu → luật đó ẩn sạch báo cáo khi bấm PDF.
- Đã sửa: `:not(.app-shell)` + ẩn tường minh `.app-sidebar, .app-pagehead, .app-statusbar` (+ `.app-reportbar` từ v1.9.0). Thêm phần khung mới thì gắn class rồi thêm vào danh sách ẩn khi in.
- Kiểm bản in bằng puppeteer: `page.emulateMediaType('print')` + `page.pdf()` — so số trang và danh sách phần tử hiện với bản cũ (27/09: 2 trang, cùng 130 phần tử + 2 div bọc).

### Bẫy 17: Zoom tờ báo cáo — dùng `transform: scale`, KHÔNG dùng CSS `zoom` (v1.9.0)
- `ReportBar` (thanh dưới khu báo cáo) đặt `transform: scale(z)` lên `.report-paper` và cỡ `W×z, H×z` lên khung bọc `.ds-papersizer` — qua ref, không qua state của ReportTab — rồi theo dõi tờ đổi cỡ (nạp dữ liệu, đổi dọc/ngang) bằng ResizeObserver. Bấm zoom chỉ vẽ lại thanh, không vẽ lại ReportTab.
- CSS `zoom` đã thử: BC012 10.000 dòng/trang tính lại style + layout **4,3–5 s mỗi lần bấm**. `transform: scale`: 0,8–1,1 s. Nạp BC012 10.000 dòng không chậm đi: trung vị 5,30 s trước, 5,36–5,50 s sau, nằm trong mức nhiễu.
- Scale không đổi chỗ tờ chiếm trong layout → thiếu `.ds-papersizer` là thu nhỏ xong còn dư khoảng trắng dưới/phải tờ. Zoom 100% = gỡ hết class và style → khung y hệt bản chưa có zoom.
- `transform` biến tờ giấy thành khối chứa của `position: fixed` bên trong nó → đừng đặt popup/nút `fixed` trong `.report-paper` (sẽ trôi theo tờ và bị scale). Nút nổi cũ đã chuyển ra `ReportBar`.
- In: `@media print` gỡ scale + cỡ khung giữ chỗ. Kiểm 27/09: bấm PDF lúc đang 75% → nội dung PDF (luồng đã giải nén) trùng bản 100% và bản v1.8.9, cùng 2 trang.
- "Vừa khung" (mặc định) chỉ THU NHỎ cho vừa bề ngang, không phóng quá 100%; tính theo `clientWidth` khung cuộn, có `scrollbar-gutter: stable` để không nhảy qua lại khi thanh cuộn hiện/ẩn. Lựa chọn nhớ ở `localStorage['ds_report_zoom']`.

### Bẫy 18: Hộp xuất báo cáo — đừng tách state "mở hộp" ra khỏi ReportTab (v1.9.1)
- Mở/đóng `ReportExportDialog` gọi `setShowExport` trong ReportTab → vẽ lại cả tờ báo cáo: ~0,45 s với BC012 10.000 dòng. Nhìn thì muốn chuyển nút + hộp thành component con tự giữ state để khỏi vẽ lại tờ.
- **ĐỪNG** làm vậy khi chưa sửa cách chụp bộ lọc: `exportCfg` đọc `viewSnapRef`, mà ref này được cập nhật trong `useEffect` SAU lượt vẽ có dữ liệu mới. Hiện nay lượt vẽ do `setShowExport(true)` gây ra mới tính lại `exportCfg` với snapshot đúng. Tách ra thì hộp nhận cfg tính TRƯỚC effect → file ghi tiêu đề/kỳ của lần xem trước (đúng lỗi Bẫy 6, sai mà im).
- `webbuild/build.js` ghim `compact: true` cho Babel: mặc định `auto` chỉ nén khoảng trắng khi nguồn > 500 KB. Đợt 5 làm nguồn JSX tụt dưới ngưỡng → app.js 456 → 553 KB (chỉ thêm xuống dòng/thụt lề). Ghim xong: 438 KB. app.css 48 → 33 KB là thật: bỏ ~65 tổ hợp class Tailwind của hộp thoại cũ.

### Bẫy 19: Ảnh giao diện (ảnh sóc màn đăng nhập) — đường dẫn, đóng gói, kiểu file, bóng đổ (v1.9.2)
- Đặt ảnh trong `assets/` ở gốc repo, gọi bằng đường dẫn tương đối `assets/…` → chạy nguồn (`python server.py` phục vụ gốc repo) và bản EXE (phục vụ `build_web/`) dùng chung một đường dẫn. `webbuild/build.js` chép `assets/` → `build_web/assets/`; `build_exe.py` thêm `build_web/assets;assets` vào `ADD_DATA`. Thêm ảnh mà quên một trong hai bước là EXE hiện ô ảnh vỡ, không báo lỗi.
- `server.py` phải khai báo `mimetypes.add_type('image/webp', '.webp')`: máy dev (Python 3.12 + registry Windows) trả `None` cho `.webp` → Flask gửi `application/octet-stream` (cùng lý do với `.woff2`).
- **Đừng dùng `filter: drop-shadow` lên ảnh lớn.** Đo 27/09 (headless, API giả, 8 vòng luân phiên): màn đăng nhập có filter FCP 344 ms, bỏ filter 308 ms, bản cũ 276 ms. Bóng đổ nay VẼ SẴN trong `assets/soc-it.webp` (1068×1332 = sóc 900×1292 + lề 84px hai bên, 40px trên; đáy cắt ngang vì khung ẩn phần tràn) → CSS phóng `height × 1.031`, `translateX(-46.63%)` để sóc giữ đúng chỗ và cỡ cũ. Làm lại ảnh thì chạy lại đoạn PIL trong `NHAT_KY_CONG_VIEC.md` mục 18 từ PNG gốc `Desktop\IVT\present IVT\SOC\soc IT - tach nen.png` (không nén chồng từ webp).

### Bẫy 20: Tốc độ tab sổ cái — kết nối phụ, dùng lại tổng, OFFSET/FETCH, đồng hồ đo (v1.9.3)
- **Khâu chậm là SQL, không phải giao diện.** Đo 27/09 (API giả, 10.000 dòng/trang): trình duyệt đọc JSON ~0,1 s + vẽ ~0,2 s. Trang 1 phải quét MỌI dòng khớp lọc 2 lần: `COUNT + SUM Nợ/Có` và sắp xếp lấy trang.
- **Song song:** `get_ledger` chạy COUNT+SUM trên **kết nối phụ** (`get_side_connection()`, key pool `<key>:side`) trong lúc kết nối chính lấy trang → chờ = khâu lâu hơn thay vì cộng hai. Mọi endpoint DB chạy dưới `global_db_lock` và `get_ledger` luôn `join` luồng đếm trước khi trả về → không bao giờ 2 luồng dùng chung 1 kết nối pyodbc. Không mở được kết nối phụ / nó lỗi giữa chừng → bỏ nó (`_drop_side_connection`) và đếm tuần tự trên kết nối chính, kết quả vẫn đúng. `close_pool_for` (đăng xuất, lỗi kết nối) đóng cả kết nối phụ.
- **Dùng lại tổng:** server bỏ qua COUNT khi nhận `known_total/known_deb/known_crd` ở **mọi trang** (trước chỉ trang > 1). App tự quyết gửi hay không: `countKey` = chuỗi tham số truy vấn trừ `page`, `page_size` — trùng lần đếm trước (đổi trang, đổi số dòng/trang, **sắp xếp**) thì gửi; bấm **Truy vấn** hoặc **Lọc** trong panel (`opts.fresh`) thì KHÔNG gửi → luôn đếm lại để thấy chứng từ mới nhập. Thêm tham số lọc mới vào query là tự vào `countKey`, không phải sửa gì.
- **OFFSET/FETCH:** `_supports_offset(conn)` thử `SELECT 1 … OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY` một lần mỗi (server, DB, user); SQL 2008 báo lỗi cú pháp → dùng `ROW_NUMBER` như cũ. Chạy được cả ở compat level 100 (đã thử SQL 2016 + DB compat 100). Kết quả OFFSET trùng ROW_NUMBER (tập dòng, tổng, chuỗi khoá sắp xếp từng trang). Thứ tự các dòng TRÙNG khoá sắp xếp (cùng ngày + cùng số CT) vốn không cố định ở cả 2 cách — chưa thêm `PR_KEY_LEDGER` làm khoá phụ.
- **Đồng hồ đo:** response `/api/ledger` có header `Server-Timing` (`count`, `page`, `build`, `json`, `total`, `gzip` — ms; `mode;desc="offset+parallel"` — dùng dấu `+`, KHÔNG dùng dấu phẩy vì dấu phẩy tách các mục header). App ghép thêm chờ/tải/vẽ, hiện ở thanh trạng thái khi đứng ở tab sổ cái: "Truy vấn x s (SQL · tải · vẽ)", rê chuột xem đủ từng khâu. Trum gửi số này là biết khâu nào còn chậm.
- **Đừng đo tốc độ SQL trên máy dev.** Máy có SQL Server 2016 Express (`localhost\SQLEXPRESS`, Windows auth; DB demo `TRUNGDEMO`, `SALE_DEMO`, `BIMGROUP` có bảng `LEDGER` chuẩn iPOS: PK clustered `PR_KEY_LEDGER` + index `TRAN_DATE`, `ACCOUNT_ID`…) nhưng RAM trống chỉ ~0,4–1 GB → SQL tự co còn ~132 MB, truy vấn sắp xếp vài nghìn dòng đã chờ cấp bộ nhớ (`RESOURCE_SEMAPHORE`) hàng trăm giây. Dùng nó để kiểm **tính đúng** với khoảng ngày nhỏ (vd 2024–2026 của TRUNGDEMO = 176 dòng), vá `_make_conn` sang Windows auth trong script test (NHAT_KY mục 20). 27/09 đã thử dựng DB 2,5 triệu dòng — kẹt ở tạo khoá chính, đã xoá.
- **Bước tiếp nếu SQL lấy trang vẫn chậm:** sắp xếp chỉ cột khoá hẹp rồi mới lấy đủ cột cho 10.000 dòng (cần `PR_KEY_LEDGER`, tra `sys.indexes` trước khi dùng — Bẫy 5), hoặc index do DBA quyết. Chưa làm — chờ số đo thật.

### Bẫy 21: Bộ lọc nâng cao (panel "Bộ lọc khác", v1.9.3)
- `FilterConfigurator` (định nghĩa ở cấp trên cùng, KHÔNG trong App — tránh gỡ-lắp lại mỗi lần App vẽ) nhận `items: [{ key, label, active, clear, node }]`: `node` là JSX ô lọc CŨ của tab (props/handler giữ nguyên), `active` = đang có giá trị, `clear` = hàm xoá giá trị. Ô trong `defaultOutside` (= hàng chính cũ) hiện ngoài thanh lọc; còn lại nằm trong panel. Kỳ + ô ngày luôn cố định, không nằm trong items.
- Thêm ô lọc mới cho một tab: thêm 1 phần tử vào mảng `items` của tab đó (key duy nhất, dạng `filters.xxx` / `saleFilters.xxx`). Máy nào đã lưu cấu hình thì ô mới tự nối cuối danh sách, nằm trong panel.
- Cấu hình nhớ theo tab: `localStorage['ds_filters_<tab>'] = { order, outside }`; mở/thu phần cấu hình: `ds_filters_cfg_open`. Tối đa `FILTER_OUT_MAX = 4` ô ra ngoài (ô thứ 5 khoá công tắc). "Xoá tất cả" chỉ xoá các ô đang nằm trong panel. "Lọc" = đóng panel + gọi đúng hàm Truy vấn của tab (sổ cái: đếm lại tổng).
- Panel `position: fixed` tính theo nút (không bị khung cha cắt), popup của ô lọc trong lưới được tràn ra ngoài panel; cột thứ 3 của lưới ép popup canh phải (CSS `.ds-afp-grid > :nth-child(3n) .ds-pop`).
- Kéo đổi thứ tự dùng `dragRef` (ref), không dùng state: `dragover` tới liền sau `dragstart`, state chưa kịp cập nhật → kéo không ăn. DataTransfer chỉ set kiểu riêng `application/x-ds-filter` — KHÔNG set `text/plain`, không thì thả nhầm vào vùng "Gom nhóm" của bảng sẽ thêm cột rác.

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

# Chạy build script tự động tăng version (tự dịch sẵn giao diện vào build_web/ trước — cần Node, xem Bẫy 14)
python build_exe.py
```

### Bước 4: Kiểm tra File Output
- Verify mtime + dung lượng (~16,5 MB từ v1.9.2 — React/xlsx/font + ảnh sóc 77 KB đóng kèm) của `dist/iPOS_Ledger_Studio.exe`; chạy thử `/api/version` ra đúng `version.txt`.

### Bước 5: Phát hành bản cập nhật (chỉ khi Trum bảo)
```bash
# 1. Đẩy mã nguồn đúng bản vừa build
git remote get-url origin          # phải ra .../ledgerstudio.git
git add -A && git commit -m "vX.Y.Z: ..." && git push origin main
# 2. TẠO LẠI ZIP từ EXE vừa build — build_exe.py KHÔNG làm zip; dist/*.zip để lại là zip của bản trước
python -c "import zipfile; z=zipfile.ZipFile(r'dist/iPOS_Ledger_Studio.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9); z.write(r'dist/iPOS_Ledger_Studio.exe','iPOS_Ledger_Studio.exe'); z.close()"
# 3. Release: tag = version.txt, asset tên ĐÚNG iPOS_Ledger_Studio.exe (+ .zip cho người tải tay)
gh release create vX.Y.Z dist/iPOS_Ledger_Studio.exe dist/iPOS_Ledger_Studio.zip --repo trungkhanhduong93/ledgerstudio --target <SHA đầy đủ hoặc main> --title "DataStudio vX.Y.Z (iPOS Ledger Studio)" --notes-file notes.md
```
- Máy đang chạy bản ≥ v1.8.3 thấy banner ở lần mở app kế tiếp. Máy còn bản ≤ v1.8.2 (chưa có updater) phải tải tay 1 lần.
- **Zip cũ suýt lên release (27/09/2026):** `dist/iPOS_Ledger_Studio.zip` còn là bản v1.8.5 từ 17/09 — người tải tay sẽ nhận bản cũ mà không ai biết. Luôn so mtime/kích thước zip với EXE trước khi `gh release create`.
- Phát hành xong kiểm như app kiểm: `GET https://api.github.com/repos/trungkhanhduong93/ledgerstudio/releases/latest` (không đăng nhập) → `tag_name` đúng, asset `iPOS_Ledger_Studio.exe` có `digest` = SHA-256 file vừa build. Muốn chắc chắn máy cũ lên được: tải EXE release trước (`gh release download vA.B.C --pattern iPOS_Ledger_Studio.exe`) vào thư mục tạm, chạy, bấm "Cập nhật ngay" (NHAT_KY mục 19).

---

> 🔴 **CẤM:** push lên remote nào khác `trungkhanhduong93/ledgerstudio` · push nhánh local `lich-su-truoc-17-09` hoặc `git push --all` · `push --force` / viết lại lịch sử khi Trum chưa bảo · commit mật khẩu, IP server DB, file dữ liệu khách.
