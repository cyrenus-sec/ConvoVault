import sqlite3
import os

class SettingsManager:
    def __init__(self, db_path="convovault.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"Error initializing settings DB: {e}")

    def _set(self, key: str, value: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                    (key, value)
                )
                conn.commit()
        except Exception as e:
            print(f"Error saving setting {key}: {e}")

    def _get(self, key: str, default: str = "") -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return row[0]
                return default
        except Exception as e:
            print(f"Error getting setting {key}: {e}")
            return default

    # API Keys
    def save_api_key(self, provider: str, api_key: str):
        self._set(f"api_key_{provider.lower()}", api_key)

    def get_api_key(self, provider: str) -> str:
        return self._get(f"api_key_{provider.lower()}")

    # Provider Preference
    def save_provider(self, provider: str):
        self._set("selected_provider", provider)

    def get_provider(self) -> str:
        # Default to Ollama since it's local
        return self._get("selected_provider", "Ollama")

    # Specific Model Selection per Provider
    def save_model_name(self, provider: str, model_name: str):
        self._set(f"model_{provider.lower()}", model_name)

    def get_model_name(self, provider: str) -> str:
        default_models = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307",
            "gemini": "gemini-1.5-flash",
            "deepseek": "deepseek-chat",
            "ollama": "llama3"
        }
        return self._get(f"model_{provider.lower()}", default_models.get(provider.lower(), ""))
