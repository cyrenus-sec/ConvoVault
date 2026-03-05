from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
try:
    from langchain_ollama import ChatOllama
except ImportError:
    from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from SettingsManager import SettingsManager
import time

class LLMManager:
    def __init__(self):
        self.settings = SettingsManager()
        self.current_llm = None
        self._initialize_llm()

    def _initialize_llm(self):
        provider = self.settings.get_provider().lower()
        model_name = self.settings.get_model_name(provider)
        api_key = self.settings.get_api_key(provider)

        try:
            if provider == "openai":
                if not api_key:
                    raise ValueError("OpenAI API key is missing.")
                self.current_llm = ChatOpenAI(model=model_name, api_key=api_key)
            
            elif provider == "anthropic":
                if not api_key:
                    raise ValueError("Anthropic API key is missing.")
                self.current_llm = ChatAnthropic(model=model_name, api_key=api_key)
                
            elif provider == "gemini":
                if not api_key:
                    raise ValueError("Google Gemini API key is missing.")
                self.current_llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
                
            elif provider == "deepseek":
                if not api_key:
                    raise ValueError("DeepSeek API key is missing.")
                # DeepSeek provides an OpenAI-compatible API
                self.current_llm = ChatOpenAI(
                    model=model_name, 
                    api_key=api_key, 
                    base_url="https://api.deepseek.com"
                )
                
            elif provider == "ollama":
                # Ollama runs locally, usually port 11434
                self.current_llm = ChatOllama(model=model_name)
                
            else:
                raise ValueError(f"Unknown provider: {provider}")
                
        except Exception as e:
            self.current_llm = None
            print(f"Failed to initialize LLM ({provider}): {e}")
            raise e

    def reload_llm(self):
        """Forces a reload of settings and the underlying LangChain model."""
        self._initialize_llm()

    def chat_with_context(self, document_context: str, chat_history: list, new_question: str) -> dict:
        """
        Takes the document text, previous chat history, and the new question.
        Returns a dict with 'answer' and 'processing_time'.
        chat_history format expected: [{"role": "user"/"assistant", "content": "..."}]
        """
        start_time = time.time()
        
        if not self.current_llm:
            try:
                self._initialize_llm()
            except Exception as e:
                return {"answer": f"Error: LLM not configured properly. {str(e)}", "processing_time": 0.0}

        # Build messages
        system_prompt = (
            "You are an AI assistant analyzing a document for the user. "
            "Use the provided document context to answer the user's questions. "
            "If the answer is not in the document, you can use your general knowledge but state that clearly.\n\n"
            "--- DOCUMENT CONTEXT ---\n"
            f"{document_context}\n"
            "--- END CONTEXT ---"
        )
        
        messages = [SystemMessage(content=system_prompt)]
        
        # Add history
        for msg in chat_history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content")))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg.get("content")))
                
        # Add new question
        messages.append(HumanMessage(content=new_question))

        try:
            response = self.current_llm.invoke(messages)
            processing_time = time.time() - start_time
            return {
                "answer": response.content,
                "processing_time": processing_time
            }
        except Exception as e:
            return {
                "answer": f"Error generating response: {str(e)}\nPlease check your API keys or local Ollama server status.",
                "processing_time": time.time() - start_time
            }
