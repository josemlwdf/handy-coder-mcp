"""Pattern databases for file classification in git staging validation.

This module defines the regex and glob patterns used to classify files into
categories: runtime artifacts, generated files, sensitive files, and normal
source files.

Categories
----------
- **runtime-artifact**: Files produced at runtime (caches, logs, WAL files,
  compiled bytecode). These are transient and should not be committed.
- **generated**: Files produced by a build/codegen step that can be
  reproduced from source. Usually tracked via .gitignore, but detected here
  as a safety net.
- **sensitive**: Files that may contain credentials, private keys, or other
  secrets. Always blocked regardless of policy.
- **normal**: Ordinary human-authored source files that are safe to stage.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Runtime artifact patterns
# ---------------------------------------------------------------------------
# Patterns matched against the *full relative path* of a file.
# Any match classifies the file as "runtime-artifact".
RUNTIME_ARTIFACT_PATTERNS: list[str] = [
    # SQLite WAL / SHM auxiliary files
    r".*\.db-wal$",
    r".*\.db-shm$",
    r".*\.db-journal$",
    # Python bytecode / caches
    r".*\.pyc$",
    r".*\.pyo$",
    r".*__pycache__.*",
    r".*\.pytest_cache.*",
    r".*\.mypy_cache.*",
    r".*\.ruff_cache.*",
    # Log files
    r".*\.log$",
    r".*\.log\.[0-9]+$",
    # Temporary files
    r".*\.tmp$",
    r".*\.temp$",
    r".*~$",
    r".*\.bak$",
    r".*\.swp$",
    r".*\.swo$",
    # Node / JS caches and locks
    r".*node_modules/.*",
    r".*\.npm/_cacache/.*",
    r".*\.yarn/cache/.*",
    # Build / coverage artifacts
    r".*\.tox/.*",
    r".*htmlcov/.*",
    r".*coverage\.xml$",
    r".*\.coverage$",
    r".*\.coverage\.[a-zA-Z0-9]+$",
    # Editor / OS junk
    r"\.DS_Store$",
    r"Thumbs\.db$",
    r"desktop\.ini$",
    r".*\.idea/.*",
    r".*\.vscode/.*",
    # Virtual environments
    r".*\.venv/.*",
    r".*venv/.*",
    # Misc runtime state
    r".*\.pid$",
    r".*\.lock$",
    r".*\.egg-info/.*",
]

# Pre-compiled patterns for performance
_RUNTIME_ARTIFACT_RE: list[re.Pattern[str]] = [
    re.compile(p) for p in RUNTIME_ARTIFACT_PATTERNS
]

# ---------------------------------------------------------------------------
# Generated file patterns
# ---------------------------------------------------------------------------
# Patterns matched against the *full relative path* of a file.
# Any match classifies the file as "generated".
GENERATED_PATTERNS: list[str] = [
    # Common build output directories
    r"^dist/",
    r"^build/",
    r"^out/",
    r"^target/",
    r"^_site/",
    r"^public/build/",
    # Generated TypeScript / JS
    r".*\.generated\.(ts|js|jsx|tsx|css)$",
    r".*\.min\.(js|css)$",
    r".*\.bundle\.(js|css)$",
    # Protobuf / gRPC generated
    r".*_pb2\.py$",
    r".*_pb2_grpc\.py$",
    r".*\.pb\.go$",
    r".*\.pb\.swift$",
    # OpenAPI / Swagger codegen
    r".*openapi-generated/.*",
    # Migrations that are auto-generated (heuristic)
    r".*alembic/versions/.*\.py$",
    # Storybook
    r".*storybook-static/.*",
    # Next.js / Nuxt build caches
    r".*\.next/.*",
    r".*\.nuxt/.*",
]

_GENERATED_RE: list[re.Pattern[str]] = [
    re.compile(p) for p in GENERATED_PATTERNS
]

# ---------------------------------------------------------------------------
# Sensitive filename patterns
# ---------------------------------------------------------------------------
# Patterns matched against the *basename* (filename only) of the file.
# Any match classifies the file as "sensitive".
SENSITIVE_FILENAME_PATTERNS: list[str] = [
    r"^\.env$",
    r"^\.env\..+$",          # .env.local, .env.production, etc.
    r"^secrets?\.ya?ml$",
    r"^secrets?\.json$",
    r"^secrets?\.toml$",
    r"^credentials?$",
    r"^credentials?\.json$",
    r"^credentials?\.ya?ml$",
    r".*\.pem$",
    r".*\.key$",
    r".*\.p12$",
    r".*\.pfx$",
    r".*\.pkcs12$",
    r"^id_rsa$",
    r"^id_dsa$",
    r"^id_ecdsa$",
    r"^id_ed25519$",
    r"^id_rsa\.pub$",        # public keys are still sensitive metadata
    r"^\.netrc$",
    r"^\.npmrc$",
    r"^\.pypirc$",
    r"^htpasswd$",
    r"^shadow$",
    r"^passwd$",
    r"^kubeconfig$",
    r".*kubeconfig.*",
    r"^terraform\.tfvars$",
    r"^terraform\.tfvars\.json$",
    r"^\*override\.tf$",
    r"^\*override\.tf\.json$",
    r"^\.terraformrc$",
    r"^terraform\.rc$",
    r"^service.account.*\.json$",
    r"^google.application.credentials.*\.json$",
]

_SENSITIVE_FILENAME_RE: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in SENSITIVE_FILENAME_PATTERNS
]

# ---------------------------------------------------------------------------
# Sensitive content patterns
# ---------------------------------------------------------------------------
# Patterns matched against *file content* line-by-line.
# Any match classifies the file as "sensitive".
SENSITIVE_CONTENT_PATTERNS: list[str] = [
    # Private keys (PEM / PKCS / OpenSSH)
    r"-----BEGIN (RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
    r"-----BEGIN CERTIFICATE-----",
    r"-----BEGIN PGP PRIVATE KEY BLOCK-----",
    # AWS
    r"AKIA[0-9A-Z]{16}",                         # AWS Access Key ID
    r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]",
    # GitHub PAT
    r"ghp_[0-9a-zA-Z]{36}",
    r"github_pat_[0-9a-zA-Z_]{82}",
    # Slack
    r"xox[baprs]-[0-9a-zA-Z\-]{10,}",
    # Generic high-entropy secrets in assignment context
    r"(?i)(password|passwd|secret|api.?key|auth.?token|access.?token|private.?key)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
    # Google API key
    r"AIza[0-9A-Za-z\-_]{35}",
    # Stripe
    r"(sk|pk)_(test|live)_[0-9a-zA-Z]{24,}",
    # SendGrid
    r"SG\.[0-9a-zA-Z\-_]{22}\.[0-9a-zA-Z\-_]{43}",
    # Twilio
    r"SK[0-9a-fA-F]{32}",
    # Square
    r"sq0atp-[0-9A-Za-z\-_]{22}",
    r"sq0csp-[0-9A-Za-z\-_]{43}",
    # Heroku
    r"(?i)heroku[^\n]{0,30}[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
    # JWT token (base64url header.payload.signature)
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    # Basic auth in URL
    r"https?://[^:/@\s]+:[^:/@\s]+@",
    # Bearer tokens in env-style
    r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
]

_SENSITIVE_CONTENT_RE: list[re.Pattern[str]] = [
    re.compile(p) for p in SENSITIVE_CONTENT_PATTERNS
]

# ---------------------------------------------------------------------------
# Normal source extensions
# ---------------------------------------------------------------------------
# Files with these extensions are classified as "normal" source files.
# Extensions must include the leading dot.
NORMAL_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Python
        ".py", ".pyi",
        # JavaScript / TypeScript
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        # Web
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        # Markup / data
        ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".xml", ".csv",
        # Config
        ".ini", ".cfg", ".conf", ".env.example",
        # Shell
        ".sh", ".bash", ".zsh", ".fish", ".ps1",
        # Compiled languages
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx",
        ".cs", ".java", ".kt", ".kts", ".go", ".rs", ".swift", ".rb",
        ".php", ".scala", ".clj", ".cljs", ".ex", ".exs", ".erl", ".hrl",
        # JVM
        ".gradle", ".groovy",
        # Other
        ".sql", ".graphql", ".gql", ".proto", ".tf", ".hcl",
        ".vue", ".svelte", ".astro",
        ".r", ".R", ".m", ".jl",
        # Docker / CI
        ".dockerfile", ".containerfile",
        # Lock files that ARE intentionally committed
        # (poetry.lock, Cargo.lock, go.sum, package-lock.json are source-controlled)
    }
)

# Extensions considered binary / large-asset types.
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".bin", ".exe", ".dll", ".so", ".dylib",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".mp4", ".mp3", ".avi", ".mov", ".mkv", ".wav", ".flac",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".wasm", ".class", ".jar", ".war", ".ear",
        ".sqlite", ".db",
        ".ico", ".svg",
    }
)

# Runtime-artifact extensions (always classified as runtime-artifact)
RUNTIME_ARTIFACT_EXTENSIONS: frozenset[str] = frozenset(
    {".pyc", ".pyo", ".log", ".tmp", ".temp", ".bak", ".swp", ".swo"}
)

def is_runtime_artifact_path(path: str) -> tuple[bool, list[str]]:
    """Check if path matches any runtime artifact pattern.

    Args:
        path: File path to check (relative or absolute).

    Returns:
        Tuple of (matched: bool, matched_pattern_strings: list[str]).
    """
    matched: list[str] = []
    for pattern, compiled in zip(RUNTIME_ARTIFACT_PATTERNS, _RUNTIME_ARTIFACT_RE):
        if compiled.search(path):
            matched.append(pattern)
    return bool(matched), matched

def is_generated_path(path: str) -> tuple[bool, list[str]]:
    """Check if path matches any generated-file pattern.

    Args:
        path: File path to check (relative or absolute).

    Returns:
        Tuple of (matched: bool, matched_pattern_strings: list[str]).
    """
    matched: list[str] = []
    for pattern, compiled in zip(GENERATED_PATTERNS, _GENERATED_RE):
        if compiled.search(path):
            matched.append(pattern)
    return bool(matched), matched

def is_sensitive_filename(filename: str) -> tuple[bool, list[str]]:
    """Check if filename matches any sensitive filename pattern.

    Args:
        filename: Bare filename (basename) to check.

    Returns:
        Tuple of (matched: bool, matched_pattern_strings: list[str]).
    """
    matched: list[str] = []
    for pattern, compiled in zip(SENSITIVE_FILENAME_PATTERNS, _SENSITIVE_FILENAME_RE):
        if compiled.match(filename):
            matched.append(pattern)
    return bool(matched), matched

def find_sensitive_content(text: str) -> tuple[bool, list[str]]:
    """Scan text content for sensitive patterns.

    Stops at the first matching pattern for efficiency.

    Args:
        text: File content to scan.

    Returns:
        Tuple of (found: bool, matched_pattern_strings: list[str]).
    """
    matched: list[str] = []
    for pattern, compiled in zip(SENSITIVE_CONTENT_PATTERNS, _SENSITIVE_CONTENT_RE):
        if compiled.search(text):
            matched.append(pattern)
            break  # stop on first match for performance
    return bool(matched), matched
