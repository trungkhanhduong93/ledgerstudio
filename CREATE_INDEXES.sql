/* =========================================================================
   iPOS Ledger Studio — SQL Indexes tối ưu hiệu năng
   Chạy MỘT LẦN trong SQL Server Management Studio (kết nối database IACC)

   Các index này cover các query chính của app:
     - Truy vấn sổ cái (ledger) theo TRAN_DATE DESC + các filter
     - COUNT + SUM theo TRAN_DATE, ORGANIZATION_ID, ACCOUNT_ID
     - Báo cáo theo ACCOUNT_ID + DEBIT_CREDIT
   ========================================================================= */

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- 1) Index chính: sort theo TRAN_DATE DESC + TRAN_NO (dùng cho ORDER BY trong /api/ledger)
--    INCLUDE các cột hay dùng để tránh key lookup
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LEDGER_TRAN_DATE_NO')
BEGIN
    CREATE NONCLUSTERED INDEX IX_LEDGER_TRAN_DATE_NO
        ON dbo.LEDGER (TRAN_DATE DESC, TRAN_NO)
        INCLUDE (
            TRAN_ID, DEBIT_CREDIT,
            ACCOUNT_ID, ACCOUNT_ID_CONTRA,
            PR_DETAIL_ID, DESCRIPTION, COMMENTS,
            AMOUNT, JOB_ID,
            ITEM_ID, PRODUCT_ID, EXPENSE_ID, ORGANIZATION_ID
        );
    PRINT 'Created IX_LEDGER_TRAN_DATE_NO';
END
GO

-- 2) Index cho filter theo ACCOUNT_ID + range date (dùng cho báo cáo KQKD)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LEDGER_ACC_DATE')
BEGIN
    CREATE NONCLUSTERED INDEX IX_LEDGER_ACC_DATE
        ON dbo.LEDGER (ACCOUNT_ID, TRAN_DATE)
        INCLUDE (ACCOUNT_ID_CONTRA, DEBIT_CREDIT, AMOUNT, ORGANIZATION_ID, JOB_ID);
    PRINT 'Created IX_LEDGER_ACC_DATE';
END
GO

-- 3) Index cho filter theo ORGANIZATION_ID + range date
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LEDGER_ORG_DATE')
BEGIN
    CREATE NONCLUSTERED INDEX IX_LEDGER_ORG_DATE
        ON dbo.LEDGER (ORGANIZATION_ID, TRAN_DATE);
    PRINT 'Created IX_LEDGER_ORG_DATE';
END
GO

-- 4) Index cho filter theo TRAN_ID (loại chứng từ)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LEDGER_TRAN_ID_DATE')
BEGIN
    CREATE NONCLUSTERED INDEX IX_LEDGER_TRAN_ID_DATE
        ON dbo.LEDGER (TRAN_ID, TRAN_DATE);
    PRINT 'Created IX_LEDGER_TRAN_ID_DATE';
END
GO

-- 5) Index trên TRAN_NO (column search "Số Chứng Từ" với trailing wildcard)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LEDGER_TRAN_NO')
BEGIN
    CREATE NONCLUSTERED INDEX IX_LEDGER_TRAN_NO
        ON dbo.LEDGER (TRAN_NO)
        INCLUDE (TRAN_DATE);
    PRINT 'Created IX_LEDGER_TRAN_NO';
END
GO

-- 6) Cập nhật statistics cho optimizer chọn plan tối ưu
UPDATE STATISTICS dbo.LEDGER WITH FULLSCAN;
GO

PRINT '==== DONE: Indexes đã được tạo/ kiểm tra ====';
PRINT 'Khởi động lại iPOS_Ledger_Studio để bắt đầu tận dụng index mới.';
