# -*- coding: utf-8 -*-
"""
xlsx_report.py — ENGINE XUẤT BÁO CÁO KẾ TOÁN (BC005–BC013) RA .XLSX GIỐNG FORM TRÊN APP, kèm CSV thô.

Vì sao có file này (09/2026):
  Trước đây báo cáo xuất ".xls" dạng HTML-mso dựng từ DOM: Excel mở lên luôn cảnh báo sai định dạng,
  báo cáo có phân trang phải nạp HẾT dòng vào DOM (vài chục nghìn dòng là treo), Nhật ký chung chỉ
  xuất được CSV thô, và thanh tiến trình là số giả chạy theo setTimeout. Giờ mọi báo cáo đi qua 1 engine
  xlsxwriter chạy NỀN ở server:
    - file .xlsx thật, style mô phỏng đúng bảng đang hiển thị trên app (đậm/nghiêng/nền/viền/canh lề/thụt lề);
    - ô tiền lưu SỐ THẬT (1000000), hiển thị #,##0 — âm trong ngoặc, 0 là "-" y hệt formatNum() trên app;
    - tỷ lệ % lưu 0.1552, hiển thị 15.52% (giữ đúng số chữ số thập phân đang hiện);
    - ngày lưu kiểu NGÀY thật, hiển thị dd/mm/yyyy; mã TK/số HĐ lưu CHUỖI (không mất số 0 đầu);
    - constant_memory: ghi hàng triệu dòng mà RAM không phình;
    - chạm SHEET_DATA_ROWS dòng thì tự sang sheet mới, sheet nào cũng đủ tiêu đề + đầu bảng, có dòng
      "Cộng chuyển sang sheet sau" / "Số cộng sheet trước chuyển sang" để số liệu nối liền.

Module KHÔNG phụ thuộc Flask/pyodbc → test độc lập được bằng dữ liệu giả.
Phần truy vấn SQL (BC007/BC008/BC012/BC013) nằm ở server.py, chỉ đẩy từng dòng vào writer ở đây.

⚠️ constant_memory bắt buộc ghi THEO THỨ TỰ DÒNG: đã sang dòng r+1 thì mọi lệnh ghi vào dòng r bị bỏ qua
   IM LẶNG. Vì vậy ô gộp NHIỀU DÒNG ở đầu bảng (rowspan) không dùng merge_range (nó ghi ô trống xuống dòng
   dưới trước khi dòng trên ghi xong) mà ghi tay từng ô rồi khai báo vùng gộp — xem _write_table_header.
"""
import math
import os
from datetime import datetime, date
from decimal import Decimal

import xlsxwriter

EXCEL_MAX_ROWS = 1048576
# Ngưỡng tách sheet = số dòng BẢNG tối đa trong 1 sheet. Trần Excel là 1.048.576 dòng; chừa ~48 nghìn dòng
# cho khối tiêu đề, đầu bảng, dòng chuyển sang và phần chữ ký.
SHEET_DATA_ROWS = 1000000
PROGRESS_EVERY = 2000

FONT = 'Arial'

# Bảng màu Tailwind mà trang báo cáo trên app đang dùng
BLACK = '#000000'
SLATE_50 = '#F8FAFC'
SLATE_100 = '#F1F5F9'
SLATE_200 = '#E2E8F0'
SLATE_300 = '#CBD5E1'
SLATE_400 = '#94A3B8'
SLATE_500 = '#64748B'
SLATE_600 = '#475569'
SLATE_900 = '#0F172A'
INDIGO_50 = '#EEF2FF'
INDIGO_200 = '#C7D2FE'
INDIGO_300 = '#A5B4FC'
INDIGO_700 = '#4338CA'
SLATE_100_80 = '#F4F7FA'   # bg-slate-100/80 trộn trên nền trắng

# Giống formatNum() trên app: dương 1,234 · âm (1,234) · bằng 0 hiện "-"
NUM_FMT = '#,##0;(#,##0);"-"'
DATE_FMT = 'dd/mm/yyyy'


class ExportCancelled(Exception):
    """Người dùng bấm Hủy giữa chừng."""


class Col:
    """1 cột của bảng.
    kind: text | code | num | int | date | pct
      code — mã TK/đơn vị/số HĐ: ghi CHUỖI, giữ số 0 đầu
      num  — tiền: ghi SỐ THẬT, hiển thị NUM_FMT
      pct  — nhận giá trị theo ĐƠN VỊ % (10 nghĩa là 10%) → ghi 0.1, hiển thị 10%
      date — nhận datetime/date hoặc chuỗi dd/mm/yyyy → ghi NGÀY THẬT
      int  — số thứ tự
    indent=True: cột nhận thụt lề theo kiểu dòng (tên chỉ tiêu).
    carry=True : cột được cộng dồn cho dòng "Cộng chuyển sang sheet sau" khi phải tách sheet."""
    __slots__ = ('header', 'width', 'kind', 'align', 'bold', 'wrap', 'indent', 'carry')

    def __init__(self, header, width, kind='text', align=None, bold=False, wrap=False, indent=False, carry=False):
        self.header = header
        self.width = width
        self.kind = kind
        self.align = align or {'num': 'right', 'code': 'center', 'int': 'center',
                               'date': 'center', 'pct': 'center'}.get(kind, 'left')
        self.bold = bold
        self.wrap = wrap
        self.indent = indent
        self.carry = carry


class Span:
    """Ô nhãn gộp n cột liền nhau (Tổng cộng, Cộng phát sinh, Tài khoản ...).
    upper=None: viết hoa theo kiểu dòng; True/False: ép riêng ô này (vd "Số dư đầu kỳ:" của BC012 không viết hoa)."""
    __slots__ = ('text', 'n', 'align', 'upper')

    def __init__(self, text, n, align='right', upper=None):
        self.text = text
        self.n = n
        self.align = align
        self.upper = upper


class Layout:
    """Mô tả 1 báo cáo: cột + đầu bảng + kiểu dòng + chữ ký + trang in. `info` là khối tiêu đề do app gửi lên.

    header: list các dòng đầu bảng, mỗi ô (text, colspan, rowspan) — xếp chỗ y như <thead> HTML.
    row_styles: tên kiểu → thuộc tính: bold (None = theo cột), italic, color, bg, indent,
                upper (viết hoa nhãn), top (độ dày viền trên), top_color, noborder.
    row_height: None = để Excel tự căn (bảng lớn, nhanh); số = chiều cao tối thiểu + tự nới khi chữ xuống dòng.
    """

    def __init__(self, code, sheet_name, columns, header, info, row_styles=None, landscape=False,
                 border_color=BLACK, signature='standard', row_height=None,
                 carry_out_label='Cộng chuyển sang sheet sau', carry_in_label='Số cộng sheet trước chuyển sang',
                 continue_rows=None):
        self.code = code
        self.sheet_name = sheet_name
        self.columns = columns
        self.header = header
        self.info = info or {}
        self.row_styles = {'data': {}, 'carry': {'bold': True, 'italic': True, 'bg': SLATE_50, 'upper': False}}
        self.row_styles.update(row_styles or {})
        self.landscape = landscape
        self.border_color = border_color
        self.signature = signature
        self.row_height = row_height
        self.carry_out_label = carry_out_label
        self.carry_in_label = carry_in_label
        # continue_rows(last_meta) -> list[(values, style)]: dòng mở đầu sheet nối tiếp (vd BC012 "Tài khoản X (tiếp theo)")
        self.continue_rows = continue_rows


# ---------------------------------------------------------------------------------------------------------
# Chuyển giá trị
# ---------------------------------------------------------------------------------------------------------
def _to_float(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        x = float(v)
        return x if math.isfinite(x) else None
    return None


def _pct_decimals(x):
    """Số chữ số thập phân đang hiện của 1 tỷ lệ theo đơn vị % (15.52 → 2, 10 → 0), tối đa 4."""
    s = f"{abs(x):.4f}".rstrip('0').rstrip('.')
    return len(s.split('.')[1]) if '.' in s else 0


def _to_date(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        s = v.strip()
        if len(s) == 10 and s[2] == '/' and s[5] == '/':
            try:
                return datetime.strptime(s, '%d/%m/%Y')
            except ValueError:
                return None
    return None


def _text_units(text, bold=False):
    """Ước lượng bề rộng chuỗi theo đơn vị cột Excel (≈ bề rộng chữ '0' Arial 10) — để tính số dòng khi xuống dòng
    và chọn chỗ đặt chữ ký. Hoa ~1.05, thường ~0.8, số 1.0, khoảng trắng/dấu ~0.4."""
    u = 0.0
    for ch in text:
        if ch.isupper():
            u += 1.05
        elif ch.isdigit():
            u += 1.0
        elif ch.isalpha():
            u += 0.8
        else:
            u += 0.42
    return u * (1.08 if bold else 1.0)


def _num_text(x):
    """Số cho CSV: 1000000 (không .0), còn lẻ thì giữ tối đa 4 chữ số."""
    if float(x).is_integer():
        return str(int(x))
    return repr(round(float(x), 4))


def _signature_date():
    now = datetime.now()   # máy người dùng chạy app → giờ địa phương (GMT+7)
    return now.day, now.month, now.year


# ---------------------------------------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------------------------------------
class XlsxReportWriter:
    def __init__(self, path, layout, total_rows=0, progress=None, is_cancelled=None, sheet_limit=None):
        self.path = path
        self.L = layout
        self.cols = layout.columns
        self.ncols = len(layout.columns)
        self.limit = sheet_limit or SHEET_DATA_ROWS
        self.total_rows = max(0, int(total_rows or 0))
        self.expected_sheets = max(1, math.ceil(self.total_rows / self.limit)) if self.total_rows else 1
        self.progress = progress
        self.is_cancelled = is_cancelled
        self.rows_written = 0
        self.sheet_count = 0

        self.wb = xlsxwriter.Workbook(path, {
            'constant_memory': True,
            'strings_to_numbers': False, 'strings_to_formulas': False, 'strings_to_urls': False,
        })
        if self.total_rows > 300000:
            # file XML 1 sheet có thể vượt 4 GB khi giải nén → không bật ZIP64 thì close() ném FileSizeError
            self.wb.use_zip64()
        info = layout.info
        self.wb.set_properties({
            'title': (info.get('title') or '').strip(),
            'subject': (info.get('period_text') or '').strip(),
            'company': (info.get('company_name') or '').strip(),
            'author': 'iPOS Ledger Studio',
            'comments': 'Xuất từ iPOS Ledger Studio',
        })
        self._fmt_cache = {}
        self._row_fmts = {}
        self._span_fmts = {}
        self._pct_fmts = {}
        self._carry_idx = [i for i, c in enumerate(self.cols) if c.carry]
        self._carry = {i: Decimal(0) for i in self._carry_idx}
        self._ws = None
        self._row = 0
        self._sheet_rows = 0
        self._last_meta = None

    # ---------- định dạng ----------
    def _f(self, **props):
        key = tuple(sorted(props.items()))
        fmt = self._fmt_cache.get(key)
        if fmt is None:
            p = {'font_name': FONT, 'font_size': 10}
            p.update(props)
            fmt = self._fmt_cache[key] = self.wb.add_format(p)
        return fmt

    def _style(self, name):
        rs = self.L.row_styles.get(name)
        if rs is None:
            raise KeyError(f"Kiểu dòng '{name}' chưa khai báo cho {self.L.code}")
        return rs

    def _cell_props(self, col, rs, kind=None, align=None):
        p = {'valign': 'vcenter'}
        if not rs.get('noborder'):
            p['border'] = 1
            p['border_color'] = self.L.border_color
            if rs.get('top'):
                p['top'] = rs['top']
                p['top_color'] = rs.get('top_color', self.L.border_color)
        bold = rs.get('bold')
        if bold is None:
            bold = col.bold
        if bold:
            p['bold'] = True
        if rs.get('italic'):
            p['italic'] = True
        if rs.get('color'):
            p['font_color'] = rs['color']
        if rs.get('bg'):
            p['bg_color'] = rs['bg']
        if rs.get('size'):
            p['font_size'] = rs['size']
        p['align'] = align or col.align
        kind = kind or col.kind
        if kind == 'num':
            p['num_format'] = NUM_FMT
        elif kind == 'int':
            p['num_format'] = '0'
        elif kind == 'date':
            p['num_format'] = DATE_FMT
        elif kind == 'code':
            p['num_format'] = '@'
        if col.wrap and kind == 'text':
            p['text_wrap'] = True
        if col.indent and rs.get('indent'):
            p['indent'] = rs['indent']
        return p

    def _fmts_for(self, style):
        fm = self._row_fmts.get(style)
        if fm is None:
            rs = self._style(style)
            fm = self._row_fmts[style] = [self._f(**self._cell_props(c, rs)) for c in self.cols]
        return fm

    def _span_fmt(self, style, col_idx, align):
        key = (style, col_idx, align)
        fmt = self._span_fmts.get(key)
        if fmt is None:
            rs = self._style(style)
            p = self._cell_props(self.cols[col_idx], rs, kind='text', align=align)
            p.pop('text_wrap', None)
            p.pop('num_format', None)
            if rs.get('indent') and align == 'left':
                p['indent'] = rs['indent']
            fmt = self._span_fmts[key] = self._f(**p)
        return fmt

    def _pct_fmt(self, style, col_idx, dec):
        key = (style, col_idx, dec)
        fmt = self._pct_fmts.get(key)
        if fmt is None:
            p = self._cell_props(self.cols[col_idx], self._style(style), kind='pct')
            p['num_format'] = '0%' if dec == 0 else '0.' + '0' * dec + '%'
            fmt = self._pct_fmts[key] = self._f(**p)
        return fmt

    # ---------- sheet ----------
    def _sheet_name(self, idx):
        base = ''.join('_' if ch in '[]:*?/\\' else ch for ch in (self.L.sheet_name or self.L.code))[:25]
        if idx == 1 and self.expected_sheets == 1:
            return base
        return f"{base} ({idx})"

    def _merge(self, r, c1, c2, text, fmt):
        if c2 > c1:
            self._ws.merge_range(r, c1, r, c2, text, fmt)
        elif text:
            self._ws.write_string(r, c1, text, fmt)
        else:
            self._ws.write_blank(r, c1, None, fmt)

    def _new_sheet(self):
        self.sheet_count += 1
        idx = self.sheet_count
        L, info, n = self.L, self.L.info, self.ncols
        ws = self._ws = self.wb.add_worksheet(self._sheet_name(idx))
        self._row = 0
        self._sheet_rows = 0

        # Trang in: A4, đúng hướng giấy như trên app, vừa 1 trang ngang, lặp đầu bảng mỗi trang
        ws.set_paper(9)
        if L.landscape:
            ws.set_landscape()
        else:
            ws.set_portrait()
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.35, right=0.35, top=0.5, bottom=0.6)
        ws.center_horizontally()
        ws.set_footer('&C&"Arial,Italic"&8Trang &P / &N')
        ws.hide_gridlines(2)   # nền trắng như tờ báo cáo trên app, chỉ bảng có viền
        ws.ignore_errors({'number_stored_as_text': 'A1:XFD1048576'})
        for i, c in enumerate(self.cols):
            ws.set_column(i, i, c.width)

        # ---- Khối tiêu đề (giống .report-paper) ----
        r = 0
        ws.set_row(r, 17)
        ws.write_string(r, 0, (info.get('company_name') or '').upper(), self._f(bold=True, font_size=11))
        form_code = (info.get('form_code') or '').strip()
        if form_code:
            k = 2 if n >= 6 else 1
            self._merge(r, n - k, n - 1, form_code.upper(),
                        self._f(bold=True, italic=True, underline=1, font_color=SLATE_400, align='right'))
        r += 1
        if info.get('company_line'):
            ws.write_string(r, 0, info['company_line'], self._f(italic=True, font_size=9, font_color=SLATE_500))
            r += 1
        if info.get('unit_line'):
            ws.write_string(r, 0, info['unit_line'].upper(), self._f(bold=True, font_size=9, font_color=SLATE_500))
            r += 1
        ws.set_row(r, 9)
        r += 1
        ws.set_row(r, 27)
        self._merge(r, 0, n - 1, (info.get('title') or '').upper(),
                    self._f(bold=True, font_size=16, font_color=SLATE_900, align='center', valign='vcenter'))
        r += 1
        for line in info.get('sub_lines') or []:
            ws.set_row(r, 15)
            self._merge(r, 0, n - 1, str(line).upper(),
                        self._f(bold=True, font_color=SLATE_600, align='center', valign='vcenter'))
            r += 1
        if idx > 1:
            part = f"phần {idx}/{self.expected_sheets}" if idx <= self.expected_sheets else f"phần {idx}"
            self._merge(r, 0, n - 1, f"(Tiếp theo sheet trước — {part})",
                        self._f(italic=True, font_size=9, font_color=SLATE_500, align='center'))
            r += 1
        if info.get('period_text'):
            ws.set_row(r, 16)
            self._merge(r, 0, n - 1, info['period_text'].upper(),
                        self._f(bold=True, font_size=11, font_color=INDIGO_700, align='center', valign='vcenter'))
            r += 1
        if info.get('uom_text'):
            self._merge(r, 0, n - 1, info['uom_text'],
                        self._f(italic=True, font_size=9, font_color=SLATE_500, align='center'))
            r += 1
        ws.set_row(r, 8)
        r += 1

        self._row = r
        h_first = r
        self._write_table_header()
        h_last = self._row - 1
        ws.repeat_rows(h_first, h_last)
        remaining = (self.total_rows - self.limit * (idx - 1)) if self.total_rows else 0
        if remaining > 40 or (not self.total_rows and idx > 1):
            ws.freeze_panes(self._row, 0)

    def _write_table_header(self):
        ws, n = self._ws, self.ncols
        top = self._row
        rows = self.L.header
        fmt = self._f(bold=True, font_size=9, align='center', valign='vcenter', text_wrap=True,
                      bg_color=SLATE_100, border=1, border_color=self.L.border_color)
        # Xếp ô giống thuật toán bảng HTML: ô bị rowspan phía trên chiếm chỗ thì nhảy qua
        grid = {}
        merges = []
        for ri, cells in enumerate(rows):
            c = 0
            for text, cs, rs in cells:
                while (ri, c) in grid:
                    c += 1
                for dr in range(rs):
                    for dc in range(cs):
                        grid[(ri + dr, c + dc)] = (ri, c)
                grid[('text', ri, c)] = (text, cs, rs)
                if cs > 1 or rs > 1:
                    merges.append((top + ri, c, top + ri + rs - 1, c + cs - 1))
                c += cs
        for ri in range(len(rows)):
            # chiều cao: ước lượng số dòng chữ của ô cao nhất (ô gộp không được Excel tự căn)
            lines = 1
            for c in range(n):
                t = grid.get(('text', ri, c))
                if t:
                    width = sum(self.cols[k].width for k in range(c, min(n, c + t[1])))
                    need = math.ceil(len(t[0]) * 1.15 / max(1.0, width - 1))
                    lines = max(lines, math.ceil(need / t[2]))
            ws.set_row(top + ri, max(18, 12 * lines + 6))
            for c in range(n):
                t = grid.get(('text', ri, c))
                if t:
                    ws.write_string(top + ri, c, str(t[0]).upper(), fmt)
                else:
                    ws.write_blank(top + ri, c, None, fmt)
        merge_list = getattr(ws, 'merge', None)   # danh sách vùng gộp nội bộ của xlsxwriter (3.x)
        for (r1, c1, r2, c2) in merges:
            # Khai báo vùng gộp SAU khi đã ghi đủ ô theo thứ tự dòng (constant_memory) — xem docstring đầu file.
            # Bản xlsxwriter sau này đổi cấu trúc nội bộ thì bỏ gộp (ô vẫn đủ chữ + viền), không làm hỏng file.
            if isinstance(merge_list, list):
                merge_list.append([r1, c1, r2, c2])
        self._row = top + len(rows)

    # ---------- ghi dòng ----------
    def add_row(self, values, style='data', meta=None):
        if self._ws is None:
            self._new_sheet()
        elif self._sheet_rows >= self.limit:
            self._split()
        self._write_values(values, style)
        self._sheet_rows += 1
        self.rows_written += 1
        if style == 'data' and self._carry_idx:
            for i in self._carry_idx:
                v = values[i] if i < len(values) else None
                if isinstance(v, Decimal):
                    self._carry[i] += v
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    self._carry[i] += Decimal(repr(v))
        self._last_meta = meta
        if self.rows_written % PROGRESS_EVERY == 0:
            self._tick()

    def _tick(self):
        if self.is_cancelled and self.is_cancelled():
            raise ExportCancelled()
        if self.progress:
            self.progress(self.rows_written, self.sheet_count, max(self.sheet_count, self.expected_sheets))

    def _row_height(self, values, style):
        base = self.L.row_height
        if not base:
            return None
        rs = self._style(style)
        lines = 1
        c = 0
        for v in values:
            if isinstance(v, Span):
                c += v.n
                continue
            if c < self.ncols:
                col = self.cols[c]
                if col.wrap and isinstance(v, str) and v:
                    bold = col.bold if rs.get('bold') is None else rs.get('bold')
                    units = _text_units(v, bold) + (1.4 * rs.get('indent', 0) if col.indent else 0)
                    lines = max(lines, math.ceil(units / max(1.0, col.width - 1.0)))
            c += 1
        return max(base, 13 * lines + 5)

    def _write_values(self, values, style):
        ws, r = self._ws, self._row
        h = self._row_height(values, style)
        if h:
            ws.set_row(r, h)
        fmts = self._fmts_for(style)
        cols = self.cols
        upper = self._style(style).get('upper')
        c = 0
        for v in values:
            if c >= self.ncols:
                break
            if isinstance(v, Span):
                c2 = min(self.ncols - 1, c + v.n - 1)
                text = v.text.upper() if (upper if v.upper is None else v.upper) else v.text
                self._merge(r, c, c2, text, self._span_fmt(style, c, v.align))
                c = c2 + 1
                continue
            col = cols[c]
            fmt = fmts[c]
            if v is None or v == '':
                ws.write_blank(r, c, None, fmt)
            else:
                kind = col.kind
                if kind == 'num' or kind == 'int':
                    x = _to_float(v)
                    if x is None:
                        ws.write_string(r, c, str(v), fmt)
                    else:
                        ws.write_number(r, c, round(x, 4) if kind == 'num' else x, fmt)
                elif kind == 'pct':
                    x = _to_float(v)
                    if x is None:
                        ws.write_string(r, c, str(v), fmt)
                    else:
                        dec = _pct_decimals(x)
                        # làm tròn theo đúng số chữ số đang hiện: 15.52/100 trần = 0.15519999999999998
                        ws.write_number(r, c, round(x / 100.0, dec + 2), self._pct_fmt(style, c, dec))
                elif kind == 'date':
                    d = _to_date(v)
                    if d is None:
                        ws.write_string(r, c, str(v), fmt)
                    else:
                        ws.write_datetime(r, c, d, fmt)
                else:
                    ws.write_string(r, c, str(v), fmt)
            c += 1
        while c < self.ncols:   # dòng thiếu ô → vẫn kẻ viền/tô nền đủ bảng
            ws.write_blank(r, c, None, fmts[c])
            c += 1
        self._row += 1

    def _carry_values(self, label):
        first = min(self._carry_idx)
        vals = [Span(label, first, 'right')] if first > 0 else []
        for i in range(first, self.ncols):
            vals.append(self._carry[i] if i in self._carry else None)
        return vals

    def _split(self):
        if self._carry_idx:
            self._write_values(self._carry_values(self.L.carry_out_label), 'carry')
        self._new_sheet()
        if self._carry_idx:
            self._write_values(self._carry_values(self.L.carry_in_label), 'carry')
        if self.L.continue_rows:
            for values, style in self.L.continue_rows(self._last_meta) or []:
                self._write_values(values, style)

    # ---------- chốt file ----------
    def _sign_groups(self):
        """Chia cột thành 3 nhóm liền nhau có BỀ RỘNG gần bằng nhau (như lưới 3 cột chữ ký trên app).
        Chia theo SỐ CỘT thì bảng ít cột bị lệch: BC005 [Chỉ tiêu | Mã số | Kỳ này | Kỳ trước] đặt "Kế toán
        trưởng" vào đúng cột Mã số hẹp 9 ký tự → chữ bị cắt cụt (đã thấy khi mở bằng Excel)."""
        w = [c.width for c in self.cols]
        n, total = len(w), sum(w)
        best = None
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                g = (sum(w[:i]), sum(w[i:j]), sum(w[j:]))
                score = max(abs(x - total / 3) for x in g) + sum(1000 for x in g if x < 17)
                if best is None or score < best[0]:
                    best = (score, i, j)
        _, i, j = best
        return [(0, i - 1), (i, j - 1), (j, n - 1)]

    def _rich_cell(self, r, a, b, parts, cell_fmt):
        """Ô (gộp a..b) chứa nhiều đoạn chữ khác định dạng. parts = [(format, text), ...]."""
        if b > a:
            self._ws.merge_range(r, a, r, b, '', cell_fmt)
        args = []
        for fmt, text in parts:
            if text:   # Excel không nhận đoạn rỗng trong rich string
                args += [fmt, text]
        self._ws.write_rich_string(r, a, *args, cell_fmt)

    def _write_signature(self):
        """Khối chữ ký. Ngày + chức danh + "(Ký, họ tên)" nằm trong CÙNG 1 dòng (chữ nhiều định dạng, xuống dòng
        trong ô): để 3 dòng riêng thì khi bảng kết thúc sát cuối trang in, Excel ngắt trang giữa khối —
        "(Ký, họ tên)" rơi sang trang sau kèm đầu bảng lặp lại (đã thấy khi in thử bằng Excel)."""
        L, n = self.L, self.ncols
        widths = [c.width for c in self.cols]
        d, m, y = _signature_date()
        self._row += 1
        r = self._row
        f_cell = self._f(align='center', valign='top', text_wrap=True)
        if L.signature == 'vat':
            # nửa bên phải theo bề rộng
            acc, c1 = 0, n - 1
            for k in range(n):
                if acc >= sum(widths) / 2:
                    c1 = k
                    break
                acc += widths[k]
            self._ws.set_row(r, 32)
            self._rich_cell(r, c1, n - 1, [
                (self._f(italic=True, font_color=SLATE_600), f", Ngày {d} Tháng {m} Năm {y}\n"),
                (self._f(bold=True), 'Người nộp thuế (hoặc đại diện hợp pháp của người nộp thuế)'),
            ], f_cell)
            self._row = r + 6
            return
        if L.signature != 'standard':
            return
        place = (L.info.get('sign_place') or '').strip()
        date_text = f"{place + ', ' if place else ''}Ngày {d} Tháng {m} Năm {y}"
        titles = ['NGƯỜI LẬP BIỂU', 'KẾ TOÁN TRƯỞNG', 'GIÁM ĐỐC']
        f_date = self._f(italic=True, font_color=SLATE_400)
        f_title = self._f(bold=True)
        f_hint = self._f(italic=True, font_size=9, font_color=SLATE_300)
        if n < 3:
            self._ws.set_row(r, 44)
            self._rich_cell(r, 0, n - 1, [(f_date, date_text + '\n'), (f_title, '        '.join(titles) + '\n'),
                                          (f_hint, '(Ký, họ tên)')], f_cell)
            self._row = r + 7
            return
        groups = self._sign_groups()
        a3, b3 = groups[2]
        date_inline = _text_units(date_text) <= sum(widths[a3:b3 + 1]) - 1
        if not date_inline:
            # nhóm phải quá hẹp để ngày nằm 1 dòng: để ngày ở dòng riêng ngay trên, KHÔNG gộp, canh phải ở cột cuối
            # cho chữ tràn sang trái (vẫn trong bề rộng bảng). Chỉ gặp ở bảng ít cột (BC005/009/010) — vốn ngắn 1 trang.
            self._ws.write_string(r, n - 1, date_text, self._f(italic=True, font_color=SLATE_400, align='right'))
            r += 1
        self._ws.set_row(r, 44 if date_inline else 30)
        for k, ((a, b), t) in enumerate(zip(groups, titles)):
            parts = []
            if date_inline:
                # nhóm 1-2 chèn 1 dòng trống cho chức danh thẳng hàng với nhóm 3 (có dòng ngày phía trên)
                parts.append((f_date, date_text + '\n') if k == 2 else (f_date, '\n'))
            parts += [(f_title, t + '\n'), (f_hint, '(Ký, họ tên)')]
            self._rich_cell(r, a, b, parts, f_cell)
        self._row = r + 6

    def close(self, after_rows=None):
        if self._ws is None:
            self._new_sheet()
        if after_rows:
            self._row += 1
            for values, style in after_rows:
                self._write_values(values, style)
        self._write_signature()
        if self.progress:
            self.progress(self.rows_written, self.sheet_count, self.sheet_count)
        self.wb.close()

    def abort(self):
        """Hủy/lỗi giữa chừng: xlsxwriter chưa đóng thì chưa tạo file đích, chỉ dọn file tạm từng sheet."""
        for ws in self.wb.worksheets():
            fh = getattr(ws, 'row_data_fh', None)
            fn = getattr(ws, 'row_data_filename', None)
            try:
                if fh:
                    fh.close()
            except Exception:
                pass
            try:
                if fn and os.path.exists(fn):
                    os.remove(fn)
            except Exception:
                pass


# ---------------------------------------------------------------------------------------------------------
# CSV thô — cùng dữ liệu, cùng thứ tự dòng, không có khối tiêu đề (mở thẳng bằng Excel, BOM UTF-8)
# ---------------------------------------------------------------------------------------------------------
def _csv_cell(s):
    s = '' if s is None else str(s)
    if any(ch in s for ch in (',', '"', '\n', '\r')):
        return '"' + s.replace('"', '""') + '"'
    return s


class CsvReportWriter:
    def __init__(self, path, layout, total_rows=0, progress=None, is_cancelled=None, sheet_limit=None):
        self.path = path
        self.L = layout
        self.cols = layout.columns
        self.ncols = len(layout.columns)
        self.progress = progress
        self.is_cancelled = is_cancelled
        self.rows_written = 0
        self.sheet_count = 1
        self._buf = []
        self._fh = open(path, 'w', encoding='utf-8-sig', newline='')
        self._fh.write(','.join(_csv_cell(c.header) for c in self.cols) + '\r\n')

    def _line(self, values):
        out = []
        c = 0
        for v in values:
            if c >= self.ncols:
                break
            if isinstance(v, Span):
                out.append(_csv_cell(v.text))
                out.extend([''] * (v.n - 1))
                c += v.n
                continue
            col = self.cols[c]
            if v is None or v == '':
                out.append('')
            elif col.kind in ('num', 'int', 'pct'):
                x = _to_float(v)
                out.append(_csv_cell(v) if x is None else _num_text(x))
            elif col.kind == 'date':
                d = _to_date(v)
                out.append(d.strftime('%d/%m/%Y') if d else _csv_cell(v))
            elif col.kind == 'code':
                # ="..." để Excel giữ nguyên mã (không mất số 0 đầu) — cùng quy ước _csv_text_cell ở server.py
                s = str(v).strip()
                out.append(_csv_cell(f'="{s}"') if s else '')
            else:
                out.append(_csv_cell(v))
            c += 1
        out.extend([''] * max(0, self.ncols - len(out)))
        return ','.join(out[:self.ncols])

    def add_row(self, values, style='data', meta=None):
        self._buf.append(self._line(values))
        self.rows_written += 1
        if len(self._buf) >= PROGRESS_EVERY:
            self._flush()
            if self.is_cancelled and self.is_cancelled():
                raise ExportCancelled()
            if self.progress:
                self.progress(self.rows_written, 1, 1)

    def _flush(self):
        if self._buf:
            self._fh.write('\r\n'.join(self._buf) + '\r\n')
            self._buf.clear()

    def close(self, after_rows=None):
        for values, style in after_rows or []:
            self._buf.append(self._line(values))
        self._flush()
        self._fh.close()
        if self.progress:
            self.progress(self.rows_written, 1, 1)

    def abort(self):
        try:
            self._fh.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------------------------------------
# LAYOUT từng báo cáo — mô phỏng đúng bảng render trong ReportTab (index.html).
# Lưu ý đọc CSS: `.report-table th, .report-table td { color:#000 }` có độ ưu tiên (0,1,1) THẮNG các class
# màu chữ Tailwind (0,1,0) ⇒ trên màn hình chữ trong bảng luôn ĐEN dù JSX có ghi text-indigo-700;
# còn nền (bg-*), đậm (font-*), canh lề, viết hoa thì Tailwind vẫn ăn.
# ---------------------------------------------------------------------------------------------------------
_GROUP = {'bold': True, 'bg': SLATE_50}
_TOTAL_B06 = {'bold': True, 'bg': SLATE_50, 'upper': True, 'top': 2, 'top_color': INDIGO_200}


def layout_bc005(info):
    cols = [
        Col('Chỉ tiêu', 50, 'text', wrap=True, indent=True),
        Col('Mã số', 9, 'code'),
        Col('Kỳ này', 20, 'num'),
        Col('Kỳ trước', 20, 'num'),
    ]
    header = [[('Chỉ tiêu', 1, 1), ('Mã số', 1, 1), ('Kỳ này', 1, 1), ('Kỳ trước', 1, 1)]]
    styles = {'group': _GROUP, 'item': {'bold': False, 'indent': 1},
              'sub': {'bold': False, 'italic': True, 'indent': 2}}
    return Layout('BC005', 'Bảng cân đối kế toán', cols, header, info, styles, landscape=False, row_height=18)


def rows_bc005(payload):
    for r in payload.get('rows') or []:
        t = r.get('type')
        style = 'group' if t in ('section', 'group', 'total') else ('sub' if t == 'sub' else 'item')
        yield [r.get('name') or '', r.get('id') or '', r.get('closing'), r.get('opening')], style


def layout_bc006(info, is_bc011=False):
    V = 17 if is_bc011 else 18
    cols = [
        Col('Mã' if is_bc011 else 'Mã tài khoản', 18 if is_bc011 else 12, 'code', bold=is_bc011, wrap=is_bc011),
        Col('Tên đối tượng' if is_bc011 else 'Tên tài khoản', 30 if is_bc011 else 38, 'text',
            bold=is_bc011, wrap=True, indent=True),
        Col('Dư đầu kỳ - Nợ', V, 'num'), Col('Dư đầu kỳ - Có', V, 'num'),
        Col('Phát sinh trong kỳ - Nợ', V, 'num'), Col('Phát sinh trong kỳ - Có', V, 'num'),
        Col('Dư cuối kỳ - Nợ', V, 'num'), Col('Dư cuối kỳ - Có', V, 'num'),
    ]
    row1 = [('Mã' if is_bc011 else 'Mã tài khoản', 1, 2), ('Tên đối tượng' if is_bc011 else 'Tên tài khoản', 1, 2),
            ('Dư đầu kỳ', 2, 1), ('Phát sinh trong kỳ', 2, 1), ('Dư cuối kỳ', 2, 1)]
    if is_bc011:
        cols.append(Col('TK', 8, 'code', bold=True))
        row1.append(('TK', 1, 2))
    header = [row1, [('Nợ', 1, 1), ('Có', 1, 1), ('Nợ', 1, 1), ('Có', 1, 1), ('Nợ', 1, 1), ('Có', 1, 1)]]
    if is_bc011:
        styles = {'total': _TOTAL_B06}
        return Layout('BC011', 'Tổng hợp công nợ', cols, header, info, styles, landscape=True, row_height=18)
    styles = {
        'parent': {'bold': True, 'bg': SLATE_50}, 'parent_i': {'bold': True, 'bg': SLATE_50, 'indent': 1},
        'child': {'bold': False}, 'child_i': {'bold': False, 'indent': 1},
        'total': _TOTAL_B06,
    }
    return Layout('BC006', 'Cân đối phát sinh', cols, header, info, styles, landscape=True, row_height=18)


_B06_KEYS = ('open_deb', 'open_crd', 'period_deb', 'period_crd', 'close_deb', 'close_crd')


def rows_bc006(payload, is_bc011=False):
    for r in payload.get('rows') or []:
        vals = [r.get('id') or '', r.get('name') or ''] + [r.get(k) or 0 for k in _B06_KEYS]
        if is_bc011:
            vals.append(r.get('acc') or '')
            yield vals, 'data'
        else:
            base = 'parent' if r.get('bold') else 'child'
            yield vals, (base + '_i' if r.get('indent') else base)
    total = payload.get('total')
    if total:
        vals = [Span('Tổng cộng', 2, 'right')] + [total.get(k) or 0 for k in _B06_KEYS]
        if is_bc011:
            vals.append(None)
        yield vals, 'total'


def layout_cash_flow(info, direct=True):
    # Mã số để rộng 18 (thừa so với mã 2 số) để chữ "KẾ TOÁN TRƯỞNG" nằm vừa cột giữa khi ký tên
    cols = [
        Col('Chỉ tiêu', 52, 'text', wrap=True, indent=True),
        Col('Mã số', 18, 'code'),
        Col('Kỳ này', 24, 'num'),
    ]
    header = [[('Chỉ tiêu', 1, 1), ('Mã số', 1, 1), ('Kỳ này', 1, 1)]]
    styles = {'group': _GROUP, 'plain': {'bold': True}, 'item': {'bold': False, 'indent': 1}}
    code = 'BC009' if direct else 'BC010'
    return Layout(code, 'LCTT trực tiếp' if direct else 'LCTT gián tiếp', cols, header, info, styles,
                  landscape=False, row_height=18)


def rows_cash_flow(payload):
    for r in payload.get('rows') or []:
        t = r.get('type')
        style = 'group' if t in ('section', 'total') else ('plain' if t == 'plain' else 'item')
        rid = r.get('id') or ''
        yield [r.get('name') or '', rid, r.get('value') if rid else None], style


def layout_bc007(info, view_mode='detail'):
    cols, head = [], []
    if view_mode == 'detail':
        cols += [Col('Đơn vị', 8, 'code', bold=True), Col('Tên đơn vị', 24, 'text'),
                 Col('Ngày tháng ghi sổ', 12, 'date')]
        head += [('Đơn vị', 1, 1), ('Tên đơn vị', 1, 1), ('Ngày tháng ghi sổ', 1, 1)]
    cols += [Col('Mã chứng từ', 10, 'code', bold=True), Col('Số hiệu chứng từ', 17, 'text', bold=True),
             Col('Ngày chứng từ', 12, 'date'), Col('Diễn giải', 50, 'text'),
             Col('TK', 9, 'code', bold=True), Col('TK ĐƯ', 9, 'code', bold=True),
             Col('Nợ', 18, 'num', bold=True, carry=True), Col('Có', 18, 'num', bold=True, carry=True)]
    head += [('Mã chứng từ', 1, 1), ('Số hiệu chứng từ', 1, 1), ('Ngày chứng từ', 1, 1), ('Diễn giải', 1, 1),
             ('TK', 1, 1), ('TK ĐƯ', 1, 1), ('Nợ', 1, 1), ('Có', 1, 1)]
    styles = {'total': {'bold': True, 'bg': SLATE_100, 'upper': True}}
    return Layout('BC007', 'Sổ nhật ký chung', cols, [head], info, styles, landscape=True)


def layout_bc007_full(info):
    specs = [('Bảng', 7, 'code', False), ('Mã đơn vị', 9, 'code', True), ('Tên đơn vị', 24, 'text', False),
             ('Công việc', 20, 'text', False), ('Mã chứng từ', 10, 'code', True), ('Ngày chứng từ', 12, 'date', False),
             ('Số chứng từ', 17, 'text', True), ('Diễn giải', 46, 'text', False), ('Tài khoản', 10, 'code', True),
             ('Tài khoản đối ứng', 10, 'code', True), ('Mã đối tượng', 14, 'code', False),
             ('Tên đối tượng', 28, 'text', False)]
    cols = [Col(h, w, k, bold=b) for h, w, k, b in specs]
    cols += [Col('Số tiền nợ', 18, 'num', bold=True, carry=True), Col('Số tiền có', 18, 'num', bold=True, carry=True),
             Col('Ghi chú', 24, 'text')]
    header = [[(c.header, 1, 1) for c in cols]]
    styles = {'total': {'bold': True, 'bg': SLATE_100, 'upper': True}}
    return Layout('BC007', 'Nhật ký chung đầy đủ', cols, header, info, styles, landscape=True)


def layout_bc008(info):
    cols = [Col('Ngày tháng ghi sổ', 12, 'date'), Col('Số hiệu chứng từ', 17, 'text', bold=True),
            Col('Ngày chứng từ', 12, 'date'), Col('Diễn giải', 46, 'text'),
            Col('TK ĐƯ', 9, 'code', bold=True),
            Col('Nợ', 18, 'num', bold=True, carry=True), Col('Có', 18, 'num', bold=True, carry=True)]
    header = [[(c.header, 1, 1) for c in cols]]
    styles = {
        'opening': {'bold': True, 'bg': SLATE_50},
        'total': {'bold': True, 'bg': SLATE_100, 'upper': True},
        'closing': {'bold': True, 'bg': SLATE_200},
    }
    return Layout('BC008', 'Sổ chi tiết tài khoản', cols, header, info, styles, landscape=False)


def _bc012_continue(meta):
    if meta and meta.get('t') == 'row':
        return [([Span(f"Tài khoản {meta.get('account_id', '')} (tiếp theo sheet trước)", 9, 'left')], 'head')]
    return []


def layout_bc012(info):
    cols = [Col('TT', 6, 'int'), Col('Ngày ghi sổ', 12, 'date'),
            Col('Số chứng từ - Nợ', 14, 'code', bold=True), Col('Số chứng từ - Có', 14, 'code', bold=True),
            Col('Diễn giải', 44, 'text'), Col('Tk đối ứng', 9, 'code', bold=True),
            Col('Số tiền - Nợ', 18, 'num'), Col('Số tiền - Có', 18, 'num'), Col('Số tiền - Dư', 18, 'num')]
    header = [
        [('TT', 1, 2), ('Ngày ghi sổ', 1, 2), ('Số chứng từ', 2, 1), ('Diễn giải', 1, 2), ('Tk đ/ư', 1, 2),
         ('Số tiền', 3, 1)],
        [('Nợ', 1, 1), ('Có', 1, 1), ('Nợ', 1, 1), ('Có', 1, 1), ('Dư', 1, 1)],
    ]
    styles = {
        'head': {'bold': True, 'bg': INDIGO_50, 'upper': True},
        'cong': {'bold': True, 'bg': SLATE_100, 'upper': True},
        'du': {'bold': True, 'bg': SLATE_200, 'upper': True},
        'grand': {'bold': True, 'bg': INDIGO_50, 'upper': True, 'top': 2, 'top_color': INDIGO_300},
    }
    return Layout('BC012', 'Sổ tiền mặt và ngân hàng', cols, header, info, styles, landscape=True,
                  continue_rows=_bc012_continue)


def rows_bc012(flat):
    """flat = kết quả _build_cashbook_flat (server.py) — cùng nguồn với bảng trên màn hình."""
    for r in flat:
        t = r.get('t')
        acc = r.get('account_id', '')
        if t == 'head':
            label = f"Tài khoản {acc}" + (f" - {r['account_name']}" if r.get('account_name') else '')
            yield [Span(label, 6, 'left'), Span('Số dư đầu kỳ:', 2, 'right', upper=False),
                   r.get('opening') or 0], 'head', r
        elif t == 'cong':
            yield [Span(f"Cộng phát sinh — TK {acc}", 6, 'right'), r.get('sum_deb') or 0, r.get('sum_crd') or 0,
                   None], 'cong', r
        elif t == 'du':
            yield [Span(f"Số dư cuối kỳ — TK {acc}", 6, 'right'), None, None, r.get('close') or 0], 'du', r
        elif t == 'grand':
            yield [Span('Tổng cộng tất cả tài khoản', 6, 'right'), r.get('period_deb') or 0,
                   r.get('period_crd') or 0, r.get('close') or 0], 'grand', r
        else:
            deb = r.get('debit') or 0
            crd = r.get('credit') or 0
            yield [r.get('stt'), r.get('tran_date'), r.get('tran_no') if deb > 0 else None,
                   r.get('tran_no') if crd > 0 else None, r.get('description') or '',
                   r.get('contra_account_id') or '', deb or None, crd or None, r.get('balance') or 0], 'data', r


def layout_bc013(info):
    cols = [Col('TT', 6, 'int'), Col('Ký hiệu hóa đơn', 11, 'code'), Col('Số hóa đơn', 11, 'code', bold=True),
            Col('Ngày phát hành', 12, 'date'), Col('Tên người mua', 28, 'text', wrap=True),
            Col('Mã số thuế người mua', 15, 'code'), Col('Mặt hàng', 30, 'text', wrap=True),
            Col('Doanh số bán chưa có thuế', 18, 'num', carry=True), Col('Thuế suất (%)', 9, 'pct'),
            Col('Thuế GTGT', 17, 'num', carry=True), Col('Ghi chú', 14, 'text', wrap=True)]
    header = [
        [('TT', 1, 2), ('Hóa đơn, chứng từ, biên lai nộp thuế', 3, 1), ('Tên người mua', 1, 2),
         ('Mã số thuế người mua', 1, 2), ('Mặt hàng', 1, 2), ('Doanh số bán chưa có thuế', 1, 2),
         ('Thuế suất (%)', 1, 2), ('Thuế GTGT', 1, 2), ('Ghi chú', 1, 2)],
        [('Ký hiệu hóa đơn', 1, 1), ('Số hóa đơn', 1, 1), ('Ngày phát hành', 1, 1)],
    ]
    styles = {
        'total': {'bold': True, 'bg': SLATE_100_80},
        'summary': {'noborder': True, 'bold': True, 'indent': 1},
    }
    return Layout('BC013', 'Bảng kê bán ra', cols, header, info, styles, landscape=True,
                  border_color=SLATE_300, signature='vat', row_height=16)


def bc013_summary_rows(totals):
    """3 dòng tổng dưới bảng kê (giống khối dưới bảng trên app) — số là ô SỐ, nằm dưới cột Doanh số."""
    items = [
        ('Tổng doanh thu hàng hoá dịch vụ bán ra:', totals.get('total_amount_item')),
        ('Tổng doanh thu hàng hoá dịch vụ bán ra chịu thuế GTGT:', totals.get('taxable_amount_item')),
        ('Thuế GTGT của hàng hoá dịch vụ bán ra:', totals.get('total_vat_amount')),
    ]
    return [([Span(label, 7, 'left'), value or 0], 'summary') for label, value in items]
