import sqlite3
import json
conn = sqlite3.connect('sitemapseo.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM hub_spoke_clusters;")
rows = cursor.fetchall()
for row in rows:
    print(row[0], row[2][:100]) # id, cluster_data
