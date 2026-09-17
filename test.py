import json, pyodbc
conf = json.load(open('config.json'))
conn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={conf["server"]};DATABASE={conf["database"]};UID={conf["uid"]};PWD={conf["pwd"]};Trusted_Connection=no;', timeout=5)
print([r.column_name for r in conn.cursor().columns(table='LEDGER') if 'CONTRA' in r.column_name.upper()])
