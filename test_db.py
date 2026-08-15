import sqlite3
conn = sqlite3.connect('sitemapseo.db')
cursor = conn.cursor()
cursor.execute("SELECT phrase FROM keywords ORDER BY id DESC LIMIT 20;")
rows = cursor.fetchall()
for row in rows:
    print(row[0])
