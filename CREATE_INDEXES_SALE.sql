/* =========================================================================
   iPOS Ledger Studio — Index tăng tốc DANH SÁCH CHỨNG TỪ BÁN HÀNG (SALE_VIEW)
   Chạy MỘT LẦN trong SQL Server Management Studio (SSMS),
   ĐÃ CHỌN ĐÚNG DATABASE cần tối ưu (vd: IACC_IPOS2018) ở ô dropdown phía trên.

   SALE_VIEW = ghép dbo.SALE (đầu chứng từ) + dbo.SALE_DETAIL (dòng hàng)
   qua SALE.PR_KEY = SALE_DETAIL.FR_KEY, lọc theo SALE.TRAN_DATE.
   => 2 index then chốt: TRAN_DATE trên SALE, và FR_KEY trên SALE_DETAIL.

   *** CHẠY NGOÀI GIỜ LÀM VIỆC ***
   CREATE INDEX chạy OFFLINE (bản Standard) => KHOÁ bảng SALE_DETAIL suốt lúc
   build. Bảng vài chục triệu dòng có thể mất nhiều phút, POS/kế toán sẽ treo.
   Kiểm tra còn trống ổ đĩa (index này to gần bằng bảng chi tiết) và ổ log.
   ========================================================================= */

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* ----------------------------------------------------------------------
   BƯỚC 0 (TUỲ CHỌN) — Xem các index HIỆN CÓ để biết đang thiếu gì.
   Bôi đen riêng đoạn này rồi F5 để xem trước khi tạo.
---------------------------------------------------------------------- */
SELECT t.name AS bang, i.name AS ten_index, i.type_desc,
       STUFF((SELECT ',' + c.name
              FROM sys.index_columns ic
              JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
              WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
              ORDER BY ic.key_ordinal FOR XML PATH('')), 1, 1, '') AS cot_khoa
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
WHERE t.name IN ('SALE', 'SALE_DETAIL') AND i.type > 0
ORDER BY t.name, i.name;
GO

/* ----------------------------------------------------------------------
   1) SALE: index theo TRAN_DATE DESC + TRAN_NO (phục vụ lọc khoảng ngày
      và ORDER BY của danh sách). INCLUDE vài cột hay dùng để bớt key lookup.
      PR_KEY (khoá phân cụm) tự động có sẵn trong index => phục vụ JOIN.
---------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_SALE_TRAN_DATE_NO' AND object_id = OBJECT_ID('dbo.SALE')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_SALE_TRAN_DATE_NO
        ON dbo.SALE (TRAN_DATE DESC, TRAN_NO)
        INCLUDE (ORGANIZATION_ID, PR_DETAIL_ID, WAREHOUSE_ID, TRAN_ID);
    PRINT 'Created IX_SALE_TRAN_DATE_NO';
END
ELSE PRINT 'IX_SALE_TRAN_DATE_NO da ton tai - bo qua';
GO

/* ----------------------------------------------------------------------
   2) SALE_DETAIL: index trên FR_KEY (khoá JOIN đầu->dòng). ĐÂY LÀ INDEX
      QUAN TRỌNG NHẤT: thiếu nó thì mỗi đầu chứng từ phải quét toàn bộ
      bảng dòng => rất chậm.

      TẠO TRƯỚC — DROP SAU. Bản cũ tạo index rồi mới drop thì nếu CREATE lỗi
      (sai tên cột chẳng hạn) DB sẽ mất luôn index cũ, chậm hơn cả trước khi
      tối ưu. Ở đây tạo bản mới tên khác trước; chỉ khi nó tồn tại mới drop cũ.

      LƯU Ý: KHÔNG có ACCOUNT_ID_VAT trong SALE_DETAIL (cột đó nằm ở bảng SALE
      - đầu chứng từ). Đưa vào INCLUDE là câu CREATE fail ngay.
---------------------------------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_SALE_DETAIL_FR_KEY_COVER' AND object_id = OBJECT_ID('dbo.SALE_DETAIL')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_SALE_DETAIL_FR_KEY_COVER
        ON dbo.SALE_DETAIL (FR_KEY)
        INCLUDE (ITEM_ID, QUANTITY, AMOUNT, TOTAL_AMOUNT, COG_AMOUNT,
                 DISCOUNT_AMOUNT, VAT_TAX_AMOUNT, ACCOUNT_ID, EXPENSE_ID, JOB_ID,
                 ACCOUNT_ID_COST, UNIT_ID, UNIT_PRICE, VAT_TAX_RATE, ACCOUNT_ID_INCOME)
        WITH (SORT_IN_TEMPDB = ON);
    PRINT 'Created IX_SALE_DETAIL_FR_KEY_COVER (Covering Index)';
END
ELSE PRINT 'IX_SALE_DETAIL_FR_KEY_COVER da ton tai - bo qua';
GO

/* Chỉ dọn index FR_KEY cũ khi bản COVER đã tạo xong thành công. */
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_SALE_DETAIL_FR_KEY_COVER' AND object_id = OBJECT_ID('dbo.SALE_DETAIL')
)
AND EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_SALE_DETAIL_FR_KEY' AND object_id = OBJECT_ID('dbo.SALE_DETAIL')
)
BEGIN
    DROP INDEX IX_SALE_DETAIL_FR_KEY ON dbo.SALE_DETAIL;
    PRINT 'Dropped IX_SALE_DETAIL_FR_KEY (ban cu, da co ban COVER thay the)';
END
GO

/* ----------------------------------------------------------------------
   3) Cập nhật statistics để optimizer chọn plan đúng (rất quan trọng nếu
      dữ liệu vừa được nạp nhiều).
      SALE_DETAIL để mặc định (sampled): index vừa tạo đã có stats fullscan
      sẵn, ép FULLSCAN cả bảng chi tiết chỉ tốn thêm I/O.
---------------------------------------------------------------------- */
UPDATE STATISTICS dbo.SALE         WITH FULLSCAN;
UPDATE STATISTICS dbo.SALE_DETAIL;
GO

PRINT '==== XONG: Index ban hang da duoc tao/kiem tra ====';
PRINT 'Dong va mo lai iPOS_Ledger_Studio, bam Ctrl+F5, thu lai danh sach ban hang.';
GO
