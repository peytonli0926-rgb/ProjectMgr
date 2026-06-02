HOST = "127.0.0.1"
PORT = 8000
TARGET_SUFFIX = "_desensitized"

TEXT_EXTENSIONS = {
    ".txt", ".csv", ".json", ".xml", ".yaml", ".yml", ".log", ".md",
    ".py", ".java", ".js", ".ts", ".html", ".sql",
}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
SKIP_EXTENSIONS = {".doc", ".ppt", ".xls", ".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | OFFICE_EXTENSIONS
EXCLUDED_PARTS = {".git", "__pycache__", ".idea", ".venv", "node_modules"}
