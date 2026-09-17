import pyodbc

conn_str = 'Driver={SQL Server};Server=.;Database=iPOS_ACC;Trusted_Connection=yes;'
try:
    conn = pyodbc.connect(conn_str, timeout=3)
    cursor = conn.cursor()
    cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'BALANCE_VIEW'")
    cols = [r[0] for r in cursor.fetchall()]
    print("BALANCE_VIEW columns:", cols)
except Exception as e:
    print("Error:", e)
