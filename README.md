# 📊 iPOS Ledger Studio (`ledgerstudio`)

> **Hệ thống Phần mềm Báo cáo & Tra cứu Sổ sách Kế toán iPOS / IACC**
> **GitHub Repository:** [trungkhanhduong93/ledgerstudio](https://github.com/trungkhanhduong93/ledgerstudio)

---

## 📌 HƯỚNG DẪN DÀNH CHO CẢ NGƯỜI DÙNG & AGENT AI

Nếu bạn là **Lập trình viên** hoặc **Agent AI (Claude Code, Gemini, Antigravity, Cursor, Windsurf, ChatGPT)** được yêu cầu *"đọc toàn bộ file md hướng dẫn và kiến trúc"*, vui lòng truy cập ngay các file tài liệu chuẩn bên dưới:

1. **📘 [GEMINI.md](GEMINI.md) / [CLAUDE.md](CLAUDE.md)** — **NGUỒN SỰ THẬT DUY NHẤT:**
   - ⚡ **8 Nguyên tắc vàng vận hành** & Cây quyết định 3 giây.
   - 🏗️ **Tổng quan Kiến trúc Dự án** (Backend Flask, Frontend Single-file HTML React/Babel, SQL Server connection pool).
   - 📺 **Mô tả chi tiết 100% màn hình & tính năng** (Đăng nhập, 6 Tab dữ liệu thô, 9 Báo cáo A4/A4 ngang BC005–BC013).
   - 🐛 **Thư viện 10+ Bẫy Bug Thực tế & Cách Khắc phục** (Ghost server 5050, SQL param mismatch, `smalldatetime`, `exportFullXls`, `<colgroup>`, multi-account `_acc_like_sql`).
   - 🛠️ **Quy trình Dev, Test `test_client` & Build file EXE**.

2. **📖 [KIEN_TRUC_TOAN_TAP.md](KIEN_TRUC_TOAN_TAP.md)** — Sổ tay Kiến trúc Chi tiết & History Bàn giao Chi tiết.

---

## 📦 TẢI VỀ BẢN DỰ ÁN (.EXE)

Tải `iPOS_Ledger_Studio.exe` (hoặc bản `.zip`) ở trang **GitHub Releases**:
👉 [https://github.com/trungkhanhduong93/ledgerstudio/releases/latest](https://github.com/trungkhanhduong93/ledgerstudio/releases/latest)

Từ v1.8.3 app tự báo khi có bản mới và cập nhật ngay trong app. Tự build: chạy `BuildEXE-LedgerStudio.bat`, file ra ở `dist/`.