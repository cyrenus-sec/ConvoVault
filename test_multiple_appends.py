import sqlite3
import os
import re

db_path = os.path.join(os.getcwd(), 'convovault.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT output_dir FROM history ORDER BY id DESC LIMIT 1")
row = cursor.fetchone()
output_dir = row[0]

# Pick a real file
file_path = None
for file in os.listdir(output_dir):
    if file.endswith('.html') and file != 'index.html':
        file_path = os.path.join(output_dir, file)
        break

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

html_block = '<div class="message testing">Test</div>'

for i in range(3):
    match = re.search(r'(</div>\s*</div>\s*</body>)', content)
    if match:
        print(f"Iteration {i}: Match found at {match.start()} to {match.end()}")
        content = content[:match.start()] + html_block + "\n" + match.group(1) + content[match.end():]
    else:
        print(f"Iteration {i}: MATCH FAILED")
        break

print("Success!")
