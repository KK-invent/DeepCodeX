#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import plistlib
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path


def env_path(name: str, default: str | Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


HOME = env_path("DEEPCODEX_USER_HOME", Path.home())
DEEPCODEX_HOME = env_path("DEEPCODEX_HOME", HOME / ".codex-deepseek")
DEEPCODEX_APP = env_path("DEEPCODEX_APP", "/Applications/Deepcodex.app")
CODEX_APP = env_path("CODEX_APP", "/Applications/Codex.app")
CONFIG = DEEPCODEX_HOME / "config.toml"
AUTH = DEEPCODEX_HOME / "auth.json"
SECRETS = DEEPCODEX_HOME / "secrets.env"
CCX_CONFIG = DEEPCODEX_HOME / "ccx" / ".config" / "config.json"
CONFIGURE_DEEPSEEK_SCRIPT = DEEPCODEX_HOME / "bin" / "deepcodex-configure-deepseek.py"
LAUNCH_AGENTS = HOME / "Library/LaunchAgents"
LAUNCHD_DOMAIN = os.environ.get("DEEPCODEX_LAUNCHD_DOMAIN", os.environ.get("DEEPCODEX_LAUNCHD_PREFIX", "com.deepcodex"))
HYBRID_ROUTER_LABEL = os.environ.get("DEEPCODEX_HYBRID_ROUTER_LABEL", f"{LAUNCHD_DOMAIN}.deepcodex-hybrid-router")
CCX_LABEL = os.environ.get("DEEPCODEX_CCX_LABEL", f"{LAUNCHD_DOMAIN}.ccx-deepseek")
IMAGE_STRIP_LABEL = os.environ.get("DEEPCODEX_IMAGE_STRIP_LABEL", f"{LAUNCHD_DOMAIN}.deepcodex-image-strip")
BRIDGE_LABEL = os.environ.get("DEEPCODEX_BRIDGE_LABEL", f"{LAUNCHD_DOMAIN}.deepseek-bridge")
BACKUP_LABEL = os.environ.get("DEEPCODEX_BACKUP_LABEL", f"{LAUNCHD_DOMAIN}.deepcodex-backup")
CCX_PLIST = LAUNCH_AGENTS / f"{CCX_LABEL}.plist"
BRIDGE_PLIST = LAUNCH_AGENTS / f"{BRIDGE_LABEL}.plist"
IMAGE_STRIP_PLIST = LAUNCH_AGENTS / f"{IMAGE_STRIP_LABEL}.plist"
LOG_PRUNE_SCRIPT = DEEPCODEX_HOME / "bin" / "deepcodex-log-prune.py"
APP_ASAR = DEEPCODEX_APP / "Contents/Resources/app.asar"
ICON_ASSET = DEEPCODEX_HOME / "assets/Deepcodex.icns"
MAIN_ICON_FILES = ("Deepcodex.icns", "icon.icns", "electron.icns")
HELPER_ICON_GLOB = "Contents/Frameworks/Codex Helper*.app"

EXPECTED_CODEX_HOME = str(DEEPCODEX_HOME)
EXPECTED_USER_DATA = str(HOME / "Library/Application Support/Deepcodex")
EXPECTED_DISPLAY_NAME = "DeepCodex"
EXPECTED_BUNDLE_NAME = "Codex"
EXPECTED_BUNDLE_ID = "com.openai.codex.deepcodex"
SUPPORTED_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
DEEPSEEK_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
LONG_CONTEXT_MODELS = SUPPORTED_MODELS
EXPECTED_CONTEXT_WINDOW = "1000000"
EXPECTED_AUTO_COMPACT_LIMIT = "700000"
EXPECTED_AUTH_MODE = "apikey"
# 所见即所得：思考强度由 UI 选择决定（思考=high / 深度思考=xhigh→max）。
# doctor 只校验值是否为 DeepSeek 合法档位，不再钉死某一档。
VALID_REASONING = {"high", "max", "xhigh"}
EXPECTED_PROVIDER_TABLE = "[model_providers.ccx-deepseek]"
EXPECTED_PROVIDER_NAME = 'name = "DeepSeek"'
EXPECTED_FORCED_LOGIN_METHOD = 'forced_login_method = "api"'
EXPECTED_UPDATE_CHECK = "check_for_update_on_startup = false"


@dataclass
class CheckResult:
    level: str
    title: str
    detail: str


def load_plist(path: Path) -> dict:
    with path.open("rb") as fh:
        return plistlib.load(fh)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def env_secret_present(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(f"{key}="):
            return bool(line.split("=", 1)[1].strip())
    return False


def top_level_key_exists(config_text: str, key: str) -> bool:
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            return False
        if line.startswith(f"{key} ="):
            return True
    return False


def top_level_value(config_text: str, key: str) -> str | None:
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            return None
        match = re.match(rf"^{re.escape(key)}\s*=\s*(.+?)\s*$", line)
        if match:
            value = match.group(1)
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                return value[1:-1]
            return value
    return None


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)


def run_allow_failure(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def launchctl_target(label: str) -> str:
    return f"gui/{os.getuid()}/{label}"


def tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    """实际尝试连一下端口——launchd 列着 ≠ 进程真能服务（可能 wedge）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_tcp(host: str, port: int, deadline_seconds: float = 8.0) -> bool:
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        if tcp_open(host, port, timeout=0.5):
            return True
        time.sleep(0.25)
    return tcp_open(host, port, timeout=0.5)


def backup_file(path: Path, tag: str) -> Path:
    backup = path.with_name(f"{path.name}.bak.{tag}")
    shutil.copy2(path, backup)
    return backup


def set_top_level_value(config_text: str, key: str, rendered_value: str) -> tuple[str, bool]:
    lines = config_text.splitlines()
    first_section = next((idx for idx, line in enumerate(lines) if line.strip().startswith("[")), len(lines))
    for idx in range(first_section):
        stripped = lines[idx].strip()
        if stripped.startswith(f"{key} ="):
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
        stripped = lines[idx].strip()
        if stripped.startswith(f"{key} ="):
            new_line = f"{key} = {rendered_value}"
            if lines[idx] == new_line:
                return config_text, False
            lines[idx] = new_line
            return "\n".join(lines) + "\n", True
    lines.insert(next_section_idx, f"{key} = {rendered_value}")
    return "\n".join(lines) + "\n", True


def normalize_config(config_text: str) -> tuple[str, list[str]]:
    actions: list[str] = []
    model = top_level_value(config_text, "model")
    provider = top_level_value(config_text, "model_provider")

    if model not in DEEPSEEK_MODELS:
        config_text, changed = set_top_level_value(config_text, "model", '"deepseek-v4-flash"')
        if changed:
            actions.append("set model = deepseek-v4-flash")
        model = "deepseek-v4-flash"

    new_text, changed = set_top_level_value(config_text, "model_context_window", EXPECTED_CONTEXT_WINDOW)
    if changed:
        actions.append("set model_context_window = 1000000")
    config_text = new_text

    new_text, changed = set_top_level_value(config_text, "model_auto_compact_token_limit", EXPECTED_AUTO_COMPACT_LIMIT)
    if changed:
        actions.append("set model_auto_compact_token_limit = 700000")
    config_text = new_text

    if provider != "ccx-deepseek":
        config_text, changed = set_top_level_value(config_text, "model_provider", '"ccx-deepseek"')
        if changed:
            actions.append("routed DeepCodex to DeepSeek local provider")

    config_text, changed = set_top_level_value(config_text, "forced_login_method", '"api"')
    if changed:
        actions.append("forced API-key auth mode")

    config_text, changed = set_top_level_value(config_text, "check_for_update_on_startup", "false")
    if changed:
        actions.append("disabled Codex CLI update check on DeepCodex startup")

    config_text, changed = set_section_value(
        config_text,
        EXPECTED_PROVIDER_TABLE,
        "base_url",
        '"http://127.0.0.1:3100/v1"',
    )
    if changed:
        actions.append("normalized DeepSeek base_url to shim(3100)")

    for key, value in (
        ("HTTP_PROXY", '""'),
        ("http_proxy", '""'),
        ("ALL_PROXY", '""'),
        ("all_proxy", '""'),
        ("NO_PROXY", '"127.0.0.1,localhost,::1"'),
        ("no_proxy", '"127.0.0.1,localhost,::1"'),
    ):
        config_text, changed = set_section_value(config_text, "[shell_environment_policy.set]", key, value)
        if changed:
            actions.append(f"normalized shell_environment_policy.set.{key}")

    return config_text, actions


def launchctl_load_or_restart(plist: Path, label: str) -> str:
    target = launchctl_target(label)
    code, out = run_allow_failure(["launchctl", "kickstart", "-k", target])
    if code == 0:
        return f"restarted {label}"
    code, out = run_allow_failure(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)])
    if code != 0 and "already bootstrapped" not in out.lower():
        raise RuntimeError(out.strip() or f"bootstrap failed for {label}")
    code, out = run_allow_failure(["launchctl", "kickstart", "-k", target])
    if code != 0:
        raise RuntimeError(out.strip() or f"kickstart failed for {label}")
    return f"restarted {label}"


def repair_environment() -> list[str]:
    actions: list[str] = []
    config_text = load_text(CONFIG)
    normalized_text, config_actions = normalize_config(config_text)
    if normalized_text != config_text:
        backup = backup_file(CONFIG, "before-repair")
        CONFIG.write_text(normalized_text, encoding="utf-8")
        actions.append(f"backed up config to {backup}")
        actions.extend(config_actions)

    code, out = run_allow_failure(["launchctl", "remove", HYBRID_ROUTER_LABEL])
    if code == 0 or "could not find service" not in out.lower():
        actions.append("removed legacy hybrid router launchd service")

    code, out = run_allow_failure(["launchctl", "bootout", launchctl_target(CCX_LABEL)])
    if code == 0:
        actions.append("stopped legacy ccx launchd service")
    elif "could not find service" not in out.lower():
        actions.append("legacy ccx launchd service was not stopped: " + (out.strip() or "not loaded"))

    if BRIDGE_PLIST.exists():
        actions.append(launchctl_load_or_restart(BRIDGE_PLIST, BRIDGE_LABEL))
        if wait_tcp("127.0.0.1", 3000):
            actions.append("deepseek-bridge port 3000 is ready")
        else:
            actions.append("deepseek-bridge port 3000 is not ready yet")
    else:
        actions.append(f"missing {BRIDGE_PLIST}")

    if IMAGE_STRIP_PLIST.exists():
        actions.append(launchctl_load_or_restart(IMAGE_STRIP_PLIST, IMAGE_STRIP_LABEL))
        if wait_tcp("127.0.0.1", 3100):
            actions.append("image-strip port 3100 is ready")
        else:
            actions.append("image-strip port 3100 is not ready yet")
    else:
        actions.append(f"missing {IMAGE_STRIP_PLIST}")

    return actions


def check_apps_exist(results: list[CheckResult]) -> None:
    for path in (CODEX_APP, DEEPCODEX_APP, CONFIG, AUTH):
        if not path.exists():
            results.append(CheckResult("FAIL", "required-path", f"missing: {path}"))


def check_info_plist(results: list[CheckResult], info: dict, source_info: dict) -> None:
    env = info.get("LSEnvironment", {})
    if info.get("CFBundleDisplayName") != EXPECTED_DISPLAY_NAME:
        results.append(CheckResult("FAIL", "display-name", f'expected "{EXPECTED_DISPLAY_NAME}", got "{info.get("CFBundleDisplayName")}"'))
    else:
        results.append(CheckResult("OK", "display-name", EXPECTED_DISPLAY_NAME))

    if info.get("CFBundleName") != EXPECTED_BUNDLE_NAME:
        results.append(CheckResult("FAIL", "bundle-name", f'expected "{EXPECTED_BUNDLE_NAME}", got "{info.get("CFBundleName")}"'))
    else:
        results.append(CheckResult("OK", "bundle-name", "helper app compatibility preserved"))

    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        results.append(CheckResult("FAIL", "bundle-id", f'expected "{EXPECTED_BUNDLE_ID}", got "{info.get("CFBundleIdentifier")}"'))
    else:
        results.append(CheckResult("OK", "bundle-id", EXPECTED_BUNDLE_ID))

    if not ICON_ASSET.exists():
        results.append(CheckResult("WARN", "app-icon", f"custom icon asset not packaged: {ICON_ASSET}"))
    elif info.get("CFBundleIconFile") != "Deepcodex.icns":
        results.append(CheckResult("FAIL", "app-icon", f'expected Deepcodex.icns, got "{info.get("CFBundleIconFile")}"'))
    elif info.get("CFBundleIconName"):
        results.append(CheckResult("FAIL", "app-icon", "CFBundleIconName should be absent so system surfaces use Deepcodex.icns"))
    else:
        icon_failures: list[str] = []
        if not ICON_ASSET.exists():
            icon_failures.append(f"missing asset {ICON_ASSET}")
        else:
            expected_hash = sha256_file(ICON_ASSET)
            for name in MAIN_ICON_FILES:
                path = DEEPCODEX_APP / "Contents/Resources" / name
                if not path.exists():
                    icon_failures.append(f"missing {path}")
                elif sha256_file(path) != expected_hash:
                    icon_failures.append(f"hash mismatch {path}")
            for helper in sorted(DEEPCODEX_APP.glob(HELPER_ICON_GLOB)):
                helper_info = load_plist(helper / "Contents/Info.plist")
                helper_icon = helper / "Contents/Resources/Deepcodex.icns"
                if helper_info.get("CFBundleIconFile") != "Deepcodex.icns":
                    icon_failures.append(f"helper plist icon mismatch {helper}")
                elif helper_info.get("CFBundleIconName"):
                    icon_failures.append(f"helper CFBundleIconName should be absent {helper}")
                elif not helper_icon.exists():
                    icon_failures.append(f"missing {helper_icon}")
                elif sha256_file(helper_icon) != expected_hash:
                    icon_failures.append(f"hash mismatch {helper_icon}")

        if icon_failures:
            results.append(CheckResult("FAIL", "app-icon", "; ".join(icon_failures[:5])))
        else:
            results.append(CheckResult("OK", "app-icon", "Deepcodex.icns installed for main bundle and Electron helpers"))

    if env.get("CODEX_HOME") != EXPECTED_CODEX_HOME:
        results.append(CheckResult("FAIL", "codex-home", f'expected "{EXPECTED_CODEX_HOME}", got "{env.get("CODEX_HOME")}"'))
    else:
        results.append(CheckResult("OK", "codex-home", EXPECTED_CODEX_HOME))

    if env.get("CODEX_ELECTRON_USER_DATA_PATH") != EXPECTED_USER_DATA:
        results.append(CheckResult("FAIL", "user-data-path", f'expected "{EXPECTED_USER_DATA}", got "{env.get("CODEX_ELECTRON_USER_DATA_PATH")}"'))
    else:
        results.append(CheckResult("OK", "user-data-path", EXPECTED_USER_DATA))

    if env.get("LANG") != "zh_CN.UTF-8":
        results.append(CheckResult("WARN", "locale", f'LANG is "{env.get("LANG")}", expected zh_CN.UTF-8'))
    else:
        results.append(CheckResult("OK", "locale", "zh_CN.UTF-8"))

    if not env.get("CCX_PROXY_ACCESS_KEY"):
        results.append(CheckResult("FAIL", "deepseek-env", "missing CCX_PROXY_ACCESS_KEY in DeepCodex LSEnvironment"))
    elif any(key in env for key in ("BXCV_API_KEY", "TRANSFORM_API_KEY")):
        results.append(CheckResult("FAIL", "deepseek-env", "stale non-DeepSeek provider keys remain in DeepCodex LSEnvironment"))
    elif env.get("CODEX_SPARKLE_ENABLED") != "false":
        results.append(CheckResult("FAIL", "deepseek-env", "CODEX_SPARKLE_ENABLED must be false to avoid startup update checks"))
    else:
        results.append(CheckResult("OK", "deepseek-env", "DeepSeek-only env present; Sparkle disabled"))

    source_ver = str(source_info.get("CFBundleShortVersionString", ""))
    target_ver = str(info.get("CFBundleShortVersionString", ""))
    source_build = str(source_info.get("CFBundleVersion", ""))
    target_build = str(info.get("CFBundleVersion", ""))
    target_build_prefix = target_build.split(".", 1)[0]
    if target_ver != source_ver or target_build_prefix != source_build:
        results.append(
            CheckResult(
                "WARN",
                "upstream-version-drift",
                f"Codex={source_ver} ({source_build}), DeepCodex={target_ver} ({target_build}); upstream update detected or bundle drifted",
            )
        )
    else:
        results.append(CheckResult("OK", "upstream-version-drift", f"{source_ver} / {source_build}"))


def check_config(results: list[CheckResult], config_text: str) -> None:
    model = top_level_value(config_text, "model")
    provider = top_level_value(config_text, "model_provider")
    context_window = top_level_value(config_text, "model_context_window")
    auto_compact_limit = top_level_value(config_text, "model_auto_compact_token_limit")

    if model not in SUPPORTED_MODELS:
        results.append(CheckResult("FAIL", "current-model", f"unsupported model: {model!r}"))
    else:
        results.append(CheckResult("OK", "current-model", model))

    reasoning = top_level_value(config_text, "model_reasoning_effort")
    if reasoning is None:
        results.append(CheckResult("WARN", "default-reasoning", "model_reasoning_effort not set; UI default applies"))
    elif reasoning in VALID_REASONING:
        results.append(CheckResult("OK", "default-reasoning", f"{reasoning} (UI 所见即所得)"))
    else:
        results.append(CheckResult("FAIL", "default-reasoning", f"invalid effort {reasoning!r}, expected one of {sorted(VALID_REASONING)}"))

    # DeepSeek-only：任何当前模型都必须是 DeepSeek，且只能走本地 provider。
    if model in DEEPSEEK_MODELS and provider != "ccx-deepseek":
        results.append(CheckResult("FAIL", "provider-route", f"DeepSeek model requires ccx-deepseek, got {provider!r}"))
    elif model not in DEEPSEEK_MODELS:
        results.append(CheckResult("FAIL", "provider-route", f"DeepCodex is DeepSeek-only; got non-DeepSeek model {model!r}"))
    else:
        results.append(CheckResult("OK", "provider-route", "DeepSeek -> shim(3100) -> bridge(3000)"))

    if model in LONG_CONTEXT_MODELS:
        if context_window != EXPECTED_CONTEXT_WINDOW or auto_compact_limit != EXPECTED_AUTO_COMPACT_LIMIT:
            results.append(
                CheckResult(
                    "FAIL",
                    "long-context",
                    f"expected context={EXPECTED_CONTEXT_WINDOW}, compact={EXPECTED_AUTO_COMPACT_LIMIT}; got context={context_window!r}, compact={auto_compact_limit!r}",
                )
            )
        else:
            results.append(CheckResult("OK", "long-context", "1M context / 700K compact"))
    elif context_window is not None or auto_compact_limit is not None:
        results.append(CheckResult("WARN", "long-context", f"unexpected long-context keys for {model!r}"))

    required_snippets = [
        EXPECTED_PROVIDER_TABLE,
        EXPECTED_PROVIDER_NAME,
        "codex_hooks = true",
        "goals = true",
        "memories = true",
        "model_catalog_json",
        EXPECTED_FORCED_LOGIN_METHOD,
        EXPECTED_UPDATE_CHECK,
    ]
    for snippet in required_snippets:
        if snippet not in config_text:
            results.append(CheckResult("FAIL", "config-snippet", f"missing: {snippet}"))

    if not any(r.level == "FAIL" and r.title == "config-snippet" for r in results):
        results.append(CheckResult("OK", "config-snippets", "provider, features, marketplaces present"))


def check_auth(results: list[CheckResult], auth: dict) -> None:
    mode = auth.get("auth_mode")
    if mode != EXPECTED_AUTH_MODE:
        results.append(CheckResult("FAIL", "auth-mode", f'expected "{EXPECTED_AUTH_MODE}", got "{mode}"'))
    elif not auth.get("OPENAI_API_KEY"):
        results.append(CheckResult("FAIL", "auth-mode", "apikey mode is missing local provider key"))
    elif "tokens" in auth:
        results.append(CheckResult("FAIL", "auth-mode", "ChatGPT OAuth tokens still present in DeepCodex auth.json"))
    else:
        results.append(CheckResult("OK", "auth-mode", "apikey (no ChatGPT OAuth tokens)"))


def check_deepseek_api_entry(results: list[CheckResult], info: dict, auth: dict) -> None:
    if not CONFIGURE_DEEPSEEK_SCRIPT.exists():
        results.append(CheckResult("FAIL", "deepseek-api-entry", f"missing: {CONFIGURE_DEEPSEEK_SCRIPT}"))
        return
    if not os.access(CONFIGURE_DEEPSEEK_SCRIPT, os.X_OK):
        results.append(CheckResult("FAIL", "deepseek-api-entry", f"not executable: {CONFIGURE_DEEPSEEK_SCRIPT}"))
        return

    missing: list[str] = []
    if not env_secret_present(SECRETS, "CCX_PROXY_ACCESS_KEY"):
        missing.append("secrets.env:CCX_PROXY_ACCESS_KEY")
    if not auth.get("OPENAI_API_KEY"):
        missing.append("auth.json:OPENAI_API_KEY")
    if not info.get("LSEnvironment", {}).get("CCX_PROXY_ACCESS_KEY"):
        missing.append("Info.plist:LSEnvironment:CCX_PROXY_ACCESS_KEY")
    # Bridge reads API key from secrets.env (not ccx config)
    if not env_secret_present(SECRETS, "DEEPSEEK_API_KEY"):
        missing.append("secrets.env:DEEPSEEK_API_KEY")
    if not env_secret_present(SECRETS, "DEEPSEEK_BASE_URL"):
        missing.append("secrets.env:DEEPSEEK_BASE_URL")

    if missing:
        results.append(
            CheckResult(
                "FAIL",
                "deepseek-api-entry",
                "missing API config; run deepcodex-configure-deepseek.py (" + ", ".join(missing) + ")",
            )
        )
        return

    results.append(CheckResult("OK", "deepseek-api-entry", "base URL and API keys configurable via deepcodex-configure-deepseek.py; secrets not printed"))


def check_launchd(results: list[CheckResult], config_text: str) -> None:
    try:
        launchctl = run(["launchctl", "list"])
    except subprocess.CalledProcessError as exc:
        results.append(CheckResult("WARN", "launchctl", exc.output.strip() or "unable to inspect launchctl"))
        return

    if re.search(re.escape(HYBRID_ROUTER_LABEL), launchctl):
        results.append(CheckResult("FAIL", "old-hybrid-router", "legacy hybrid router is still loaded"))
    else:
        results.append(CheckResult("OK", "old-hybrid-router", "not loaded"))

    if re.search(re.escape(CCX_LABEL), launchctl):
        results.append(CheckResult("WARN", "ccx-service", "legacy ccx launchd entry is still loaded; bridge should own port 3000"))
    else:
        results.append(CheckResult("OK", "ccx-service", "legacy ccx launchd entry not loaded"))

    # 剥图中转 (image-strip shim)：DeepSeek 纯文本，shim 把请求里的图片剥掉，防止手滑发图整轮崩。

    # DeepSeek Bridge (replaces ccx)
    if re.search(re.escape(BRIDGE_LABEL), launchctl):
        results.append(CheckResult("OK", "deepseek-bridge", "launchd entry present (Python bridge)"))
    else:
        results.append(CheckResult("WARN", "deepseek-bridge", "launchd entry not found"))
    if tcp_open("127.0.0.1", 3000):
        results.append(CheckResult("OK", "deepseek-bridge-live", "bridge port 127.0.0.1:3000 is reachable"))
    else:
        results.append(CheckResult("FAIL", "deepseek-bridge-live", "bridge port 127.0.0.1:3000 is not reachable"))
    shim_loaded = bool(re.search(re.escape(IMAGE_STRIP_LABEL), launchctl))
    base_url_match = re.search(r'base_url\s*=\s*"([^"]+)"', config_text)
    base_url = base_url_match.group(1) if base_url_match else ""
    via_shim = ":3100" in base_url
    if via_shim and shim_loaded:
        results.append(CheckResult("OK", "image-strip", "剥图中转在线，base_url 经 3100 (发图不会崩)"))
    elif via_shim and not shim_loaded:
        results.append(CheckResult("FAIL", "image-strip", "base_url 指向 3100 但 shim 未运行，DeepSeek 会全部失败"))
    elif not via_shim and shim_loaded:
        results.append(CheckResult("WARN", "image-strip", f"shim 在线但 base_url 未走它 ({base_url})；发图仍会崩"))
    else:
        results.append(CheckResult("WARN", "image-strip", "剥图保护未启用，DeepSeek 下发图会整轮失败；建议走 3100"))

    # 实际探活 shim 端口：launchd 列着不代表进程没卡死。
    if via_shim:
        m = re.search(r"//([^:/]+):(\d+)", base_url)
        host = m.group(1) if m else "127.0.0.1"
        port = int(m.group(2)) if m else 3100
        if tcp_open(host, port):
            results.append(CheckResult("OK", "image-strip-live", f"shim 端口 {host}:{port} 可连通"))
        else:
            results.append(CheckResult("FAIL", "image-strip-live", f"shim 端口 {host}:{port} 连不上（进程可能卡死，DeepSeek 会挂）"))

    # 备份/日志裁剪服务（每日 10:00/22:00）：缺了磁盘/日志没人清理。
    if re.search(re.escape(BACKUP_LABEL), launchctl):
        results.append(CheckResult("OK", "backup-service", "备份+日志裁剪服务已加载"))
    else:
        results.append(CheckResult("WARN", "backup-service", "备份/日志裁剪服务未加载；app-backups 与 logs_2.sqlite 可能无人清理"))

    # 日志保留脚本在位（被 backup.sh 调用裁剪 logs_2.sqlite）。
    if LOG_PRUNE_SCRIPT.exists():
        results.append(CheckResult("OK", "log-prune", "日志保留脚本在位"))
    else:
        results.append(CheckResult("WARN", "log-prune", f"missing: {LOG_PRUNE_SCRIPT}（logs_2.sqlite 会无限增长）"))


MODELS_CACHE = DEEPCODEX_HOME / "models_cache.json"
MODEL_CATALOG = DEEPCODEX_HOME / "model-catalog.json"


def check_frontend_picker(results: list[CheckResult]) -> None:
    """Ensure the packaged model picker cannot surface ChatGPT/GPT entries."""
    if not APP_ASAR.exists():
        results.append(CheckResult("WARN", "frontend-picker", f"missing: {APP_ASAR}"))
        return

    try:
        data = APP_ASAR.read_bytes()
    except OSError as exc:
        results.append(CheckResult("WARN", "frontend-picker", f"read error: {exc}"))
        return

    # Codex 26.513 used a composer bundle with a hard-coded featured model list.
    # Codex 26.519 moved the model-list filtering into model-queries and
    # use-model-settings. Accept either patched shape so controlled upstream
    # rebuilds do not fail only because the bundle split changed.
    match = re.search(rb"var FR = \[([^\]]*)\];", data)
    if match:
        featured = match.group(1).decode("utf-8", errors="replace")
        if "gpt-" in featured.lower() or "chatgpt" in featured.lower():
            results.append(CheckResult("FAIL", "frontend-picker", f"GPT model still present in featured picker list: [{featured}]"))
            return

        deepseek_filter = b"let o = e.filter((e) => LRR(e.model) || LRR(e.displayName))" in data
        if not deepseek_filter:
            results.append(CheckResult("FAIL", "frontend-picker", "missing DeepSeek-only filter for picker otherModels"))
            return

        results.append(CheckResult("OK", "frontend-picker", "UI picker is DeepSeek-only; GPT filtered from featured and otherModels"))
        return

    new_query_filter = (
        b"var p=`deepseek-v4-flash`" in data
        and b"e.model===`deepseek-v4-flash`||e.model===`deepseek-v4-pro`" in data
        and b"displayName:`DeepSeek Flash`" in data
        and b"displayName:`DeepSeek Pro`" in data
    )
    if not new_query_filter:
        results.append(CheckResult("FAIL", "frontend-picker", "DeepSeek-only model query/filter/static fallback patch not found in app.asar"))
        return

    results.append(CheckResult("OK", "frontend-picker", "UI model queries are DeepSeek-only with static Flash/Pro fallback"))


def check_bootstrap_sparkle(results: list[CheckResult]) -> None:
    """Ensure disabled Sparkle is actually skipped at bootstrap, not only in config."""
    if not APP_ASAR.exists():
        results.append(CheckResult("WARN", "bootstrap-sparkle", f"missing: {APP_ASAR}"))
        return

    try:
        data = APP_ASAR.read_bytes()
    except OSError as exc:
        results.append(CheckResult("WARN", "bootstrap-sparkle", f"read error: {exc}"))
        return

    if b"CODEX_SPARKLE_ENABLED!==`false`" not in data or b"initialize();try" not in data:
        results.append(CheckResult("FAIL", "bootstrap-sparkle", "Sparkle initialize is not gated by CODEX_SPARKLE_ENABLED=false"))
        return

    if b"appendSwitch(`password-store`,`basic`)" not in data or b"appendSwitch(`use-mock-keychain`)" not in data:
        results.append(CheckResult("FAIL", "bootstrap-sparkle", "bootstrap must disable Chromium Keychain access for DeepCodex"))
        return
    bootstrap_idx = data.find(b"process.env.LANG='zh_CN.UTF-8'")
    electron_idx = data.find(b"require(`electron`)", bootstrap_idx)
    password_idx = data.find(b"appendSwitch(`password-store`,`basic`)", bootstrap_idx)
    mock_idx = data.find(b"appendSwitch(`use-mock-keychain`)", bootstrap_idx)
    app_session_idx = data.find(b"app-session-", bootstrap_idx)
    if (
        electron_idx < 0
        or password_idx < 0
        or mock_idx < 0
        or app_session_idx < 0
        or not (electron_idx < password_idx < app_session_idx and electron_idx < mock_idx < app_session_idx)
    ):
        results.append(CheckResult("FAIL", "bootstrap-sparkle", "Electron commandLine switches must be set before app-session loads"))
        return

    results.append(CheckResult("OK", "bootstrap-sparkle", "Sparkle skipped and Chromium Keychain disabled for DeepCodex"))


def check_controlled_update_button(results: list[CheckResult]) -> None:
    """Ensure the Codex header update button routes to DeepCodex's manual updater."""
    if not APP_ASAR.exists():
        results.append(CheckResult("WARN", "controlled-update-button", f"missing: {APP_ASAR}"))
        return

    try:
        with APP_ASAR.open("rb") as fh:
            first, header_size, _json_size, json_len = struct.unpack("<IIII", fh.read(16))
            if first != 4:
                results.append(CheckResult("FAIL", "controlled-update-button", "unsupported app.asar header"))
                return
            header = json.loads(fh.read(json_len))
            base_offset = 8 + header_size

            def walk(node: dict, prefix: str = ""):
                for name, entry in node.get("files", {}).items():
                    path = f"{prefix}/{name}" if prefix else name
                    if "files" in entry:
                        yield from walk(entry, path)
                    else:
                        yield path, entry

            main_entry = None
            main_path = None
            for path, entry in walk(header):
                if re.fullmatch(r"\.vite/build/main-[^/]+\.js", path):
                    main_path = path
                    main_entry = entry
                    break
            if main_entry is None or main_path is None:
                results.append(CheckResult("FAIL", "controlled-update-button", "active main bundle not found"))
                return

            fh.seek(base_offset + int(main_entry["offset"]))
            data = fh.read(int(main_entry["size"]))
    except (OSError, struct.error, KeyError, json.JSONDecodeError, ValueError) as exc:
        results.append(CheckResult("WARN", "controlled-update-button", f"read error: {exc}"))
        return

    required = (
        b"DCXUNotifyUpdateState",
        b"DCXUStartControlledUpdate",
        b"DCXURunSync",
        b"--apply-staged",
        b"deepcodex-sync-upstream.py",
        b"CODEX_DEEPCODEX_BUTTON_UPDATE",
    )
    missing = [marker.decode("utf-8") for marker in required if marker not in data]
    if missing:
        results.append(CheckResult("FAIL", "controlled-update-button", f"missing markers: {', '.join(missing)}"))
        return
    if b"this.sparkleManager.installUpdatesIfAvailable()" in data:
        results.append(CheckResult("FAIL", "controlled-update-button", "header update action still routes to Sparkle"))
        return

    results.append(CheckResult("OK", "controlled-update-button", f"{main_path} routes Codex-style header button to manual controlled updater"))


def check_deepseek_config_window(results: list[CheckResult]) -> None:
    """Ensure DeepCodex has a non-React DeepSeek configuration window entry."""
    if not APP_ASAR.exists():
        results.append(CheckResult("WARN", "deepseek-config-window", f"missing: {APP_ASAR}"))
        return

    try:
        data = APP_ASAR.read_bytes()
    except OSError as exc:
        results.append(CheckResult("WARN", "deepseek-config-window", f"read error: {exc}"))
        return

    required = (
        b"DCXCfgOpen",
        b"dcx-deepseek-config-status",
        b"dcx-deepseek-config-save",
        b"dcx-deepseek-config-restart",
        b"deepcodex-configure-deepseek.py",
        "配置 DeepSeek...".encode("utf-8"),
        "DeepSeek base URL".encode("utf-8"),
    )
    missing = [marker.decode("utf-8", errors="replace") for marker in required if marker not in data]
    if missing:
        results.append(CheckResult("FAIL", "deepseek-config-window", f"missing markers: {', '.join(missing)}"))
        return

    results.append(CheckResult("OK", "deepseek-config-window", "first-run and menu DeepSeek base URL/API key window present"))


def check_models_cache(results: list[CheckResult]) -> None:
    """Ensure both model metadata files are DeepSeek-only.

    The Codex desktop UI reads its model picker from models_cache.json, while
    the runtime can also consult model_catalog_json.  Remote refreshes may
    reintroduce OpenAI models into the cache, so doctor restores the DeepSeek
    catalog as the single source of truth.
    """
    if not MODELS_CACHE.exists():
        results.append(CheckResult("WARN", "models-cache", f"missing: {MODELS_CACHE}"))
        return
    if not MODEL_CATALOG.exists():
        results.append(CheckResult("WARN", "models-cache", f"missing: {MODEL_CATALOG}"))
        return

    try:
        cache = json.loads(MODELS_CACHE.read_text())
        catalog = json.loads(MODEL_CATALOG.read_text())
    except (json.JSONDecodeError, KeyError) as exc:
        results.append(CheckResult("WARN", "models-cache", f"parse error: {exc}"))
        return

    catalog_models = catalog.get("models", [])
    catalog_slugs = [m.get("slug") for m in catalog_models]
    expected_slugs = list(SUPPORTED_MODELS)
    if set(catalog_slugs) != SUPPORTED_MODELS:
        results.append(CheckResult("FAIL", "models-cache", f"catalog must contain only DeepSeek models, got {catalog_slugs}"))
        return

    cache_slugs = [m.get("slug") for m in cache.get("models", [])]
    if set(cache_slugs) == SUPPORTED_MODELS and len(cache_slugs) == len(SUPPORTED_MODELS):
        results.append(CheckResult("OK", "models-cache", f"DeepSeek-only cache ({', '.join(cache_slugs)})"))
        return

    cache["models"] = catalog_models
    MODELS_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    results.append(CheckResult("OK", "models-cache", f"rewrote cache to DeepSeek-only ({', '.join(expected_slugs)}); UI restart needed"))


def parse_args() -> ArgumentParser:
    parser = ArgumentParser(description="DeepCodex doctor / repair")
    parser.add_argument("--repair", action="store_true", help="normalize config and restart DeepCodex local services")
    return parser


def main() -> int:
    args = parse_args().parse_args()
    if args.repair:
        print("Repair: starting")
        try:
            actions = repair_environment()
        except Exception as exc:
            print(f"[FAIL] repair: {exc}")
            return 2
        if actions:
            for action in actions:
                print(f"[REPAIR] {action}")
        else:
            print("[REPAIR] no changes needed")
        print("")

    results: list[CheckResult] = []
    check_apps_exist(results)
    if any(r.level == "FAIL" and r.title == "required-path" for r in results):
        for result in results:
            print(f"[{result.level}] {result.title}: {result.detail}")
        return 2

    info = load_plist(DEEPCODEX_APP / "Contents/Info.plist")
    source_info = load_plist(CODEX_APP / "Contents/Info.plist")
    config_text = load_text(CONFIG)
    auth = load_json(AUTH)

    check_info_plist(results, info, source_info)
    check_config(results, config_text)
    check_auth(results, auth)
    check_deepseek_api_entry(results, info, auth)
    check_models_cache(results)
    check_frontend_picker(results)
    check_bootstrap_sparkle(results)
    check_controlled_update_button(results)
    check_deepseek_config_window(results)
    check_launchd(results, config_text)

    worst = 0
    counts = {"OK": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        counts[result.level] += 1
        if result.level == "WARN":
            worst = max(worst, 1)
        elif result.level == "FAIL":
            worst = max(worst, 2)
        print(f"[{result.level}] {result.title}: {result.detail}")

    print(f"\nSummary: OK={counts['OK']} WARN={counts['WARN']} FAIL={counts['FAIL']}")
    if worst == 1:
        print("Action: review warnings, especially upstream-version-drift after Codex updates.")
    elif worst == 2:
        print("Action: repair before using DeepCodex.")
    # 常驻护栏：DeepSeek V4（flash/pro）是纯文本模型，不支持原生图片输入。
    # shim 会尽量把图片转文字，失败时退化成剥图，保证 DeepSeek-only 主链路不崩。
    print("\nNote: DeepCodex is DeepSeek-only. 图片会由 shim 尝试转文字；失败时会被忽略以保护主链路。")
    return worst


if __name__ == "__main__":
    sys.exit(main())
