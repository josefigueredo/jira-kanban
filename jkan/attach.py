"""jtk attach: what a file becomes before it goes to Jira as an attachment, and how the approval describes it.

Sanitizing is on by default and runs once: the bytes shown in the approval (size, sha256) are the bytes uploaded, and
the original file is never touched. It replaces what must not leave the machine: the configured Jira token, known
token formats, private key blocks and home-directory paths. It does not touch names or emails (a guide's authorship
is deliberate). A replaced value is never printed, shown or journaled: only how many of each kind. Content that is not
UTF-8 text cannot be sanitized, so it goes only with --no-sanitize, and the approval says so.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

ORDER = ("ruta local", "token", "clave privada", "credencial de Jira")
_PLURAL = {"ruta local": "rutas locales", "token": "tokens", "clave privada": "claves privadas",
           "credencial de Jira": "credenciales de Jira"}
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_TOKENS = [
    re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}"),                 # Atlassian API token
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),                 # GitHub token
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),               # GitHub fine-grained token
    re.compile(r"\bNRAK-[A-Z0-9]{27}\b"),                        # New Relic user key
    re.compile(r"\b[a-f0-9]{36}NRAL\b"),                         # New Relic ingest license key
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                # AWS access key id
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),               # Slack token
]
_BEARER = re.compile(r"(\bBearer\s+)[A-Za-z0-9._~+/=-]{20,}")
_HOME = re.compile(r"(?:/Users|/home)/[^/\s\"'<>`]+")


class Upload(NamedTuple):
    path: Path
    name: str
    data: bytes
    sanitized: bool
    binary: bool
    redactions: Dict[str, int]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def sanitize(data: bytes, secrets: Iterable[str] = ()) -> Tuple[Optional[bytes], Dict[str, int]]:
    """The sanitized bytes and how many values of each kind were replaced; (None, {}) when it is not UTF-8 text."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, {}
    if "\x00" in text:
        return None, {}
    counts: Dict[str, int] = {}

    def count(kind: str, n: int) -> None:
        if n:
            counts[kind] = counts.get(kind, 0) + n

    for secret in (s for s in secrets if s and len(s) >= 8):
        n = text.count(secret)
        text = text.replace(secret, "[REDACTED:jira-token]")
        count("credencial de Jira", n)
    text, n = _PRIVATE_KEY.subn("[REDACTED:private-key]", text)
    count("clave privada", n)
    for pattern in _TOKENS:
        text, n = pattern.subn("[REDACTED:token]", text)
        count("token", n)
    text, n = _BEARER.subn(r"\1[REDACTED:token]", text)
    count("token", n)
    text, n = _HOME.subn("~", text)
    count("ruta local", n)
    return text.encode("utf-8"), counts


def describe(sanitized: bool, redactions: Dict[str, int], binary: bool = False) -> str:
    if not sanitized:
        return "no (binario, --no-sanitize)" if binary else "no (--no-sanitize)"
    if not redactions:
        return "sí — sin cambios"
    parts = [f"{redactions[k]} {k if redactions[k] == 1 else _PLURAL[k]}" for k in ORDER if redactions.get(k)]
    return "sí — " + ", ".join(parts)


def prepare(path: Path, sanitize_on: bool, secrets: Iterable[str] = ()) -> Upload:
    """Read the file once and build what will be uploaded. Raises ValueError for content that cannot be sanitized."""
    raw = Path(path).read_bytes()
    clean, counts = sanitize(raw, secrets)
    binary = clean is None
    if not sanitize_on:
        return Upload(Path(path), Path(path).name, raw, False, binary, {})
    if binary:
        raise ValueError(f"{Path(path).name}: not UTF-8 text, so it cannot be sanitized; pass --no-sanitize to upload "
                         f"it as is (the approval will say it was not sanitized)")
    return Upload(Path(path), Path(path).name, clean, True, False, counts)


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def change(upload: Upload) -> str:
    """The approval row's change, one labelled line each (the window renders «Label: value» lines)."""
    return (f"Acción: subir adjunto\nTamaño: {human_size(len(upload.data))} · sha256 {upload.sha256[:12]}\n"
            f"Sanitizado: {describe(upload.sanitized, upload.redactions, upload.binary)}")


def split_duplicates(uploads: List[Upload], existing: List[dict]) -> Tuple[List[Upload], List[Upload]]:
    """Uploads to send, and those already attached with the same name and the same size (of the bytes to send)."""
    present = {(a.get("filename"), a.get("size")) for a in existing}
    send = [u for u in uploads if (u.name, len(u.data)) not in present]
    return send, [u for u in uploads if (u.name, len(u.data)) in present]
