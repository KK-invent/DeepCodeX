#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import plistlib
import secrets
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


HOME = Path.home()
DEEPCODEX_HOME = Path(os.environ.get("DEEPCODEX_HOME", HOME / ".codex-deepseek"))
DEEPCODEX_APP = Path(os.environ.get("DEEPCODEX_APP", "/Applications/Deepcodex.app"))
USER_DATA = HOME / "Library/Application Support/Deepcodex"
CONFIG = DEEPCODEX_HOME / "config.toml"
SECRETS = DEEPCODEX_HOME / "secrets.env"
AUTH = DEEPCODEX_HOME / "auth.json"
CCX_CONFIG = DEEPCODEX_HOME / "ccx" / ".config" / "config.json"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
APP_BACKUPS = DEEPCODEX_HOME / "app-backups"
LAUNCHD_DOMAIN = os.environ.get("DEEPCODEX_LAUNCHD_DOMAIN", os.environ.get("DEEPCODEX_LAUNCHD_PREFIX", "com.deepcodex"))
CCX_LABEL = os.environ.get("DEEPCODEX_CCX_LABEL", f"{LAUNCHD_DOMAIN}.ccx-deepseek")
BRIDGE_LABEL = os.environ.get("DEEPCODEX_BRIDGE_LABEL", f"{LAUNCHD_DOMAIN}.deepseek-bridge")
IMAGE_STRIP_LABEL = os.environ.get("DEEPCODEX_IMAGE_STRIP_LABEL", f"{LAUNCHD_DOMAIN}.deepcodex-image-strip")


def fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 2


def backup_file(path: Path, tag: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak.{tag}")
    shutil.copy2(path, backup)
    return backup


def backup_app_file(path: Path, tag: str) -> Path | None:
    if not path.exists():
        return None
    APP_BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = APP_BACKUPS / f"{path.name}.bak.{tag}"
    shutil.copy2(path, backup)
    return backup


def run_allow_failure(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def read_key(args: argparse.Namespace) -> str:
    if args.keep_existing_key:
        key = current_deepseek_api_key()
        if not key:
            raise RuntimeError("no existing DeepSeek upstream API key to keep")
        return key
    if args.key_env:
        key = os.environ.get(args.key_env, "")
        if not key:
            raise RuntimeError(f"environment variable {args.key_env!r} is empty")
        return key.strip()
    if args.key_stdin:
        return sys.stdin.read().strip()

    key = getpass.getpass("DeepSeek upstream API key: ").strip()
    if not args.no_confirm:
        again = getpass.getpass("Confirm API key: ").strip()
        if key != again:
            raise RuntimeError("keys did not match")
    return key


def current_deepseek_entry() -> dict | None:
    if not CCX_CONFIG.exists():
        return None
    try:
        config = json.loads(CCX_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    for upstream in config.get("responsesUpstream", []):
        if not isinstance(upstream, dict):
            continue
        models = upstream.get("supportedModels") or []
        if "deepseek-v4-flash" in models or "deepseek-v4-pro" in models or upstream.get("name") == "DeepSeek Chat":
            return upstream
    return None


def current_deepseek_base_url() -> str | None:
    base_url = read_env_value(SECRETS, "DEEPSEEK_BASE_URL")
    if base_url:
        return base_url
    upstream = current_deepseek_entry()
    if upstream:
        base_url = upstream.get("baseUrl")
        if isinstance(base_url, str) and base_url.strip():
            return base_url.strip()
    return None


def current_deepseek_api_key() -> str | None:
    # First try secrets.env (new bridge location), then legacy config for backward compatibility.
    key = read_env_value(SECRETS, "DEEPSEEK_API_KEY")
    if key:
        return key
    upstream = current_deepseek_entry()
    if upstream:
        keys = upstream.get("apiKeys") or []
        if isinstance(keys, list) and keys and isinstance(keys[0], str) and keys[0].strip():
            return keys[0].strip()
    return None


def read_base_url(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url.strip()
    if args.base_url_env:
        value = os.environ.get(args.base_url_env, "")
        if not value:
            raise RuntimeError(f"environment variable {args.base_url_env!r} is empty")
        return value.strip()

    default = current_deepseek_base_url() or DEFAULT_DEEPSEEK_BASE_URL
    entered = input(f"DeepSeek base URL [{default}]: ").strip()
    return entered or default


def validate_key(key: str) -> None:
    if not key:
        raise RuntimeError("API key is empty")
    if any(ch.isspace() for ch in key):
        raise RuntimeError("API key contains whitespace")
    if len(key) < 8:
        raise RuntimeError("API key is too short")


def validate_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    if not base_url:
        raise RuntimeError("DeepSeek base URL is empty")
    if any(ch.isspace() for ch in base_url):
        raise RuntimeError("DeepSeek base URL contains whitespace")
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("DeepSeek base URL must be an http(s) URL")
    return base_url


def load_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def set_env_value(lines: list[str], name: str, value: str) -> tuple[list[str], bool]:
    rendered = f"{name}={value}"
    changed = False
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{name}="):
            found = True
            if line != rendered:
                changed = True
            out.append(rendered)
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(rendered)
        changed = True
    return out, changed


def read_env_presence(path: Path, name: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.startswith(f"{name}="):
            return bool(stripped.split("=", 1)[1].strip())
    return False


def read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.startswith(f"{name}="):
            value = stripped.split("=", 1)[1].strip()
            return value or None
    return None


def choose_proxy_key(args: argparse.Namespace) -> str:
    if args.proxy_key_env:
        key = os.environ.get(args.proxy_key_env, "")
        if not key:
            raise RuntimeError(f"environment variable {args.proxy_key_env!r} is empty")
        validate_key(key.strip())
        return key.strip()
    existing = read_env_value(SECRETS, "CCX_PROXY_ACCESS_KEY")
    if existing and not args.rotate_proxy_key:
        return existing
    return "dcx-" + secrets.token_urlsafe(32)


def write_secrets(proxy_key: str, base_url: str, deepseek_key: str, tag: str) -> list[str]:
    actions: list[str] = []
    DEEPCODEX_HOME.mkdir(parents=True, exist_ok=True)
    backup = backup_file(SECRETS, tag)
    if backup:
        actions.append(f"backed up secrets.env to {backup}")
    lines = load_env_lines(SECRETS)
    changed_any = False
    for name, value in (
        ("CCX_PROXY_ACCESS_KEY", proxy_key),
        ("DEEPSEEK_BASE_URL", base_url),
        ("DEEPSEEK_API_KEY", deepseek_key),
    ):
        lines, changed = set_env_value(lines, name, value)
        changed_any = changed_any or changed
    if changed_any or not SECRETS.exists():
        SECRETS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(SECRETS, stat.S_IRUSR | stat.S_IWUSR)
        actions.append("wrote proxy key, base URL, and API key to secrets.env")
    else:
        actions.append("secrets.env already contains proxy key, base URL, and API key")
    return actions


def write_auth(proxy_key: str, tag: str) -> list[str]:
    actions: list[str] = []
    auth: dict = {}
    if AUTH.exists():
        backup = backup_file(AUTH, tag)
        if backup:
            actions.append(f"backed up auth.json to {backup}")
        try:
            auth = json.loads(AUTH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            auth = {}
    auth["auth_mode"] = "apikey"
    auth["OPENAI_API_KEY"] = proxy_key
    auth.pop("tokens", None)
    AUTH.write_text(json.dumps(auth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(AUTH, stat.S_IRUSR | stat.S_IWUSR)
    actions.append("wrote apikey auth.json for DeepCodex local provider")
    return actions


def load_plist(path: Path) -> dict:
    with path.open("rb") as fh:
        return plistlib.load(fh)


def write_plist(path: Path, info: dict) -> None:
    with path.open("wb") as fh:
        plistlib.dump(info, fh)


def update_info_plist(proxy_key: str, tag: str) -> list[str]:
    info_path = DEEPCODEX_APP / "Contents/Info.plist"
    if not info_path.exists():
        return [f"skipped Info.plist update; missing {info_path}"]
    backup = backup_app_file(info_path, tag)
    info = load_plist(info_path)
    env = dict(info.get("LSEnvironment", {}))
    env.update(
        {
            "CODEX_HOME": str(DEEPCODEX_HOME),
            "CODEX_ELECTRON_USER_DATA_PATH": str(USER_DATA),
            "CODEX_DEEPSEEK_APP": "1",
            "CODEX_SPARKLE_ENABLED": "false",
            "CCX_PROXY_ACCESS_KEY": proxy_key,
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
    )
    info["LSEnvironment"] = env
    write_plist(info_path, info)
    actions = ["updated DeepCodex Info.plist LSEnvironment"]
    if backup:
        actions.insert(0, f"backed up Info.plist to {backup}")
    return actions


def write_ccx_config(api_key: str, base_url: str, tag: str) -> list[str]:
    actions: list[str] = []
    CCX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if CCX_CONFIG.exists():
        backup = backup_file(CCX_CONFIG, tag)
        if backup:
            actions.append(f"backed up legacy bridge config.json to {backup}")
        try:
            config = json.loads(CCX_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}

    upstreams = config.get("responsesUpstream")
    if not isinstance(upstreams, list):
        upstreams = []

    deepseek_entry = None
    for upstream in upstreams:
        if not isinstance(upstream, dict):
            continue
        models = upstream.get("supportedModels") or []
        if "deepseek-v4-flash" in models or "deepseek-v4-pro" in models or upstream.get("name") == "DeepSeek Chat":
            deepseek_entry = upstream
            break
    if deepseek_entry is None:
        deepseek_entry = {}
        upstreams.insert(0, deepseek_entry)

    deepseek_entry.update(
        {
            "name": "DeepSeek Chat",
            "serviceType": "openai",
            "baseUrl": base_url,
            "apiKeys": [api_key],
            "supportedModels": ["deepseek-v4-pro", "deepseek-v4-flash"],
            "modelMapping": {"gpt": "deepseek-v4-pro", "mini": "deepseek-v4-flash"},
            "normalizeNonstandardChatRoles": True,
            "codexNativeToolPassthrough": True,
            "priority": 0,
            "status": "active",
        }
    )
    config["responsesUpstream"] = upstreams
    config.setdefault("fuzzyModeEnabled", True)
    config.setdefault("stripBillingHeader", True)
    CCX_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(CCX_CONFIG, stat.S_IRUSR | stat.S_IWUSR)
    actions.append(f"wrote DeepSeek upstream base URL to bridge compatibility config: {base_url}")
    actions.append("wrote DeepSeek upstream API key to bridge compatibility config without printing it")
    return actions


def set_top_level_value(config_text: str, key: str, rendered_value: str) -> tuple[str, bool]:
    lines = config_text.splitlines()
    first_section = next((idx for idx, line in enumerate(lines) if line.strip().startswith("[")), len(lines))
    for idx in range(first_section):
        if lines[idx].strip().startswith(f"{key} ="):
            new_line = f"{key} = {rendered_value}"
            if lines[idx] == new_line:
                return config_text, False
            lines[idx] = new_line
            return "\n".join(lines) + "\n", True
    lines.insert(first_section, f"{key} = {rendered_value}")
    return "\n".join(lines) + "\n", True


def set_section_value(config_text: str, section_header: str, key: str, rendered_value: str) -> tuple[str, bool]:
    lines = config_text.splitlines()
    section_idx = None
    next_section_idx = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section_header:
            section_idx = idx
            continue
        if section_idx is not None and stripped.startswith("["):
            next_section_idx = idx
            break
    if section_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([section_header, f"{key} = {rendered_value}"])
        return "\n".join(lines) + "\n", True
    for idx in range(section_idx + 1, next_section_idx):
        if lines[idx].strip().startswith(f"{key} ="):
            new_line = f"{key} = {rendered_value}"
            if lines[idx] == new_line:
                return config_text, False
            lines[idx] = new_line
            return "\n".join(lines) + "\n", True
    lines.insert(next_section_idx, f"{key} = {rendered_value}")
    return "\n".join(lines) + "\n", True


def update_config(tag: str) -> list[str]:
    actions: list[str] = []
    text = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else ""
    backup = backup_file(CONFIG, tag)
    if backup:
        actions.append(f"backed up config.toml to {backup}")
    for key, rendered in (
        ("model", '"deepseek-v4-flash"'),
        ("model_provider", '"ccx-deepseek"'),
        ("forced_login_method", '"api"'),
        ("check_for_update_on_startup", "false"),
        ("model_context_window", "1000000"),
        ("model_auto_compact_token_limit", "700000"),
    ):
        text, changed = set_top_level_value(text, key, rendered)
        if changed:
            actions.append(f"set {key}")
    for key, rendered in (
        ("name", '"DeepSeek"'),
        ("base_url", '"http://127.0.0.1:3100/v1"'),
        ("wire_api", '"responses"'),
        ("env_key", '"CCX_PROXY_ACCESS_KEY"'),
        ("env_key_instructions", '"Configure with deepcodex-configure-deepseek.py; stored in DEEPCODEX_HOME/secrets.env"'),
        ("request_max_retries", "3"),
        ("stream_idle_timeout_ms", "300000"),
    ):
        text, changed = set_section_value(text, "[model_providers.ccx-deepseek]", key, rendered)
        if changed:
            actions.append(f"set provider {key}")
    CONFIG.write_text(text, encoding="utf-8")
    return actions


def restart_services() -> list[str]:
    actions: list[str] = []
    code, out = run_allow_failure(["launchctl", "bootout", f"gui/{os.getuid()}/{CCX_LABEL}"])
    if code == 0:
        actions.append(f"stopped legacy {CCX_LABEL}")
    elif "could not find service" not in out.lower():
        actions.append(f"legacy {CCX_LABEL} was not stopped: {out.strip() or 'not loaded'}")
    for label in (BRIDGE_LABEL, IMAGE_STRIP_LABEL):
        target = f"gui/{os.getuid()}/{label}"
        code, out = run_allow_failure(["launchctl", "kickstart", "-k", target])
        if code == 0:
            actions.append(f"restarted {label}")
        else:
            actions.append(f"could not restart {label}: {out.strip() or 'not loaded'}")
    return actions


def resign_app() -> list[str]:
    if not DEEPCODEX_APP.exists():
        return [f"skipped codesign; missing {DEEPCODEX_APP}"]
    code, out = run_allow_failure(["codesign", "--force", "--deep", "--sign", "-", str(DEEPCODEX_APP)])
    if code != 0:
        raise RuntimeError("codesign failed after Info.plist update: " + (out.strip() or f"exit {code}"))
    return ["codesigned DeepCodex app after Info.plist update"]


def status_info() -> dict:
    missing: list[str] = []
    proxy_present = read_env_presence(SECRETS, "CCX_PROXY_ACCESS_KEY")
    base_url_secret_present = read_env_presence(SECRETS, "DEEPSEEK_BASE_URL")
    base_url = current_deepseek_base_url() or DEFAULT_DEEPSEEK_BASE_URL
    upstream_key_present = bool(current_deepseek_api_key())
    if not read_env_presence(SECRETS, "CCX_PROXY_ACCESS_KEY"):
        missing.append("secrets.env:CCX_PROXY_ACCESS_KEY")
    if not read_env_presence(SECRETS, "DEEPSEEK_BASE_URL"):
        missing.append("secrets.env:DEEPSEEK_BASE_URL")
    if not read_env_presence(SECRETS, "DEEPSEEK_API_KEY"):
        missing.append("secrets.env:DEEPSEEK_API_KEY")
    if not AUTH.exists():
        missing.append("auth.json")
    else:
        try:
            auth = json.loads(AUTH.read_text(encoding="utf-8"))
            if auth.get("auth_mode") != "apikey" or not auth.get("OPENAI_API_KEY"):
                missing.append("auth.json apikey")
            if "tokens" in auth:
                missing.append("auth.json contains ChatGPT tokens")
        except json.JSONDecodeError:
            missing.append("auth.json parse")
    info_path = DEEPCODEX_APP / "Contents/Info.plist"
    if info_path.exists():
        env = load_plist(info_path).get("LSEnvironment", {})
        if not env.get("CCX_PROXY_ACCESS_KEY"):
            missing.append("Info.plist:LSEnvironment:CCX_PROXY_ACCESS_KEY")

    return {
        "configured": not missing,
        "missing": missing,
        "base_url": base_url,
        "upstream_api_key_present": upstream_key_present,
        "local_proxy_key_present": proxy_present,
        "deepseek_api_key_present": read_env_presence(SECRETS, "DEEPSEEK_API_KEY"),
        "base_url_secret_present": base_url_secret_present,
    }


def print_status_json() -> int:
    print(json.dumps(status_info(), ensure_ascii=False, sort_keys=True))
    return 0


def check_status() -> int:
    status = status_info()
    if status["missing"]:
        print("[FAIL] DeepSeek API entry incomplete: " + ", ".join(status["missing"]))
        return 2
    print("[OK] DeepSeek API entry configured; base URL present and secret values are not printed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure DeepCodex's DeepSeek base URL and API key without printing secrets.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--key-env", metavar="ENV", help="read the upstream DeepSeek API key from an environment variable")
    source.add_argument("--key-stdin", action="store_true", help="read the upstream DeepSeek API key from stdin")
    source.add_argument("--keep-existing-key", action="store_true", help="reuse the existing upstream DeepSeek API key")
    parser.add_argument("--base-url", metavar="URL", help=f"upstream DeepSeek/OpenAI-compatible base URL; default: {DEFAULT_DEEPSEEK_BASE_URL}")
    parser.add_argument("--base-url-env", metavar="ENV", help="read the upstream DeepSeek base URL from an environment variable")
    parser.add_argument("--proxy-key-env", metavar="ENV", help="read the local bridge/shim access key from an environment variable; otherwise keep or generate one")
    parser.add_argument("--rotate-proxy-key", action="store_true", help="generate a new local bridge/shim access key")
    parser.add_argument("--no-confirm", action="store_true", help="do not ask for a second interactive confirmation")
    parser.add_argument("--check", action="store_true", help="check whether the DeepSeek API entry is configured; no writes")
    parser.add_argument("--status-json", action="store_true", help="print non-secret DeepSeek configuration status as JSON; no writes")
    parser.add_argument("--restart-services", action="store_true", help="restart deepseek-bridge and image-strip launchd services after writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.status_json:
        return print_status_json()
    if args.check:
        return check_status()

    tag = "before-deepseek-api-config-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        api_key = read_key(args)
        validate_key(api_key)
        base_url = validate_base_url(read_base_url(args))
        proxy_key = choose_proxy_key(args)
        actions: list[str] = []
        actions.extend(write_ccx_config(api_key, base_url, tag))
        actions.extend(write_secrets(proxy_key, base_url, api_key, tag))
        actions.extend(write_auth(proxy_key, tag))
        actions.extend(update_info_plist(proxy_key, tag))
        actions.extend(resign_app())
        actions.extend(update_config(tag))
        if args.restart_services:
            actions.extend(restart_services())
    except Exception as exc:
        return fail(str(exc))

    for action in actions:
        print(f"[OK] {action}")
    print("[OK] DeepSeek API configured. Secret values were not printed.")
    print("Next: restart DeepCodex so the updated Info.plist environment is loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
