# ConvoVault - AI-Powered Chat Archive

ConvoVault is an AI-powered desktop application built with Python and PyQt5. It provides a beautiful interface to parse, archive, and query your conversation histories from platforms like ChatGPT and Claude.

## Description

ConvoVault allows users to convert their exported chat histories into visually appealing, searchable local HTML archives. Furthermore, it features an integrated Multi-LLM Chat system powered by **LangChain**, allowing you to interact intelligently with your local chat archives using models from OpenAI, Anthropic, Gemini, DeepSeek, and locally via Ollama.

![screen](screen.png)

## Features

- **Chat Parsing & Archiving**: Convert exported ChatGPT and Claude conversation JSON/HTML into beautiful, responsive local HTML archives.
- **Multi-LLM Question Answering**: Chat with your document context using LangChain! Supports OpenAI, Anthropic, Google Gemini, DeepSeek, and local Ollama integrations.
- **Seamless HTML Appending**: AI responses seamlessly integrate into the beautiful Markdown UI of the loaded Chat Archive.
- **Local Storage**: Preferences and API Keys are securely stored locally via SQLite (`convovault.db`) ensuring total privacy.

## Local LLM Setup (Ollama)

ConvoVault natively supports 100% offline, private inference using Ollama. To configure this:
1. Download and install [Ollama](https://ollama.com).
2. Open your terminal and run a model (e.g. `ollama run llama3`).
3. In ConvoVault, open the **⚙️ Settings** tab and select **Ollama** as your provider with `llama3` as your model name. No API key is required!

## Installation & Requirements

Ensure you have Python 3 installed. You can install the required dependencies using `pip`.

```bash
pip install -r requirements.txt
pip install PyQt5 PyQtWebEngine langchain
```

**Note:** If you choose to use cloud APIs, ensure you input your API keys in the app's settings screen. They are strictly stored on your local disk in the SQLite DB.

## Running the Application

To run ConvoVault locally:

```bash
python ConvoVault.py
```

## Building Executable

The project includes PyInstaller configurations (`ConvoVault.spec`) to build a standalone executable:

```bash
pip install pyinstaller
pyinstaller ConvoVault.spec
```

## Developer

Developed by Mohamed Alaaeldin.
