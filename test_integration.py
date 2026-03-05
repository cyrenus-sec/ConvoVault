import sys
import os
import shutil
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# Initialize app properly for WebEngine
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)

import ConvoVault

# Create a mock instance
window = ConvoVault.ConvoVault()
window.llm_manager = None # Don't need real LLM

# Find latest DB output dir
import sqlite3
db_path = os.path.join(os.getcwd(), 'convovault.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT output_dir FROM history ORDER BY id DESC LIMIT 1")
row = cursor.fetchone()
output_dir = row[0]

# Pick a real file
file_to_test = None
for file in os.listdir(output_dir):
    if file.endswith('.html') and file != 'index.html':
        file_to_test = os.path.join(output_dir, file)
        break

# Backup the file for testing
test_file_path = "test_conversation.html"
shutil.copy(file_to_test, test_file_path)

# Set the current html path
window.current_html_path = os.path.abspath(test_file_path)

# Ensure webview is mocked or won't crash when running JS
# We can mock the webview's page().runJavaScript
class MockPage:
    def runJavaScript(self, js):
        pass
        
class MockWebView:
    def page(self):
        return MockPage()

window.webview = MockWebView()

print("Before appending, file size:", os.path.getsize(test_file_path))

# Run the append method
window.append_to_html_view("assistant", "This is a test AI response for TDD.")

print("After appending, file size:", os.path.getsize(test_file_path))

# Check if the appended text is actually in the file
with open(test_file_path, 'r', encoding='utf-8') as f:
    content = f.read()

if "This is a test AI response for TDD." in content:
    print("SUCCESS: File was successfully saved with the new text.")
else:
    print("FAILURE: Text was not appended.")
