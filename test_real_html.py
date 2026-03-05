import sqlite3
import os
import re

db_path = os.path.join(os.getcwd(), 'convovault.db')
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT output_dir FROM history ORDER BY id DESC LIMIT 1")
row = cursor.fetchone()
if not row:
    print("No history found")
    exit()

output_dir = row[0]
print(f"Latest output dir: {output_dir}")

for file in os.listdir(output_dir):
    if file.endswith('.html') and file != 'index.html':
        file_path = os.path.join(output_dir, file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'(</div>\s*</div>\s*</body>)', content)
        if match:
            print(f"File {file}: Match Found! (First match at {match.start()} to {match.end()})")
        else:
            print(f"File {file}: NO MATCH")
            # Let's see the end of the file
            print("--- END OF FILE ---")
            print(content[-200:])
            print("-------------------")
        break
