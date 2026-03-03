# ConvoVault - AI-Powered Chat Archive

ConvoVault is an AI-powered desktop application built with Python and PyQt5. It provides a beautiful interface to parse, archive, and query your conversation histories from platforms like ChatGPT and Claude.

## Description

ConvoVault allows users to convert their exported chat histories into visually appealing, searchable local HTML archives. Furthermore, it features an integrated AI Question-Answering system (powered by Hugging Face `transformers` and `torch`) allowing you to interact intelligently with your local chat archives.

![screen](screen.png)

## Features

- **Chat Parsing & Archiving**: Convert exported ChatGPT and Claude conversation JSON/HTML into beautiful, responsive local HTML archives.
- **AI Question Answering**: Integrated local AI models to query and answer questions based on your archived conversations.
- **Beautiful UI**: Built with PyQt5, featuring a sleek, modern dark theme.
- **Local Storage**: Completely local processing and SQLite database storage for absolute privacy.

## Installation & Requirements

Ensure you have Python 3 installed. You can install the required dependencies using `pip`.

```bash
pip install -r requirements.txt
pip install PyQt5 PyQtWebEngine
```

**Note:** The application uses `transformers` and `torch==2.0.1`. Ensure your environment supports these versions. 

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
