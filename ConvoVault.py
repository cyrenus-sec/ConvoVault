import sys
import json
import os
import html
from datetime import datetime
from pathlib import Path
import threading
import sqlite3
import re
import time
import base64
 
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QLabel, QLineEdit, QFileDialog, 
                            QProgressBar, QTextEdit, QSplitter, QListWidget, 
                            QListWidgetItem, QMessageBox, QFrame, QScrollArea,
                            QTabWidget, QComboBox, QCheckBox, QDesktopWidget, QDialog, QFormLayout)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QEventLoop
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QDesktopServices
from PyQt5.QtWebEngineWidgets import QWebEngineView

from LLMManager import LLMManager
from SettingsManager import SettingsManager

# Add Q&A Worker Thread
class LLMChatWorker(QThread):
    answer_ready = pyqtSignal(dict)
    
    def __init__(self, llm_manager, context, chat_history, question):
        super().__init__()
        self.llm_manager = llm_manager
        self.context = context
        self.chat_history = chat_history
        self.question = question
        
    def run(self):
        result = self.llm_manager.chat_with_context(self.context, self.chat_history, self.question)
        self.answer_ready.emit(result)

class ConversionWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    conversion_complete = pyqtSignal(str, list)
    conversion_error = pyqtSignal(str)
    
    def __init__(self, input_file, output_dir, file_format='claude'):
        super().__init__()
        self.input_file = input_file
        self.output_dir = output_dir
        self.file_format = file_format
        
    def run(self):
        try:
            self.progress_updated.emit(10, "Reading conversations file...")
            
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if self.file_format == 'chatgpt':
                conversations = self.parse_chatgpt_format(data)
            else:
                conversations = data if isinstance(data, list) else [data]
            
            self.progress_updated.emit(20, f"Found {len(conversations)} conversations")
            
            os.makedirs(self.output_dir, exist_ok=True)
            
            total_conversations = len(conversations)
            conversation_files = []
            
            for i, conversation in enumerate(conversations, 1):
                progress = 20 + (60 * i / total_conversations)
                self.progress_updated.emit(int(progress), f"Processing conversation {i}/{total_conversations}")
                
                output_file = os.path.join(self.output_dir, f'conversation_{i}.html')
                html_content = self.create_conversation_html(conversation, i)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                conversation_files.append({
                    'file': f'conversation_{i}.html',
                    'title': self.get_conversation_title(conversation, i),
                    'created_at': self.get_conversation_date(conversation),
                    'message_count': self.get_message_count(conversation)
                })
            
            self.progress_updated.emit(85, "Generating index page...")
            
            index_file = os.path.join(self.output_dir, 'index.html')
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(self.create_index_html(conversations))
            
            self.progress_updated.emit(100, f"Successfully converted {len(conversations)} conversations!")
            
            conversation_files.insert(0, {
                'file': 'index.html',
                'title': 'All Conversations (Index)',
                'created_at': '',
                'message_count': len(conversations)
            })
            
            self.conversion_complete.emit(self.output_dir, conversation_files)
            
        except Exception as e:
            self.conversion_error.emit(str(e))
    
    def parse_chatgpt_format(self, data):
        conversations = []
        
        if isinstance(data, list):
            for conv_data in data:
                conversation = {
                    'name': conv_data.get('title', 'Untitled Conversation'),
                    'created_at': conv_data.get('create_time', ''),
                    'chat_messages': []
                }
                
                mapping = conv_data.get('mapping', {})
                messages = []
                
                for node_id, node in mapping.items():
                    message = node.get('message')
                    if message and message.get('content') and message['content'].get('parts'):
                        content_parts = message['content']['parts']
                        if content_parts and content_parts[0]:
                            if isinstance(content_parts[0], dict):
                                text = str(content_parts[0])
                            else:
                                text = str(content_parts[0])
                            
                            messages.append({
                                'sender': 'human' if message.get('author', {}).get('role') == 'user' else 'assistant',
                                'text': text,
                                'created_at': message.get('create_time', ''),
                                'uuid': node_id,
                                'content': [{'type': 'text', 'text': text}],
                                'files': [],
                                'attachments': []
                            })
                
                conversation['chat_messages'] = sorted(messages, key=lambda x: str(x.get('created_at', '')))
                conversations.append(conversation)
        
        return conversations
    
    def get_conversation_title(self, conversation, index):
        return conversation.get('name', conversation.get('title', f'Conversation {index}'))
    
    def get_conversation_date(self, conversation):
        return conversation.get('created_at', conversation.get('create_time', ''))
    
    def get_message_count(self, conversation):
        messages = conversation.get('chat_messages', conversation.get('messages', []))
        return len(messages)
    
    def format_timestamp(self, timestamp_str: str) -> str:
        if not timestamp_str:
            return ''
        try:
            if isinstance(timestamp_str, (int, float)) or (isinstance(timestamp_str, str) and timestamp_str.isdigit()):
                dt = datetime.fromtimestamp(float(timestamp_str))
            else:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError):
            return str(timestamp_str)

    def process_message_content(self, content_items: list) -> tuple:
        text_contents = []
        artifacts = []
        tool_results = []
        
        for item in content_items:
            item_type = item.get('type', '')
            
            if item_type == 'text':
                text_contents.append(item.get('text', ''))
            
            elif item_type == 'tool_use' and item.get('name') == 'artifacts':
                input_data = item.get('input', {})
                if input_data and input_data.get('content'):
                    artifacts.append({
                        'id': input_data.get('id', ''),
                        'title': input_data.get('title', 'Untitled'),
                        'content': input_data.get('content', ''),
                        'language': input_data.get('language', 'plaintext'),
                        'type': input_data.get('type', '')
                    })
            
            elif item_type == 'tool_result' and item.get('name') == 'artifacts':
                content = item.get('content', [])
                result_text = ' '.join(c.get('text', '') for c in content if c.get('text'))
                if result_text:
                    tool_results.append(result_text)

        return text_contents, artifacts, tool_results
   
    def extract_artifacts(self, content):
        artifacts = []
        for item in content:
            if item.get('type') == 'tool_use' and item.get('name') == 'artifacts':
                input_data = item.get('input', {})
                if input_data and input_data.get('content'):
                    artifacts.append({
                        'title': input_data.get('title', 'Untitled'),
                        'content': input_data.get('content', ''),
                        'language': input_data.get('language', 'plaintext'),
                        'type': input_data.get('type', ''),
                        'id': input_data.get('id', '')
                    })
        return artifacts

    def process_code_blocks(self, text):
        if not text:
            return text
            
        parts = text.split('```')
        
        if len(parts) < 2:
            return text
            
        formatted_parts = []
        for i, part in enumerate(parts):
            if i == 0:
                formatted_parts.append(part)
                continue
                
            if i % 2 == 1:
                lines = part.strip().split('\n', 1)
                if len(lines) > 1:
                    language = lines[0].strip()
                    code = lines[1]
                else:
                    language = 'plaintext'
                    code = lines[0]
                    
                language = language.lower().replace('javascript', 'js')
                if language not in ['python', 'js', 'java', 'html', 'css', 'typescript', 'ts',
                            'json', 'xml', 'sql', 'bash', 'shell', 'plaintext']:
                    language = 'plaintext'
                
                # FIXED: Remove all extra whitespace from the HTML string
                code_block = f'<div class="inline-code-block"><div class="code-header"><span class="code-language copy-button">{language}</span></div><pre><code id="code-{i}" class="language-{language}">{html.escape(code.strip())}</code></pre></div>'
                
                formatted_parts.append(code_block)
            else:
                formatted_parts.append(part)
                
        return ''.join(formatted_parts)

    def create_message_html(self, message: dict) -> str:
        sender = message.get('sender', 'unknown')
        text = self.process_code_blocks(message.get('text', ''))
        created_at = message.get('created_at', '')
        content = message.get('content', [])
        files = message.get('files', [])
        attachments = message.get('attachments', [])

        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                formatted_time = created_at
        else:
            formatted_time = ''

        artifacts = self.extract_artifacts(content) if sender == 'assistant' else []

        attachments_html = ''
        if files or attachments:
            attachments_html = f"""
            <div class="attachments-section">
                <button onclick="toggleSection(this)" data-target="attachments-{message['uuid']}" class="toggle-btn">
                    Show Attachments
                </button>
                <div id="attachments-{message['uuid']}" class="collapsible" style="display: none;">
                    {f'<div class="files-list"><h4>Files:</h4><ul>{"".join(f"<li>{html.escape(str(f))}</li>" for f in files)}</ul></div>' if files else ''}
                    {f'<div class="attachments-list"><h4>Attachments:</h4><ul>{"".join(f"<li>{html.escape(str(a))}</li>" for a in attachments)}</ul></div>' if attachments else ''}
                </div>
            </div>
            """

        artifacts_html = ''
        if artifacts:
            artifacts_html = '<div class="artifacts-container">'
            for idx, artifact in enumerate(artifacts):
                artifact_id = f"{message['uuid']}-artifact-{idx}"
                artifacts_html += f"""
                <div class="artifact-section">
                    <button onclick="toggleSection(this)" data-target="{artifact_id}" class="toggle-btn artifact-btn">
                        Show Code: {html.escape(artifact['title'])}
                    </button>
                    <div id="{artifact_id}" class="collapsible code-block" style="display: none;">
                        <div class="artifact-header">
                            <h4>{html.escape(artifact['title'])}</h4>
                            <div class="artifact-info">
                                <span class="artifact-type">{artifact['type']}</span>
                                <span class="artifact-lang">{artifact['language']}</span>
                            </div>
                        </div>
                        <pre><code class="language-{artifact['language']}">{html.escape(artifact['content'])}</code></pre>
                    </div>
                </div>
                """
            artifacts_html += '</div>'

        return f"""
        <div class="message {sender}">
            <div class="message-header">
                <span class="sender-badge">{sender.capitalize()}</span>
                <span class="timestamp">{formatted_time}</span>
            </div>
            <div class="message-content">{text}</div>
            {attachments_html}
            {artifacts_html}
        </div>
        """
    
    def create_page_html(self, title: str, content: str) -> str:
        return f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{html.escape(title)}</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
            <style>
                :root {{
                    --bg-primary: #0d1117;
                    --bg-secondary: #161b22;
                    --bg-tertiary: #21262d;
                    --bg-accent: #30363d;
                    
                    --text-primary: #f0f6fc;
                    --text-secondary: #8b949e;
                    --text-muted: #656d76;
                    
                    --human-color: #238636;
                    --human-bg: #0f2419;
                    --assistant-color: #1f6feb;
                    --assistant-bg: #0c1116;
                    
                    --accent-purple: #8b5cf6;
                    --accent-pink: #ec4899;
                    --accent-cyan: #06b6d4;
                    
                    --border-default: #30363d;
                    --border-muted: #21262d;
                    
                    --shadow-default: 0 8px 24px rgba(0,0,0,0.3);
                    --shadow-lg: 0 16px 48px rgba(0,0,0,0.4);
                    
                    --gradient-primary: linear-gradient(135deg, var(--assistant-color), var(--accent-purple));
                    --gradient-accent: linear-gradient(135deg, var(--accent-pink), var(--accent-cyan));
                }}
                
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                    background: var(--bg-primary);
                    color: var(--text-primary);
                    line-height: 1.7;
                    padding: 2rem;
                    min-height: 100vh;
                }}
                
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                }}
                
                h1 {{
                    font-size: 2.5rem;
                    font-weight: 700;
                    background: var(--gradient-primary);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                    margin-bottom: 2rem;
                    text-align: center;
                }}
                
                .message {{
                    background: var(--bg-secondary);
                    margin: 2rem 0;
                    padding: 2rem;
                    border-radius: 1rem;
                    border: 1px solid var(--border-default);
                    box-shadow: var(--shadow-default);
                    position: relative;
                    overflow: hidden;
                }}
                
                .message::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 4px;
                    background: var(--gradient-primary);
                }}
                
                .message.human::before {{
                    background: linear-gradient(135deg, var(--human-color), var(--accent-cyan));
                }}
                
                .message-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 1.5rem;
                }}
                
                .sender-badge {{
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                    padding: 0.5rem 1rem;
                    border-radius: 2rem;
                    font-weight: 600;
                    font-size: 0.9rem;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }}
                
                .human .sender-badge {{
                    background: var(--human-bg);
                    color: var(--human-color);
                    border: 1px solid var(--human-color);
                }}
                
                .assistant .sender-badge {{
                    background: var(--assistant-bg);
                    color: var(--assistant-color);
                    border: 1px solid var(--assistant-color);
                }}
                
                .timestamp {{
                    color: var(--text-muted);
                    font-size: 0.85rem;
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                }}
                
                .message-content {{
                    white-space: pre-wrap;
                    line-height: 1.7;
                }}
                
                .artifacts-container {{
                    margin: 2rem 0;
                }}
                
                .artifact-section {{
                    background: var(--bg-tertiary);
                    border: 1px solid var(--border-default);
                    border-radius: 0.75rem;
                    margin: 1.5rem 0;
                    overflow: hidden;
                }}
                
                .artifact-header {{
                    padding: 1rem 1.5rem;
                    background: var(--bg-accent);
                    border-bottom: 1px solid var(--border-default);
                }}
                
                .artifact-info {{
                    display: flex;
                    gap: 0.75rem;
                    margin-top: 0.5rem;
                }}
                
                .artifact-type, .artifact-lang {{
                    padding: 0.25rem 0.75rem;
                    border-radius: 1rem;
                    font-size: 0.75rem;
                    font-weight: 500;
                    background: var(--bg-primary);
                    color: var(--text-secondary);
                    border: 1px solid var(--border-muted);
                }}
                
                .toggle-btn {{
                    background: var(--bg-accent);
                    border: 1px solid var(--border-default);
                    color: var(--text-primary);
                    padding: 0.75rem 1.5rem;
                    border-radius: 0.5rem;
                    cursor: pointer;
                    font-size: 0.9rem;
                    margin: 1rem 0;
                    transition: all 0.3s ease;
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                }}
                
                .toggle-btn:hover {{
                    background: var(--assistant-color);
                    border-color: var(--assistant-color);
                }}
                
                .code-block {{
                    margin: 0;
                    padding: 2rem 1.5rem;
                    background: var(--bg-primary);
                    border-radius: 0;
                    overflow-x: auto;
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
                    font-size: 0.9rem;
                    line-height: 1.6;
                }}
                
                .nav-link {{
                    color: var(--assistant-color);
                    text-decoration: none;
                    font-weight: 600;
                    transition: color 0.3s ease;
                }}
                
                .nav-link:hover {{
                    color: var(--accent-purple);
                    text-decoration: underline;
                }}
                
                .conversation-item {{
                    background: var(--bg-secondary);
                    margin: 1.5rem 0;
                    padding: 2rem;
                    border-radius: 1rem;
                    border: 1px solid var(--border-default);
                    box-shadow: var(--shadow-default);
                    transition: all 0.3s ease;
                }}
                
                .conversation-item:hover {{
                    border-color: var(--assistant-color);
                    box-shadow: var(--shadow-lg);
                }}
                
                .conversation-time {{
                    color: var(--text-muted);
                    font-size: 0.9rem;
                    margin-top: 0.5rem;
                    font-family: 'SF Mono', Monaco, monospace;
                }}
            </style>
            <script>
                function toggleSection(button) {{
                    const targetId = button.getAttribute('data-target');
                    const content = document.getElementById(targetId);
                    const isHidden = content.style.display === 'none';
                    
                    content.style.display = isHidden ? 'block' : 'none';
                    
                    if (button.textContent.includes('Show')) {{
                        button.innerHTML = button.innerHTML.replace('Show', 'Hide');
                    }} else if (button.textContent.includes('Hide')) {{
                        button.innerHTML = button.innerHTML.replace('Hide', 'Show');
                    }}
                    
                    if (isHidden) {{
                        hljs.highlightAll();
                    }}
                }}
                
                function copyCode(button) {{
                    const codeBlock = button.closest('.artifact-content').querySelector('code');
                    const text = codeBlock.textContent;
                    
                    navigator.clipboard.writeText(text).then(() => {{
                        const originalText = button.innerHTML;
                        button.innerHTML = 'Copied!';
                        button.style.background = 'var(--human-color)';
                        
                        setTimeout(() => {{
                            button.innerHTML = originalText;
                            button.style.background = '';
                        }}, 2000);
                    }});
                }}
                
                document.addEventListener('DOMContentLoaded', () => {{
                    hljs.highlightAll();
                }});
            </script>
        </head>
        <body>
            <div class="container">
                {content}
            </div>
        </body>
        </html>"""

    def create_conversation_html(self, conversation: dict, conversation_id: int) -> str:
        title = self.get_conversation_title(conversation, conversation_id)
        messages = conversation.get('chat_messages', conversation.get('messages', []))
        
        content = f"""
        <div class="nav-header">
            <a href="index.html" class="nav-link">Back to Conversations</a>
        </div>
        <h1>{html.escape(title)}</h1>
        <div class="conversation">
            {''.join(self.create_message_html(msg) for msg in messages)}
        </div>
        """
        
        return self.create_page_html(title, content)

    def create_index_html(self, conversations: list) -> str:
        conversation_links = []
        for i, conv in enumerate(conversations, 1):
            title = self.get_conversation_title(conv, i)
            created_at = self.format_timestamp(self.get_conversation_date(conv))
            message_count = self.get_message_count(conv)
            
            conversation_links.append(f"""
            <div class="conversation-item">
                <a href="conversation_{i}.html" class="nav-link">{html.escape(title)}</a>
                <div class="conversation-time">Created: {created_at} • {message_count} messages</div>
            </div>
            """)

        content = f"""
        <h1>ConvoVault Archive</h1>
        <p style="text-align: center; color: var(--text-secondary); font-size: 1.1rem; margin-bottom: 3rem;">
            Your conversation archive, beautifully preserved
        </p>
        <div class="conversations-list">
            {''.join(conversation_links)}
        </div>
        """
        
        return self.create_page_html('ConvoVault Archive', content)


class ConvoVault(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_dir = ""
        self.conversation_files = []
        self.current_conversation_data = None
        self.current_conversation_title = "No conversation loaded"
        self.current_html_path = None
        self.llm_manager = None
        self.llm_chat_worker = None
        self.chat_history = []
        self.settings_manager = SettingsManager()
        
        self.init_ui()
        self.create_status_bar()  
        self.apply_dark_theme()
        self.init_db()
        self.load_history()
        self.init_qa_system()
        
    def init_qa_system(self):
        def load_model():
            try:
                self.llm_manager = LLMManager()
                self.update_qa_status("LLM Provider Ready", "#238636")
            except Exception as e:
                self.update_qa_status(f"Model Error: {str(e)}", "#dc3545")
        
        thread = threading.Thread(target=load_model, daemon=True)
        thread.start()
    
    def update_qa_status(self, text, color):
        if hasattr(self, 'qa_status_label'):
            self.qa_status_label.setText(text)
            self.qa_status_label.setStyleSheet(f"color: {color}; font-size: 13px; margin-top: 8px; font-weight: bold;")
        
    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #0d1117; color: #f0f6fc; }
            QFrame { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; }
            QLabel { color: #f0f6fc; font-family: 'Segoe UI', Arial, sans-serif; background: transparent; }
            QLineEdit {
                background-color: #21262d; border: 2px solid #30363d; border-radius: 8px;
                padding: 12px; font-size: 14px; color: #f0f6fc;
            }
            QLineEdit:focus { border-color: #1f6feb; background-color: #0d1117; }
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #1f6feb, stop: 1 #0969da);
                color: white; border: none; padding: 12px 24px; border-radius: 8px;
                font-weight: 600; font-size: 14px; min-height: 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #0969da, stop: 1 #0550ae);
            }
            QPushButton:disabled { background-color: #30363d; color: #656d76; }
            QPushButton#convertBtn {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #238636, stop: 1 #196127);
                font-size: 16px; padding: 16px 32px; min-height: 24px;
            }
            QPushButton#convertBtn:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #2ea043, stop: 1 #238636);
            }
            QProgressBar {
                border: 2px solid #30363d; border-radius: 8px; text-align: center;
                background-color: #21262d; color: #f0f6fc; font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #1f6feb, stop: 1 #8b5cf6);
                border-radius: 6px;
            }
            QListWidget {
                background-color: #0d1117; border: 2px solid #30363d; border-radius: 8px;
                padding: 8px; outline: none;
            }
            QListWidget::item {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 6px;
                padding: 12px; margin: 4px; color: #f0f6fc;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #1f6feb, stop: 1 #0969da);
                border-color: #1f6feb; color: white;
            }
            QListWidget::item:hover { background-color: #21262d; border-color: #656d76; }
            QComboBox {
                background-color: #21262d; border: 2px solid #30363d; border-radius: 8px;
                padding: 8px 12px; color: #f0f6fc; min-width: 100px;
            }
            QComboBox:hover { border-color: #1f6feb; }
            QComboBox QAbstractItemView {
                background-color: #161b22; border: 1px solid #30363d; border-radius: 6px;
                selection-background-color: #1f6feb; color: #f0f6fc;
            }
            QTextEdit {
                background-color: #0d1117; border: 2px solid #30363d; border-radius: 8px;
                padding: 12px; color: #f0f6fc; font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #8b5cf6; }
            QTabWidget::pane { border: 2px solid #30363d; border-radius: 8px; background-color: #161b22; }
            QTabBar::tab {
                background-color: #21262d; border: 1px solid #30363d; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                padding: 8px 16px; margin-right: 2px; color: #8b949e;
            }
            QTabBar::tab:selected {
                background-color: #161b22; color: #f0f6fc; border-color: #1f6feb;
                border-bottom: 2px solid #1f6feb;
            }
            QTabBar::tab:hover { background-color: #30363d; color: #f0f6fc; }
        """)
    def create_status_bar(self):
        """Create and configure the status bar with developer info"""
        statusbar = self.statusBar()
        statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #161b22;
                color: #8b949e;
                border-top: 1px solid #30363d;
                padding: 5px;
            }
            QStatusBar::item {
                border: none;
            }
        """)
        
        # Create developer info label
        dev_info = QLabel("Developed by Mohamed Alaaeldin")
        dev_info.setStyleSheet("color: #8b949e; padding: 0 10px;")
        statusbar.addWidget(dev_info)
        
        # Add separator
        separator1 = QLabel("|")
        separator1.setStyleSheet("color: #30363d; padding: 0 5px;")
        statusbar.addWidget(separator1)
        
        # Create clickable LinkedIn link
        linkedin_label = QLabel('<a href="https://www.linkedin.com/in/mohamed-elkerwash" style="color: #1f6feb; text-decoration: none;">LinkedIn Profile</a>')
        linkedin_label.setOpenExternalLinks(True)
        linkedin_label.setStyleSheet("padding: 0 10px;")
        linkedin_label.setToolTip("Visit Mohamed Alaaeldin's LinkedIn")
        statusbar.addWidget(linkedin_label)
        
        # Add separator
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: #30363d; padding: 0 5px;")
        statusbar.addWidget(separator2)
        
        # Add version info
        version_label = QLabel("v1.0.8")
        version_label.setStyleSheet("color: #656d76; padding: 0 10px;")
        statusbar.addWidget(version_label)
        
        # Add stretch to push status messages to the right
        statusbar.addPermanentWidget(QLabel(""), 1)
        
        # Add status message area (right side)
        self.statusbar_message = QLabel("Ready")
        self.statusbar_message.setStyleSheet("color: #238636; padding: 0 15px; font-weight: bold;")
        statusbar.addPermanentWidget(self.statusbar_message)
    
    def init_ui(self):
        self.setWindowTitle("ConvoVault - AI-Powered Chat Archive")
        #self.setGeometry(100, 100, 1400, 900)
        screen = QDesktopWidget().screenGeometry()
    
        # Set window to 95% of screen size, centered
        margin = 50  # pixels from screen edge
        self.setGeometry(
            margin,
            margin,
            screen.width() - (margin * 2),
            screen.height() - (margin * 2)
            )
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        self.create_control_panel(splitter)
        self.create_webview_panel(splitter)
        
        splitter.setSizes([550, 850])
        
    def create_control_panel(self, parent):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        parent.addWidget(scroll_area)

        control_frame = QFrame()
        scroll_area.setWidget(control_frame)

        layout = QVBoxLayout(control_frame)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        archive_tab = QWidget()
        tab_widget.addTab(archive_tab, "Import Archive")
        self.create_archive_tab(archive_tab)

        chat_tab = QWidget()
        tab_widget.addTab(chat_tab, "AI Chat")
        self.create_chat_tab(chat_tab)
        
        history_tab = QWidget()
        tab_widget.addTab(history_tab, "History")
        self.create_history_tab(history_tab)

    def create_history_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Conversion History")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1f6feb;")
        layout.addWidget(title)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.load_history_item)
        self.history_list.itemSelectionChanged.connect(self.update_delete_button_state)
        layout.addWidget(self.history_list)

        delete_layout = QHBoxLayout()
        self.delete_history_btn = QPushButton("Delete Selected")
        self.delete_history_btn.clicked.connect(self.delete_history_item)
        self.delete_history_btn.setEnabled(False)
        self.delete_history_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #dc3545, stop: 1 #c82333);
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #e74c3c, stop: 1 #dc3545);
            }
            QPushButton:disabled { background-color: #30363d; color: #656d76; }
        """)
        delete_layout.addWidget(self.delete_history_btn)
        delete_layout.addStretch()
        layout.addLayout(delete_layout)

        layout.addStretch()

    def update_delete_button_state(self):
        if hasattr(self, 'delete_history_btn'):
            has_selection = len(self.history_list.selectedItems()) > 0
            self.delete_history_btn.setEnabled(has_selection)

    def delete_history_item(self):
        selected_items = self.history_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        folder = item.data(Qt.UserRole)
        if not folder:
            return
        
        reply = QMessageBox.question(
            self, 
            "Delete History Item", 
            f"Are you sure you want to delete this history item?\n\nFolder: {folder}\n\nNote: This will only remove it from history, not delete the actual files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                row = self.history_list.row(item)
                self.cursor.execute("SELECT id FROM history ORDER BY id DESC LIMIT 1 OFFSET ?", (row,))
                result = self.cursor.fetchone()
                
                if result:
                    history_id = result[0]
                    self.cursor.execute("DELETE FROM history WHERE id = ?", (history_id,))
                    self.conn.commit()
                    self.load_history()
                    QMessageBox.information(self, "Deleted", "History item deleted successfully!")
                else:
                    QMessageBox.warning(self, "Error", "Could not find history item to delete.")
                    
            except Exception as e:
                QMessageBox.critical(self, "Database Error", f"Failed to delete history item:\n{str(e)}")

    def load_history_item(self, item):
        folder = item.data(Qt.UserRole)
        if not folder:
            return
        index_path = os.path.join(folder, "index.html")
        if os.path.exists(index_path):
            self.output_dir = folder
            self.populate_conversation_list_from_dir(folder)
            url = QUrl.fromLocalFile(os.path.abspath(index_path))
            self.webview.load(url)
            # Clear current conversation data when loading index
            self.current_conversation_data = None
            self.current_conversation_title = "No conversation loaded"
            self.update_current_conv_label()
        else:
            QMessageBox.warning(self, "Missing", f"No index.html found in {folder}")
                
    def populate_conversation_list_from_dir(self, folder):
        self.conversation_list.clear()
        index_path = os.path.join(folder, "index.html")
        if os.path.exists(index_path):
            item = QListWidgetItem("All Conversations (Index)")
            item.setData(Qt.UserRole, {'file': 'index.html', 'title': 'All Conversations (Index)'})
            self.conversation_list.addItem(item)

        files = [f for f in os.listdir(folder) if f.startswith("conversation_") and f.endswith(".html")]
        files_sorted = sorted(files, key=lambda x: int(x.replace("conversation_","").replace(".html","")))
        for f in files_sorted:
            title = f.replace(".html", "")
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, {'file': f, 'title': title})
            self.conversation_list.addItem(item)
                
    def create_archive_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title_label = QLabel("ConvoVault")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #1f6feb; qproperty-alignment: AlignCenter;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("Transform your conversations into\nbeautiful, searchable archives")
        desc_label.setStyleSheet("color: #8b949e; margin-bottom: 30px; qproperty-alignment: AlignCenter; font-size: 14px;")
        layout.addWidget(desc_label)
        
        file_section = QFrame()
        file_section.setStyleSheet("QFrame { padding: 20px; }")
        file_layout = QVBoxLayout(file_section)
        
        file_label = QLabel("Select Conversation File")
        file_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 8px;")
        file_layout.addWidget(file_label)
        
        file_input_layout = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Choose your conversations.json file...")
        file_input_layout.addWidget(self.file_input)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        browse_btn.setMaximumWidth(110)
        file_input_layout.addWidget(browse_btn)
        
        file_layout.addLayout(file_input_layout)
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format:"))
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Claude Export", "ChatGPT Export"])
        self.format_combo.setCurrentText("Claude Export")
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        
        file_layout.addLayout(format_layout)
        layout.addWidget(file_section)
        
        output_section = QFrame()
        output_section.setStyleSheet("QFrame { padding: 20px; }")
        output_layout = QVBoxLayout(output_section)
        
        output_label = QLabel("Output Directory")
        output_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 8px;")
        output_layout.addWidget(output_label)
        
        self.output_input = QLineEdit("convovault_archive")
        self.output_input.setPlaceholderText("Enter output directory name...")
        output_layout.addWidget(self.output_input)
        
        layout.addWidget(output_section)
        
        self.convert_btn = QPushButton("Transform to Archive")
        self.convert_btn.setObjectName("convertBtn")
        self.convert_btn.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_btn)
        
        progress_section = QFrame()
        progress_section.setStyleSheet("QFrame { padding: 15px; }")
        progress_layout = QVBoxLayout(progress_section)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready to transform your conversations")
        self.status_label.setStyleSheet("color: #8b949e; font-style: italic; font-size: 13px;")
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_section)
        
        list_section = QFrame()
        list_section.setStyleSheet("QFrame { padding: 20px; }")
        list_layout = QVBoxLayout(list_section)
        
        list_label = QLabel("Generated Archive")
        list_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 12px;")
        list_layout.addWidget(list_label)
        
        self.conversation_list = QListWidget()
        self.conversation_list.itemClicked.connect(self.load_conversation)
        self.conversation_list.setMinimumHeight(300)
        list_layout.addWidget(self.conversation_list)
        
        actions_layout = QHBoxLayout()
        
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.setMaximumWidth(140)
        actions_layout.addWidget(self.open_folder_btn)
        
        actions_layout.addStretch()
        list_layout.addLayout(actions_layout)
        
        layout.addWidget(list_section)
        layout.addStretch()
        
    def create_chat_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title_label = QLabel("AI Chat Assistant")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #8b5cf6; qproperty-alignment: AlignCenter;")
        layout.addWidget(title_label)
        
        desc_label = QLabel("Ask questions about your opened conversations")
        desc_label.setStyleSheet("color: #8b949e; margin-bottom: 20px; qproperty-alignment: AlignCenter; font-size: 13px;")
        layout.addWidget(desc_label)
        
        status_section = QFrame()
        status_section.setStyleSheet("QFrame { padding: 15px; }")
        status_layout = QVBoxLayout(status_section)
        
        self.qa_status_label = QLabel("Loading LLM Provider...")
        self.qa_status_label.setStyleSheet("color: #8b949e; font-size: 13px; margin-top: 8px;")
        status_layout.addWidget(self.qa_status_label)
        
        self.current_conv_label = QLabel("Configure your LLM Provider in Settings")
        self.current_conv_label.setStyleSheet("color: #656d76; font-size: 12px; margin-top: 5px; font-style: italic;")
        status_layout.addWidget(self.current_conv_label)
        
        self.settings_btn = QPushButton("⚙️ Settings")
        self.settings_btn.setMaximumWidth(120)
        self.settings_btn.clicked.connect(self.open_settings)
        status_layout.addWidget(self.settings_btn)
        
        layout.addWidget(status_section)
        
        chat_section = QFrame()
        chat_section.setStyleSheet("QFrame { padding: 20px; }")
        chat_layout = QVBoxLayout(chat_section)
        
        chat_label = QLabel("Chat History")
        chat_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 8px;")
        chat_layout.addWidget(chat_label)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Ask questions about your conversations...\n\nExamples:\n- What was discussed about Python?\n- What solutions were proposed?")
        chat_layout.addWidget(self.chat_display)
        
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Ask a question about the current conversation...")
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        self.send_btn.setMaximumWidth(90)
        input_layout.addWidget(self.send_btn)
        
        chat_layout.addLayout(input_layout)
        layout.addWidget(chat_section)
        
        help_text = QLabel("Tip: Open a conversation from the Archive tab first, then ask questions here!")
        help_text.setStyleSheet("""
            color: #8b949e; background-color: #21262d; border: 1px solid #30363d;
            border-radius: 8px; padding: 15px; margin: 10px 0;
            qproperty-alignment: AlignCenter; line-height: 1.4;
        """)
        layout.addWidget(help_text)
        
        layout.addStretch()

    def open_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("LLM Settings")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        provider_combo = QComboBox()
        providers = ["Ollama", "OpenAI", "Anthropic", "Gemini", "DeepSeek"]
        provider_combo.addItems(providers)
        provider_combo.setCurrentText(self.settings_manager.get_provider())
        form.addRow("Provider:", provider_combo)
        
        model_input = QLineEdit()
        form.addRow("Model Name:", model_input)
        
        api_key_input = QLineEdit()
        api_key_input.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", api_key_input)
        
        def update_fields():
            prov = provider_combo.currentText()
            model_input.setText(self.settings_manager.get_model_name(prov))
            api_key_input.setText(self.settings_manager.get_api_key(prov))
            
            # Disable API key for Ollama
            if prov.lower() == "ollama":
                api_key_input.setEnabled(False)
                api_key_input.setPlaceholderText("Not required for local Ollama")
            else:
                api_key_input.setEnabled(True)
                api_key_input.setPlaceholderText("Enter API Key")
                
        provider_combo.currentTextChanged.connect(update_fields)
        update_fields() # Initial populate
        
        layout.addLayout(form)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save & Reload")
        save_btn.clicked.connect(lambda: self.save_settings(dialog, provider_combo, model_input, api_key_input))
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec_()
        
    def save_settings(self, dialog, provider_combo, model_input, api_key_input):
        prov = provider_combo.currentText()
        self.settings_manager.save_provider(prov)
        self.settings_manager.save_model_name(prov, model_input.text())
        self.settings_manager.save_api_key(prov, api_key_input.text())
        
        self.update_qa_status("Reloading LLM Provider...", "#8b949e")
        dialog.accept()
        
        # Reload LLM asynchronously
        def reload():
            try:
                if not self.llm_manager:
                    self.llm_manager = LLMManager()
                else:
                    self.llm_manager.reload_llm()
                self.update_qa_status(f"Provider Ready: {prov}", "#238636")
            except Exception as e:
                self.update_qa_status(f"Provider Error: {str(e)}", "#dc3545")
                
        threading.Thread(target=reload, daemon=True).start()

        
    def create_webview_panel(self, parent):
        webview_frame = QFrame()
        webview_frame.setStyleSheet("QFrame { border: none; }")
        parent.addWidget(webview_frame)
        
        layout = QVBoxLayout(webview_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.webview = QWebEngineView()
        
        welcome_html = """
                       <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="UTF-8">
                            <style>
                                body {
                                    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                                    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #21262d 100%);
                                    color: #f0f6fc;
                                    margin: 0;
                                    padding: 40px;
                                    text-align: center;
                                    height: 100vh;
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: center;
                                    align-items: center;
                                    overflow: hidden;
                                }
                                .logo {
                                    font-size: 6em;
                                    margin-bottom: 30px;
                                    background: linear-gradient(135deg, #1f6feb, #8b5cf6);
                                    -webkit-background-clip: text;
                                    -webkit-text-fill-color: transparent;
                                    background-clip: text;
                                    filter: drop-shadow(0 0 20px rgba(31, 111, 235, 0.3));
                                    animation: float 3s ease-in-out infinite, sparkle 2s ease-in-out infinite;
                                }
                                h1 {
                                    font-size: 3.5em;
                                    margin-bottom: 20px;
                                    font-weight: 300;
                                    background: linear-gradient(135deg, #f0f6fc, #8b949e);
                                    -webkit-background-clip: text;
                                    -webkit-text-fill-color: transparent;
                                    background-clip: text;
                                    animation: fadeInDown 1s ease-out;
                                }
                                .subtitle {
                                    font-size: 1.3em;
                                    opacity: 0;
                                    max-width: 700px;
                                    line-height: 1.6;
                                    margin-bottom: 40px;
                                    animation: fadeIn 1s ease-out 0.3s forwards;
                                }
                                .features {
                                    display: flex;
                                    gap: 30px;
                                    margin-top: 40px;
                                    flex-wrap: wrap;
                                    justify-content: center;
                                }
                                .feature {
                                    background: rgba(22, 27, 34, 0.8);
                                    border: 1px solid #30363d;
                                    border-radius: 12px;
                                    padding: 20px;
                                    max-width: 200px;
                                    backdrop-filter: blur(10px);
                                    opacity: 0;
                                    transform: translateY(30px);
                                    transition: all 0.3s ease;
                                    animation: slideUp 0.6s ease-out forwards;
                                }
                                .feature:nth-child(1) {
                                    animation-delay: 0.5s;
                                }
                                .feature:nth-child(2) {
                                    animation-delay: 0.7s;
                                }
                                .feature:nth-child(3) {
                                    animation-delay: 0.9s;
                                }
                                .feature:hover {
                                    transform: translateY(-10px) scale(1.05);
                                    border-color: #1f6feb;
                                    box-shadow: 0 10px 30px rgba(31, 111, 235, 0.3);
                                }
                                .feature-icon {
                                    font-size: 2em;
                                    margin-bottom: 10px;
                                    display: inline-block;
                                    animation: bounce 2s ease-in-out infinite;
                                }
                                .feature:hover .feature-icon {
                                    animation: spin 0.6s ease-in-out;
                                }
                                .feature-title {
                                    font-weight: 600;
                                    margin-bottom: 5px;
                                    color: #1f6feb;
                                }
                                .feature-desc {
                                    font-size: 0.9em;
                                    opacity: 0.7;
                                }
                                .glow {
                                    position: absolute;
                                    top: 20%;
                                    left: 50%;
                                    transform: translateX(-50%);
                                    width: 600px;
                                    height: 600px;
                                    background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%);
                                    z-index: -1;
                                    animation: pulse 4s ease-in-out infinite;
                                }
                                .particles {
                                    position: absolute;
                                    width: 100%;
                                    height: 100%;
                                    overflow: hidden;
                                    z-index: -1;
                                }
                                .particle {
                                    position: absolute;
                                    width: 4px;
                                    height: 4px;
                                    background: rgba(31, 111, 235, 0.5);
                                    border-radius: 50%;
                                    animation: float-particles 15s linear infinite;
                                }
                                .particle:nth-child(1) { left: 10%; animation-delay: 0s; }
                                .particle:nth-child(2) { left: 30%; animation-delay: 2s; }
                                .particle:nth-child(3) { left: 50%; animation-delay: 4s; }
                                .particle:nth-child(4) { left: 70%; animation-delay: 6s; }
                                .particle:nth-child(5) { left: 90%; animation-delay: 8s; }
                                
                                @keyframes pulse {
                                    0%, 100% { opacity: 0.3; transform: translateX(-50%) scale(1); }
                                    50% { opacity: 0.6; transform: translateX(-50%) scale(1.1); }
                                }
                                @keyframes float {
                                    0%, 100% { transform: translateY(0px); }
                                    50% { transform: translateY(-20px); }
                                }
                                @keyframes sparkle {
                                    0%, 100% { filter: drop-shadow(0 0 20px rgba(31, 111, 235, 0.3)); }
                                    50% { filter: drop-shadow(0 0 40px rgba(139, 92, 246, 0.6)); }
                                }
                                @keyframes fadeInDown {
                                    from {
                                        opacity: 0;
                                        transform: translateY(-30px);
                                    }
                                    to {
                                        opacity: 1;
                                        transform: translateY(0);
                                    }
                                }
                                @keyframes fadeIn {
                                    from { opacity: 0; }
                                    to { opacity: 0.8; }
                                }
                                @keyframes slideUp {
                                    from {
                                        opacity: 0;
                                        transform: translateY(30px);
                                    }
                                    to {
                                        opacity: 1;
                                        transform: translateY(0);
                                    }
                                }
                                @keyframes bounce {
                                    0%, 100% { transform: translateY(0); }
                                    50% { transform: translateY(-10px); }
                                }
                                @keyframes spin {
                                    from { transform: rotate(0deg); }
                                    to { transform: rotate(360deg); }
                                }
                                @keyframes float-particles {
                                    0% {
                                        transform: translateY(100vh) rotate(0deg);
                                        opacity: 0;
                                    }
                                    10% {
                                        opacity: 1;
                                    }
                                    90% {
                                        opacity: 1;
                                    }
                                    100% {
                                        transform: translateY(-100vh) rotate(360deg);
                                        opacity: 0;
                                    }
                                }
                            </style>
                        </head>
                        <body>
                            <div class="particles">
                                <div class="particle"></div>
                                <div class="particle"></div>
                                <div class="particle"></div>
                                <div class="particle"></div>
                                <div class="particle"></div>
                            </div>
                            <div class="glow"></div>
                            <div class="logo">💎</div>
                            <h1>ConvoVault</h1>
                            <p class="subtitle">
                                Transform your conversations into beautiful, searchable archives. 
                                Select your conversation file and watch the magic happen!
                            </p>
                            <div class="features">
                                <div class="feature">
                                    <div class="feature-icon">🎨</div>
                                    <div class="feature-title">Beautiful Design</div>
                                    <div class="feature-desc">Dark, modern interface with syntax highlighting</div>
                                </div>
                                <div class="feature">
                                    <div class="feature-icon">🔍</div>
                                    <div class="feature-title">Easy Navigation</div>
                                    <div class="feature-desc">Browse conversations with intuitive controls</div>
                                </div>
                                <div class="feature">
                                    <div class="feature-icon">⚡</div>
                                    <div class="feature-title">Fast & Responsive</div>
                                    <div class="feature-desc">Instant loading and smooth interactions</div>
                                </div>
                            </div>
                        </body>
                        </html>
        """
       
        self.webview.setHtml(welcome_html)
        layout.addWidget(self.webview)
        
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select conversations JSON file", "", "JSON files (*.json);;All files (*.*)"
        )
        if file_path:
            self.file_input.setText(file_path)
            
    def start_conversion(self):
        input_file = self.file_input.text()
        output_dir = self.output_input.text()
        file_format = 'chatgpt' if 'ChatGPT' in self.format_combo.currentText() else 'claude'
        
        if not input_file:
            QMessageBox.warning(self, "Warning", "Please select an input file")
            return
        
        if not os.path.exists(input_file):
            QMessageBox.critical(self, "Error", "Input file does not exist")
            return
            
        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("Processing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.conversation_list.clear()
        
        self.worker = ConversionWorker(input_file, output_dir, file_format)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.conversion_complete.connect(self.conversion_complete)
        self.worker.conversion_error.connect(self.conversion_error)
        self.worker.start()
        
    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        
    def conversion_complete(self, output_dir, conversation_files):
        self.output_dir = output_dir
        self.conversation_files = conversation_files
        
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("Transform to Archive")
        self.progress_bar.setVisible(False)
        self.open_folder_btn.setVisible(True)
        
        for conv_info in conversation_files:
            item = QListWidgetItem()
            if conv_info['file'] == 'index.html':
                item.setText(f"{conv_info['title']}")
                item.setToolTip("Overview of all conversations")
            else:
                created_at = conv_info['created_at']
                if created_at:
                    try:
                        if isinstance(created_at, (int, float)) or created_at.isdigit():
                            dt = datetime.fromtimestamp(float(created_at))
                        else:
                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        date_str = dt.strftime('%m/%d/%Y')
                    except:
                        date_str = "Unknown"
                else:
                    date_str = "Unknown"
                
                item.setText(f"{conv_info['title'][:50]}{'...' if len(conv_info['title']) > 50 else ''}")
                item.setToolTip(f"Created: {date_str}\nMessages: {conv_info['message_count']}")
            
            item.setData(Qt.UserRole, conv_info)
            self.conversation_list.addItem(item)
        
        if conversation_files:
            self.conversation_list.setCurrentRow(0)
            self.load_conversation(self.conversation_list.item(0))
        
        QMessageBox.information(self, "Success", 
                               f"Successfully transformed {len(conversation_files)-1} conversations!\n\n"
                               f"Archive location: {output_dir}\n"
                               f"Ready to explore and ask questions!")
        try:
            conv_count = max(0, len(conversation_files) - 1)
            self.add_to_history(output_dir, conv_count)
            self.load_history()
        except Exception as e:
            print("Failed to add to history:", e)

    def conversion_error(self, error_message):
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("Transform to Archive")
        self.progress_bar.setVisible(False)
        self.status_label.setText("Error occurred during transformation")
        QMessageBox.critical(self, "Transformation Error", f"An error occurred:\n\n{error_message}")
        
    def load_conversation(self, item):
        if not item:
            return
            
        conv_info = item.data(Qt.UserRole)
        file_path = os.path.join(self.output_dir, conv_info['file'])
        
        if os.path.exists(file_path):
            abs_path = os.path.abspath(file_path)
            url = QUrl.fromLocalFile(abs_path)
            self.webview.load(url)
            self.current_html_path = abs_path
            
            # Only load conversation data for individual conversations (not index)
            if conv_info['file'] != 'index.html':
                self.load_conversation_text_from_html(file_path)
                self.current_conversation_title = conv_info['title']
            else:
                self.current_conversation_data = None
                self.current_conversation_title = "No conversation loaded"
            
            self.update_current_conv_label()
        else:
            QMessageBox.warning(self, "Warning", f"File not found: {file_path}")
    
    def update_current_conv_label(self):
        if hasattr(self, 'current_conv_label'):
            if self.current_conversation_data:
                self.current_conv_label.setText(f"Loaded: {self.current_conversation_title[:50]}")
                self.current_conv_label.setStyleSheet("color: #238636; font-size: 12px; margin-top: 5px; font-weight: bold;")
            else:
                self.current_conv_label.setText("No conversation loaded - open one from Archive tab")
                self.current_conv_label.setStyleSheet("color: #656d76; font-size: 12px; margin-top: 5px; font-style: italic;")
    
    def load_conversation_text_from_html(self, html_path):
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            messages = re.findall(r'<div class="message-content">(.*?)</div>', content, re.DOTALL)
            
            clean_messages = []
            for msg in messages:
                clean = re.sub(r'<[^>]+>', '', msg)
                clean = html.unescape(clean)
                clean_messages.append(clean.strip())
            
            self.current_conversation_data = "\n\n".join(clean_messages)
            
        except Exception as e:
            print(f"Error loading conversation text: {e}")
            self.current_conversation_data = ""
            
    def open_output_folder(self):
        if self.output_dir and os.path.exists(self.output_dir):
            if sys.platform == "win32":
                os.startfile(self.output_dir)
            elif sys.platform == "darwin":
                os.system(f'open "{self.output_dir}"')
            else:
                os.system(f'xdg-open "{self.output_dir}"')
    
    def init_db(self):
        try:
            self.db_path = os.path.join(os.getcwd(), "convovault.db")
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    output_dir TEXT,
                    created_at TEXT,
                    conv_count INTEGER
                )
            """)
            self.conn.commit()
        except Exception as e:
            print("DB init error:", e)

    def add_to_history(self, output_dir, conv_count):
        try:
            self.cursor.execute(
                "INSERT INTO history (output_dir, created_at, conv_count) VALUES (?, ?, ?)",
                (output_dir, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), conv_count)
            )
            self.conn.commit()
        except Exception as e:
            print("Failed to add history:", e)

    def load_history(self):
        try:
            self.cursor.execute("SELECT id, output_dir, created_at, conv_count FROM history ORDER BY id DESC")
            rows = self.cursor.fetchall()
        except Exception as e:
            print("Failed to read history:", e)
            rows = []

        if not hasattr(self, 'history_list'):
            return

        self.history_list.clear()
        for row in rows:
            id_, output_dir, created_at, conv_count = row
            display = f"{output_dir}  |  {created_at}  |  {conv_count} convos"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, output_dir)
            self.history_list.addItem(item)


    def get_page_text_sync(self) -> str:
        """
        Returns the current page's text (clean string, no HTML) synchronously.
        """
        loop = QEventLoop()
        result = {}

        def callback(text):
            result["text"] = text
            loop.quit()

        self.webview.page().toPlainText(callback)
        loop.exec_()
        return result.get("text", "")
        
    def send_message(self):
        context = self.get_page_text_sync()
        question = self.message_input.text().strip()
        if not question:
            return
        
        if not self.llm_manager:
            self.append_to_chat("System", "LLM Provider is not configured or still loading. Please check Settings.")
            return
        
        if not context:
            self.append_to_chat("System", "No conversation loaded. Please open a specific conversation from the Archive tab first (not the index page).")
            self.message_input.clear()
            return
        
        self.chat_history.append({"role": "user", "content": question})
        self.append_to_chat("You", question)
        self.append_to_html_view("human", question)
        
        self.message_input.clear()
        
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")
        
        self.llm_chat_worker = LLMChatWorker(self.llm_manager, context, self.chat_history[:-1], question)
        self.llm_chat_worker.answer_ready.connect(self.handle_qa_response)
        self.llm_chat_worker.start()
    
    def handle_qa_response(self, result):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        
        answer = result.get("answer", "")
        self.chat_history.append({"role": "assistant", "content": answer})
        
        response_text = f"{answer}\n\n[Processing Time: {result.get('processing_time', 0):.2f}s]"
        self.append_to_chat("AI", response_text)
        self.append_to_html_view("assistant", answer)

    def append_to_html_view(self, sender, text):
        worker = ConversionWorker("", "")
        message = {
            'sender': sender,
            'text': text,
            'created_at': datetime.now().isoformat() + 'Z',
            'uuid': f'chat-{int(time.time()*1000)}',
            'content': [{'type': 'text', 'text': text}],
            'files': [],
            'attachments': []
        }
        html_block = worker.create_message_html(message)
        
        b64_html = base64.b64encode(html_block.encode('utf-8')).decode('utf-8')
        
        js_code = f"""
        var conv = document.querySelector('.conversation');
        if (conv) {{
            try {{
                var binaryString = window.atob('{b64_html}');
                var bytes = new Uint8Array(binaryString.length);
                for (var i = 0; i < binaryString.length; i++) {{
                    bytes[i] = binaryString.charCodeAt(i);
                }}
                var decodedHtml = new TextDecoder('utf-8').decode(bytes);
                
                var template = document.createElement('template');
                template.innerHTML = decodedHtml;
                var newElement = template.content.firstElementChild;
                conv.appendChild(newElement);
                window.scrollTo(0, document.body.scrollHeight);
                if (typeof hljs !== 'undefined') {{
                    var blocks = newElement.querySelectorAll('pre code');
                    for (var i = 0; i < blocks.length; i++) {{
                        hljs.highlightElement(blocks[i]);
                    }}
                }}
            }} catch (e) {{
                console.error("Failed to append HTML view:", e);
            }}
        }}
        """
        self.webview.page().runJavaScript(js_code)
        
        # Save payload to disk so it persists
        if hasattr(self, 'current_html_path') and self.current_html_path and os.path.exists(self.current_html_path):
            print(f"[DEBUG] Attempting to save to {self.current_html_path}")
            try:
                with open(self.current_html_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                match = re.search(r'(</div>\s*</div>\s*</body>)', content)
                if match:
                    print("[DEBUG] Match found for HTML injection!")
                    content = content[:match.start()] + html_block + "\n" + match.group(1) + content[match.end():]
                    with open(self.current_html_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print("[DEBUG] Successfully saved to disk.")
                else:
                    print("[DEBUG] Regex MATCH FAILED on file content.")
            except Exception as e:
                print(f"[ERROR] Failed to save AI response to disk: {e}")
        else:
            print("[DEBUG] current_html_path not set or file doesn't exist.")
    
    def append_to_chat(self, sender, message):
        current_text = self.chat_display.toPlainText()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if current_text:
            new_text = f"{current_text}\n\n[{timestamp}] {sender}:\n{message}"
        else:
            new_text = f"[{timestamp}] {sender}:\n{message}"
        
        self.chat_display.setPlainText(new_text)
        
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.End)
        self.chat_display.setTextCursor(cursor)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ConvoVault")
    app.setApplicationDisplayName("ConvoVault - AI-Powered Chat Archive")
    
    app.setStyle('Fusion')
    
    window = ConvoVault()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()