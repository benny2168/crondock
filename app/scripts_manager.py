import ast
import logging
import os
import re
import stat
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from database import DATA_DIR, Job

logger = logging.getLogger(__name__)

SCRIPTS_DIR = os.getenv("SCRIPTS_DIR", os.path.join(DATA_DIR, "scripts"))
SAFE_FILENAME_RE = re.compile(r'^[a-zA-Z0-9_\-\.]+$')

# Ensure directory exists on load
os.makedirs(SCRIPTS_DIR, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Validate and sanitize script filename to prevent path traversal and shell injection."""
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename cannot be empty")
    name = os.path.basename(filename).strip()
    if not SAFE_FILENAME_RE.match(name) or name in (".", "..") or ".." in name:
        raise ValueError(
            f"Invalid script filename '{filename}'. Use letters, numbers, dots, hyphens, and underscores."
        )
    return name


def get_script_path(filename: str) -> str:
    name = sanitize_filename(filename)
    return os.path.join(SCRIPTS_DIR, name)


def detect_script_type(filename: str, content: str = "") -> str:
    name = filename.lower()
    if name.endswith(".py"):
        return "python"
    if name.endswith((".sh", ".bash", ".zsh")):
        return "shell"
    if content:
        first_line = content.splitlines()[0] if content.splitlines() else ""
        if "python" in first_line:
            return "python"
        if any(sh in first_line for sh in ("bash", "sh", "zsh")):
            return "shell"
    return "shell"


def list_scripts(db) -> List[Dict[str, Any]]:
    """Scan SCRIPTS_DIR and cross-reference with jobs referencing each script."""
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    all_jobs = db.query(Job).all()

    scripts = []
    try:
        entries = sorted(os.listdir(SCRIPTS_DIR))
    except Exception as e:
        logger.error(f"Failed to read scripts dir {SCRIPTS_DIR}: {e}")
        return []

    for entry in entries:
        if entry.startswith("."):
            continue
        path = os.path.join(SCRIPTS_DIR, entry)
        if not os.path.isfile(path):
            continue

        try:
            st = os.stat(path)
            is_exec = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            mod_dt = datetime.utcfromtimestamp(st.st_mtime)

            # Peek first 200 chars for type detection
            peek = ""
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    peek = f.read(200)
            except Exception:
                pass

            script_type = detect_script_type(entry, peek)

            # Match associated jobs referencing this script
            linked_jobs = []
            for j in all_jobs:
                cmd = j.command or ""
                if entry in cmd or f"/data/scripts/{entry}" in cmd:
                    linked_jobs.append({"id": j.id, "name": j.name, "enabled": j.enabled})

            scripts.append({
                "name": entry,
                "path": f"/data/scripts/{entry}",
                "size": st.st_size,
                "modified_at": mod_dt.isoformat(),
                "is_executable": is_exec,
                "type": script_type,
                "job_count": len(linked_jobs),
                "jobs": linked_jobs,
            })
        except Exception as e:
            logger.warning(f"Error inspecting script {entry}: {e}")

    return scripts


def get_script_detail(filename: str, db) -> Dict[str, Any]:
    """Read full script content and metadata."""
    name = sanitize_filename(filename)
    path = get_script_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script '{name}' not found")

    st = os.stat(path)
    is_exec = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    mod_dt = datetime.utcfromtimestamp(st.st_mtime)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    script_type = detect_script_type(name, content)

    # Linked jobs
    all_jobs = db.query(Job).all()
    linked_jobs = []
    for j in all_jobs:
        cmd = j.command or ""
        if name in cmd or f"/data/scripts/{name}" in cmd:
            linked_jobs.append({"id": j.id, "name": j.name, "enabled": j.enabled})

    return {
        "name": name,
        "path": f"/data/scripts/{name}",
        "content": content,
        "size": st.st_size,
        "modified_at": mod_dt.isoformat(),
        "is_executable": is_exec,
        "type": script_type,
        "job_count": len(linked_jobs),
        "jobs": linked_jobs,
    }


def save_script_content(filename: str, content: str, make_executable: bool = True) -> str:
    """Save content to script file, normalize line endings, set executable permissions."""
    name = sanitize_filename(filename)
    path = get_script_path(name)

    # Normalize line endings (CRLF -> LF)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)

    if make_executable:
        try:
            os.chmod(path, 0o755)
        except Exception as e:
            logger.warning(f"Failed to chmod 755 {path}: {e}")

    return name


def delete_script_file(filename: str) -> bool:
    name = sanitize_filename(filename)
    path = get_script_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script '{name}' not found")
    os.remove(path)
    return True


def check_and_correct_syntax(
    filename: str,
    content: str,
    script_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Perform deep syntax validation and generate automated syntax corrections."""
    name = sanitize_filename(filename or "script.sh")
    stype = script_type or detect_script_type(name, content)

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    fixes_available: List[str] = []

    # ── 1. Check line endings (CRLF) ──
    has_crlf = "\r" in content
    if has_crlf:
        warnings.append({
            "line": 1,
            "message": "Windows-style CRLF (\\r\\n) line endings detected.",
            "hint": "CRLF line endings trigger '\\r: command not found' errors in Linux/Docker containers.",
        })
        fixes_available.append("Convert Windows CRLF line endings to Unix LF")

    # ── 2. Check Unicode smart quotes / dashes ──
    smart_chars = {
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "—": "-", "–": "-", "…": "...", " ": " "
    }
    found_smart = [c for c in smart_chars if c in content]
    if found_smart:
        warnings.append({
            "line": 1,
            "message": f"Unicode typography/smart quotes detected: {' '.join(found_smart)}",
            "hint": "Non-ASCII quotes cause shell parsing errors when copying from Word, Notion, or Slack.",
        })
        fixes_available.append("Replace Unicode smart quotes and dashes with ASCII equivalents")

    # ── 3. Check Shebang ──
    lines = content.splitlines()
    has_shebang = len(lines) > 0 and lines[0].startswith("#!")
    if not has_shebang:
        default_shebang = "#!/usr/bin/env python3" if stype == "python" else "#!/usr/bin/env bash"
        warnings.append({
            "line": 1,
            "message": f"No shebang line detected on line 1.",
            "hint": f"A shebang like '{default_shebang}' ensures direct execution via CronDock.",
        })
        fixes_available.append(f"Add shebang '{default_shebang}' to line 1")

    # ── 4. Shell Syntax Verification via bash -n ──
    if stype == "shell":
        try:
            # Test normalized version
            clean_for_test = content.replace("\r\n", "\n").replace("\r", "\n")
            proc = subprocess.run(
                ["bash", "-n"],
                input=clean_for_test,
                text=True,
                capture_output=True,
                timeout=5,
            )
            if proc.returncode != 0 and proc.stderr:
                for line in proc.stderr.splitlines():
                    # Parse "bash: line 12: syntax error near unexpected token 'fi'"
                    m = re.search(r'line\s+(\d+):\s*(.*)', line)
                    if m:
                        line_no = int(m.group(1))
                        msg = m.group(2).strip()
                        # Deduplicate backtick line echo
                        if msg.startswith("`") and msg.endswith("'"):
                            continue

                        hint = ""
                        if "unexpected token `fi'" in msg or "unexpected token 'fi'" in msg:
                            hint = "Missing 'then' statement after 'if', or unbalanced conditional."
                        elif "unexpected token `done'" in msg or "unexpected token 'done'" in msg:
                            hint = "Missing 'do' statement after 'for'/'while', or unbalanced loop."
                        elif "unexpected EOF" in msg or "unexpected end of file" in msg:
                            hint = "Unclosed quote, bracket, parenthesis, heredoc, or conditional block."
                        elif "syntax error near unexpected token" in msg:
                            hint = "Check surrounding keywords, quotes, and punctuation."

                        errors.append({
                            "line": line_no,
                            "message": msg,
                            "hint": hint,
                        })
                    elif "syntax error" in line.lower():
                        errors.append({
                            "line": 1,
                            "message": line.strip(),
                            "hint": "Check script structure and shell syntax.",
                        })
        except subprocess.TimeoutExpired:
            warnings.append({
                "line": 1,
                "message": "Bash syntax check timed out.",
                "hint": "Script may contain large recursive structures.",
            })
        except Exception as e:
            logger.warning(f"Could not run bash -n check: {e}")

    # ── 5. Python Syntax Verification via ast.parse ──
    elif stype == "python":
        try:
            clean_for_test = content.replace("\r\n", "\n").replace("\r", "\n")
            ast.parse(clean_for_test, filename=name)
        except SyntaxError as e:
            hint = ""
            if "invalid syntax" in str(e.msg):
                hint = "Check indentation, colons after def/if/for/class, or unmatched parentheses."
            elif "unindent does not match" in str(e.msg):
                hint = "Inconsistent indentation (mix of tabs and spaces or wrong indentation depth)."
            elif "EOL while scanning string literal" in str(e.msg):
                hint = "Unterminated string literal (missing closing quote)."

            errors.append({
                "line": e.lineno or 1,
                "column": e.offset,
                "message": str(e.msg),
                "hint": hint,
                "snippet": e.text.strip() if e.text else None,
            })
        except Exception as e:
            errors.append({
                "line": 1,
                "message": f"Syntax parsing error: {e}",
                "hint": "Check Python syntax.",
            })

    # ── 6. Compute auto-fixed content ──
    fixed_content = content
    # Fix CRLF
    if has_crlf:
        fixed_content = fixed_content.replace("\r\n", "\n").replace("\r", "\n")
    # Fix smart quotes
    for bad, good in smart_chars.items():
        if bad in fixed_content:
            fixed_content = fixed_content.replace(bad, good)
    # Fix missing shebang
    if not has_shebang:
        default_shebang = "#!/usr/bin/env python3" if stype == "python" else "#!/usr/bin/env bash"
        fixed_content = f"{default_shebang}\n\n{fixed_content.lstrip()}"
    # Ensure trailing newline
    if fixed_content and not fixed_content.endswith("\n"):
        fixed_content += "\n"

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "type": stype,
        "errors": errors,
        "warnings": warnings,
        "fixes_available": fixes_available,
        "fixed_content": fixed_content if fixes_available else None,
    }


def test_run_script(filename: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute a script in a test execution subshell with real-time output capture."""
    name = sanitize_filename(filename)
    path = get_script_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script '{name}' not found")

    # Ensure executable
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass

    stype = detect_script_type(name)
    if stype == "python":
        cmd = ["python3", path]
    else:
        cmd = ["/bin/bash", path]

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SCRIPTS_DIR,
        )
        duration_ms = int((time.time() - start_time) * 1000)
        output = (proc.stdout + proc.stderr).strip()
        return {
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "output": output,
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "exit_code": -1,
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
            "output": f"Execution timed out after {timeout} seconds.",
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "exit_code": -1,
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "output": str(e),
            "duration_ms": duration_ms,
        }
