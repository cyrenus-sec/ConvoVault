import sys
import os
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Initialize app properly for WebEngine
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)

import ConvoVault
from LLMManager import LLMManager

# Mock an LLM Manager that just returns instantly
class MockLLMManager(LLMManager):
    def _initialize_llm(self):
        pass
        
    def chat_with_context(self, document_context, chat_history, new_question):
        return {
            "answer": "This is a mock response from the LLM.",
            "processing_time": 0.5
        }

def test_thread():
    window = ConvoVault.ConvoVault()
    window.llm_manager = MockLLMManager()
    
    # Setup some dummy data
    window.current_html_path = os.path.abspath("test_conversation.html")
    window.message_input.setText("Test message")
    window.chat_history = []
    
    # Mock webview JS execution map
    class MockPage:
        def runJavaScript(self, js):
            print("[MOCK JS EVAL]")
            
    class MockWebView:
        def page(self):
            return MockPage()
            
    window.webview = MockWebView()
    
    # Override get_page_text_sync to not hang EventLoop
    window.get_page_text_sync = lambda: "Dummy context"
    
    print("Sending message...")
    window.send_message()
    
    # Let event loop process the signal
    start = time.time()
    while time.time() - start < 2:
        app.processEvents()
        time.sleep(0.1)
        
    print("Test finished.")

if __name__ == "__main__":
    test_thread()
