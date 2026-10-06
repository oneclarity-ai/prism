"""Fail when versioned or nonignored files contain likely credentials."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}
SENSITIVE_ASSIGNMENT_KEYS = {
    "AZURE_OPENAI_API_KEY",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_TOKEN_ENCRYPTION_KEY",
    "OPERATOR_API_TOKEN",
}
SAFE_PLACEHOLDERS = {
    "",
    "change-me",
    "replace-with-a-local-password",
}


def is_safe_placeholder(value: str) -> bool:
    """Return whether an example value cannot authenticate to a service."""

    normalized = value.casefold()
    return (
        value in SAFE_PLACEHOLDERS
        or normalized in {"fake", "test", "example", "dummy"}
        or normalized.startswith(("fake-", "test-", "example-", "dummy-"))
        or (value.startswith("<") and value.endswith(">"))
    )


def assignment_findings(content: str) -> list[tuple[int, str]]:
    """Find populated sensitive environment settings outside safe examples."""

    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)=(.*)\s*$", line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip().rstrip(",").strip().strip('"').strip("'")
        if key in SENSITIVE_ASSIGNMENT_KEYS and not is_safe_placeholder(value):
            findings.append((line_number, f"configured {key}"))
        if key == "DATABASE_URL" and "://" in value:
            password_match = re.search(r"://[^:@/\s]+:([^@/\s]+)@", value)
            if password_match and not is_safe_placeholder(password_match.group(1)):
                findings.append((line_number, "configured DATABASE_URL password"))
    return findings


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: possible {name}")
        for line, description in assignment_findings(content):
            findings.append(f"{path.relative_to(ROOT)}:{line}: possible {description}")

    if findings:
        print("Potential secrets found in tracked files:")
        print("\n".join(findings))
        return 1
    print("No likely credentials found in versioned or nonignored files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
