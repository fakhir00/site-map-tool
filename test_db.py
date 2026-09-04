import sqlite3
import json

conn = sqlite3.connect('backend/sitemapseo.db')
c = conn.cursor()

# Get the latest project ID
c.execute("SELECT id, name, urls_found, urls_processed FROM projects ORDER BY created_at DESC LIMIT 5")
projects = c.fetchall()
print("Recent Projects:")
for p in projects:
    print(p)

if projects:
    pid = projects[0][0]
    c.execute("SELECT status, count(*) FROM urls WHERE project_id = ? GROUP BY status", (pid,))
    print(f"\nURL counts for {projects[0][1]}:")
    print(c.fetchall())
