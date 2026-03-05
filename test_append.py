import re
import os

dummy_html = """
<!DOCTYPE html>
<html>
    <head></head>
    <body>
        <div class="container">
            <div class="nav-header">
                <a href="index.html" class="nav-link">Back to Conversations</a>
            </div>
            <h1>Test Conversation</h1>
            <div class="conversation">
                <div class="message human">Hello</div>
            </div>
            
        </div>
    </body>
</html>
"""

html_block = '<div class="message assistant">Hi there!</div>'

# Test 1: The current regex fails or succeeds?
match1 = re.search(r'(</div>\s*</div>\s*</body>)', dummy_html)
print("Test 1 (Original Regex):", "Match found" if match1 else "NO MATCH")

# Test 2: A better regex to find the closing tag of the conversation div
# We search for the end of the conversation div by looking for the sequence:
# </div> (closes conversation div)
# \s*
# </div> (closes container div)
# \s*
# </body>
match2 = re.search(r'(</div>\s*</div>\s*</body>)', dummy_html)
print("Test 2 (Better Regex):", "Match found" if match2 else "NO MATCH")

# Test 3: Maybe just use the string literal '</div>\\s*</div>\\s*</body>' is failing because of newlines in the python re.search?
match3 = re.search(r'(</div>\s*</div>\s*</body>)', dummy_html, re.DOTALL | re.MULTILINE | re.IGNORECASE)
print("Test 3 (With Flags):", "Match found" if match3 else "NO MATCH")

# Test 4: Simply look for the exact closing tag combination, ignoring other attributes or whitespaces
match4 = re.search(r'(</div>\s*</div>\s*</body>\s*</html>)', dummy_html, re.IGNORECASE)
print("Test 4 (With </html>):", "Match found" if match4 else "NO MATCH")
