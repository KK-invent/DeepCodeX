#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


def env_path(name: str, default: str | Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


HOME = env_path("DEEPCODEX_USER_HOME", Path.home())
CODEX_APP = env_path("CODEX_APP", "/Applications/Codex.app")
DEEPCODEX_APP = env_path("DEEPCODEX_APP", "/Applications/Deepcodex.app")
DEEPCODEX_HOME = env_path("DEEPCODEX_HOME", HOME / ".codex-deepseek")
USER_DATA = env_path("DEEPCODEX_USER_DATA", HOME / "Library/Application Support/Deepcodex")
APP_BACKUPS = DEEPCODEX_HOME / "app-backups"
CACHE_BACKUPS = DEEPCODEX_HOME / "cache-backups"
ASSETS = DEEPCODEX_HOME / "assets"
DOCTOR = DEEPCODEX_HOME / "bin" / "deepcodex-doctor.py"
AUTH = DEEPCODEX_HOME / "auth.json"
ASAR_BLOCK_SIZE = 4 * 1024 * 1024
DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
CACHE_DIRS = ("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache")
MAIN_ICON_FILES = ("Deepcodex.icns", "icon.icns", "electron.icns")
HELPER_ICON_GLOB = "Contents/Frameworks/Codex Helper*.app"


@dataclass
class AsarFile:
    path: str
    entry: dict
    old_offset: int | None
    old_size: int


def run(cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if check and completed.returncode != 0:
        joined = " ".join(cmd)
        raise RuntimeError(f"command failed ({completed.returncode}): {joined}\n{completed.stdout}")
    return completed


def log(message: str) -> None:
    print(f"[deepcodex-sync] {message}", flush=True)


def read_plist(app: Path) -> dict:
    with (app / "Contents/Info.plist").open("rb") as fh:
        return plistlib.load(fh)


def write_plist(app: Path, info: dict) -> None:
    with (app / "Contents/Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)


def version(info: dict) -> str:
    return f"{info.get('CFBundleShortVersionString', '?')} ({info.get('CFBundleVersion', '?')})"


def version_key(info: dict) -> tuple[str, str]:
    return (str(info.get("CFBundleShortVersionString", "")), str(info.get("CFBundleVersion", "")))


def read_secret_value(name: str) -> str | None:
    secrets = DEEPCODEX_HOME / "secrets.env"
    if not secrets.exists():
        return None
    for raw in secrets.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == name:
            return value.strip().strip('"').strip("'")
    return None


def deepcodex_environment(existing: dict | None = None) -> dict:
    existing = existing or {}
    ccx_key = existing.get("CCX_PROXY_ACCESS_KEY") or read_secret_value("CCX_PROXY_ACCESS_KEY") or ""
    env = {
        "CODEX_HOME": str(DEEPCODEX_HOME),
        "CODEX_ELECTRON_USER_DATA_PATH": str(USER_DATA),
        "CODEX_DEEPSEEK_APP": "1",
        "CODEX_SPARKLE_ENABLED": "false",
        "LANG": "zh_CN.UTF-8",
        "LANGUAGE": "zh_CN:zh",
        "LC_ALL": "zh_CN.UTF-8",
        "LC_MESSAGES": "zh_CN.UTF-8",
        "MallocNanoZone": "0",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    }
    if ccx_key:
        env["CCX_PROXY_ACCESS_KEY"] = ccx_key
    return env


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_icon_overlay(app: Path) -> None:
    """Install DeepCodex's icon in every bundle location macOS may surface."""
    icon = ASSETS / "Deepcodex.icns"
    if not icon.exists():
        log(f"custom icon asset not found, keeping upstream icons: {icon}")
        return

    info = read_plist(app)
    info["CFBundleIconFile"] = "Deepcodex.icns"
    info.pop("CFBundleIconName", None)
    write_plist(app, info)

    resources = app / "Contents/Resources"
    resources.mkdir(parents=True, exist_ok=True)
    for name in MAIN_ICON_FILES:
        shutil.copy2(icon, resources / name)

    for helper in sorted(app.glob(HELPER_ICON_GLOB)):
        helper_info_path = helper / "Contents/Info.plist"
        if not helper_info_path.exists():
            continue
        helper_resources = helper / "Contents/Resources"
        helper_resources.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, helper_resources / "Deepcodex.icns")
        helper_info = read_plist(helper)
        helper_info["CFBundleIconFile"] = "Deepcodex.icns"
        helper_info.pop("CFBundleIconName", None)
        write_plist(helper, helper_info)


def verify_icon_overlay(app: Path) -> None:
    icon = ASSETS / "Deepcodex.icns"
    if not icon.exists():
        log(f"custom icon verification skipped; asset not packaged: {icon}")
        return
    expected_hash = sha256_file(icon)

    info = read_plist(app)
    if info.get("CFBundleIconFile") != "Deepcodex.icns":
        raise RuntimeError(f"DeepCodex icon plist mismatch: {info.get('CFBundleIconFile')!r}")
    if info.get("CFBundleIconName"):
        raise RuntimeError("DeepCodex CFBundleIconName must be absent")

    resources = app / "Contents/Resources"
    mismatched = []
    for name in MAIN_ICON_FILES:
        path = resources / name
        if not path.exists() or sha256_file(path) != expected_hash:
            mismatched.append(str(path))
    for helper in sorted(app.glob(HELPER_ICON_GLOB)):
        helper_info_path = helper / "Contents/Info.plist"
        if not helper_info_path.exists():
            continue
        helper_info = read_plist(helper)
        helper_icon = helper / "Contents/Resources/Deepcodex.icns"
        if helper_info.get("CFBundleIconFile") != "Deepcodex.icns" or helper_info.get("CFBundleIconName"):
            mismatched.append(str(helper_info_path))
        elif not helper_icon.exists() or sha256_file(helper_icon) != expected_hash:
            mismatched.append(str(helper_icon))
    if mismatched:
        raise RuntimeError("DeepCodex icon overlay mismatch: " + ", ".join(mismatched))


def apply_overlay(app: Path, existing_env: dict | None) -> None:
    info = read_plist(app)
    info["CFBundleDisplayName"] = "DeepCodex"
    info["CFBundleName"] = "Codex"
    info["CFBundleIdentifier"] = "com.openai.codex.deepcodex"
    info["LSEnvironment"] = deepcodex_environment(existing_env)
    write_plist(app, info)

    apply_icon_overlay(app)

    resources = app / "Contents/Resources"
    for name in ("codexTemplate.png", "codexTemplate@2x.png"):
        src = ASSETS / "menu-bar" / name
        if src.exists():
            shutil.copy2(src, resources / name)


def codesign_and_register(app: Path) -> None:
    # Do not preserve the upstream designated requirement after changing the
    # bundle identifier to com.openai.codex.deepcodex. Preserving requirements
    # leaves a stale "identifier com.openai.codex" rule and verification fails.
    run(["codesign", "--force", "--deep", "--sign", "-", str(app)])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    run(["touch", str(app)])
    run([
        "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister",
        "-f",
        str(app),
    ], check=False)


def stop_deepcodex() -> None:
    run(["osascript", "-e", 'tell application "Deepcodex" to quit'], check=False)
    time.sleep(1.0)
    run(["pkill", "-f", str(DEEPCODEX_APP / "Contents/MacOS/Codex")], check=False)
    run(["pkill", "-f", str(DEEPCODEX_APP / "Contents/Frameworks/Codex Helper")], check=False)


def clear_runtime_caches(ts: str) -> Path | None:
    """Move Electron's regenerable web caches away after app.asar changes."""
    moved = False
    backup = CACHE_BACKUPS / f"runtime-cache-before-relaunch-{ts}"
    for name in CACHE_DIRS:
        source = USER_DATA / name
        if not source.exists():
            continue
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(backup / name))
        moved = True
    if not moved:
        return None

    existing = sorted(CACHE_BACKUPS.glob("runtime-cache-before-relaunch-*"), key=lambda p: p.name)
    for old in existing[:-3]:
        shutil.rmtree(old, ignore_errors=True)
    return backup


def read_asar_header(asar: Path) -> tuple[dict, int]:
    with asar.open("rb") as fh:
        first, header_size, _json_size, json_len = struct.unpack("<IIII", fh.read(16))
        if first != 4:
            raise RuntimeError(f"unsupported asar header pickle size: {first}")
        header = json.loads(fh.read(json_len))
    return header, 8 + header_size


def walk_asar_files(node: dict, prefix: str = "") -> Iterator[AsarFile]:
    for name, entry in node.get("files", {}).items():
        path = f"{prefix}/{name}" if prefix else name
        if "files" in entry:
            yield from walk_asar_files(entry, path)
            continue
        old_offset = None if entry.get("unpacked") else int(entry["offset"])
        yield AsarFile(path=path, entry=entry, old_offset=old_offset, old_size=int(entry.get("size", 0)))


def get_asar_entry(header: dict, rel_path: str) -> dict:
    node = header["files"]
    parts = rel_path.split("/")
    for idx, part in enumerate(parts):
        entry = node[part]
        if idx == len(parts) - 1:
            return entry
        node = entry["files"]
    raise KeyError(rel_path)


def read_asar_file(asar: Path, header: dict, base_offset: int, rel_path: str) -> bytes:
    entry = get_asar_entry(header, rel_path)
    if entry.get("unpacked"):
        raise RuntimeError(f"cannot read unpacked file from asar payload: {rel_path}")
    with asar.open("rb") as fh:
        fh.seek(base_offset + int(entry["offset"]))
        return fh.read(int(entry["size"]))


def asar_file_integrity(data: bytes) -> dict:
    blocks = [hashlib.sha256(data[idx : idx + ASAR_BLOCK_SIZE]).hexdigest() for idx in range(0, len(data), ASAR_BLOCK_SIZE)]
    if not blocks:
        blocks = [hashlib.sha256(b"").hexdigest()]
    return {
        "algorithm": "SHA256",
        "hash": hashlib.sha256(data).hexdigest(),
        "blockSize": ASAR_BLOCK_SIZE,
        "blocks": blocks,
    }


def align4(value: int) -> int:
    return (value + 3) & ~3


def write_asar(source: Path, target: Path, patches: dict[str, bytes]) -> str:
    header, base_offset = read_asar_header(source)
    files = list(walk_asar_files(header))
    payloads: list[tuple[AsarFile, bytes | None]] = []
    next_offset = 0
    with source.open("rb") as fh:
        for item in files:
            if item.entry.get("unpacked"):
                payloads.append((item, None))
                continue
            if item.path in patches:
                data = patches[item.path]
                item.entry["size"] = len(data)
                item.entry["integrity"] = asar_file_integrity(data)
            else:
                fh.seek(base_offset + int(item.old_offset))
                data = fh.read(item.old_size)
            item.entry["offset"] = str(next_offset)
            next_offset += len(data)
            payloads.append((item, data))

    header_json = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_len = len(header_json)
    json_size = align4(4 + json_len)
    header_size = 4 + json_size
    padding = b"\0" * (json_size - 4 - json_len)

    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(struct.pack("<IIII", 4, header_size, json_size, json_len))
        fh.write(header_json)
        fh.write(padding)
        for _item, data in payloads:
            if data is not None:
                fh.write(data)
    tmp.replace(target)
    return hashlib.sha256(header_json).hexdigest()


def find_asar_files(header: dict, pattern: str) -> list[str]:
    regex = re.compile(pattern)
    return [item.path for item in walk_asar_files(header) if regex.fullmatch(item.path)]


def find_first_js_containing(asar: Path, header: dict, base_offset: int, pattern: bytes) -> str | None:
    with asar.open("rb") as fh:
        for item in walk_asar_files(header):
            if item.entry.get("unpacked") or not item.path.endswith(".js"):
                continue
            fh.seek(base_offset + int(item.entry["offset"]))
            data = fh.read(int(item.entry["size"]))
            if pattern in data:
                return item.path
    return None


def extract_electron_var(bootstrap: str) -> str:
    match = re.search(r"let\s+([A-Za-z_$][\w$]*)=require\(`electron`\)", bootstrap)
    if not match:
        raise RuntimeError("bootstrap electron require not found")
    return match.group(1)


def patch_bootstrap_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    changed = False

    if "process.env.CODEX_ELECTRON_USER_DATA_PATH" not in text:
        match = re.match(
            r"^const\s+([A-Za-z_$][\w$]*)=require\(`(\./app-session-[^`]+\.js)`\),"
            r"([A-Za-z_$][\w$]*)=require\(`(\./workspace-root-drop-handler-[^`]+\.js)`\);"
            r"let\s+([A-Za-z_$][\w$]*)=require\(`electron`\),"
            r"([A-Za-z_$][\w$]*)=require\(`node:path`\);",
            text,
        )
        if not match:
            raise RuntimeError("bootstrap import prelude shape changed; refusing unsafe patch")
        session_var, session_path, workspace_var, workspace_path, electron_var, path_var = match.groups()
        prefix = (
            "process.env.LANG='zh_CN.UTF-8';"
            "process.env.LC_ALL='zh_CN.UTF-8';"
            "process.env.LC_MESSAGES='zh_CN.UTF-8';"
            "process.env.LANGUAGE='zh-CN';"
            "process.env.CODEX_ELECTRON_USER_DATA_PATH="
            "process.env.CODEX_ELECTRON_USER_DATA_PATH||process.env.DEEPCODEX_USER_DATA||`${process.env.HOME}/Library/Application Support/Deepcodex`;"
        )
        replacement = (
            f"{prefix}let {electron_var}=require(`electron`);"
            f"try{{{electron_var}.app.commandLine.appendSwitch(`lang`,`zh-CN`)}}catch{{}}"
            f"try{{{electron_var}.app.commandLine.appendSwitch(`password-store`,`basic`)}}catch{{}}"
            f"try{{{electron_var}.app.commandLine.appendSwitch(`use-mock-keychain`)}}catch{{}}"
            f"const {session_var}=require(`{session_path}`),{workspace_var}=require(`{workspace_path}`);"
            f"let {path_var}=require(`node:path`);"
        )
        text = replacement + text[match.end() :]
        changed = True

    electron_var = extract_electron_var(text)
    set_name_start = text.find(f"{electron_var}.app.setName(")
    set_path_marker = f"),{electron_var}.app.setPath"
    set_name_end = text.find(set_path_marker, set_name_start)
    if set_name_start < 0 or set_name_end < 0:
        raise RuntimeError("bootstrap app.setName/app.setPath sequence not found")
    replacement = f"{electron_var}.app.setName(`Deepcodex`)"
    text = text[:set_name_start] + replacement + text[set_name_end + 1 :]
    changed = True

    if "CODEX_SPARKLE_ENABLED!==`false`" not in text:
        text, count = re.subn(
            r"if\(await\s+([A-Za-z_$][\w$]*)\.g\(\)\)\{await\s+([A-Za-z_$][\w$]*)\.initialize\(\);try",
            r"if(await \1.g()){if(process.env.CODEX_SPARKLE_ENABLED!==`false`)await \2.initialize();try",
            text,
            count=1,
        )
        if count == 0:
            text, count = re.subn(
                r"await\s+([A-Za-z_$][\w$]*)\.initialize\(\);try\{let\{runMainAppStartup",
                r"if(process.env.CODEX_SPARKLE_ENABLED!==`false`)await \1.initialize();try{let{runMainAppStartup",
                text,
                count=1,
            )
        if count == 0:
            raise RuntimeError("Sparkle initialize call shape changed; refusing unsafe patch")
        changed = True

    verify_bootstrap_patch(text)
    return text.encode("utf-8") if changed else data


def verify_bootstrap_patch(text: str) -> None:
    start = text.find("process.env.LANG='zh_CN.UTF-8'")
    electron_idx = text.find("require(`electron`)", start)
    password_idx = text.find("appendSwitch(`password-store`,`basic`)", start)
    mock_idx = text.find("appendSwitch(`use-mock-keychain`)", start)
    app_session_idx = text.find("app-session-", start)
    if min(start, electron_idx, password_idx, mock_idx, app_session_idx) < 0:
        raise RuntimeError("bootstrap patch verification failed: missing key marker")
    if not (electron_idx < password_idx < app_session_idx and electron_idx < mock_idx < app_session_idx):
        raise RuntimeError("bootstrap patch verification failed: keychain switches load too late")
    if "CODEX_SPARKLE_ENABLED!==`false`" not in text:
        raise RuntimeError("bootstrap patch verification failed: Sparkle is not gated")
    if ".app.setName(`Deepcodex`)" not in text:
        raise RuntimeError("bootstrap patch verification failed: Deepcodex app name not set")


def patch_model_queries_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    changed = False
    if "var p=`gpt-5.5`" in text:
        text = text.replace("var p=`gpt-5.5`", "var p=`deepseek-v4-flash`", 1)
        changed = True
    elif "var p=`deepseek-v4-flash`" not in text:
        raise RuntimeError("model-queries default model marker missing")

    old_available = "_=[],v={availableModels:new Set(_),useHiddenModels:!1,defaultModel:p};"
    new_available = "_=[`deepseek-v4-flash`,`deepseek-v4-pro`],v={availableModels:new Set(_),useHiddenModels:!1,defaultModel:p};"
    if old_available in text:
        text = text.replace(old_available, new_available, 1)
        changed = True
    elif new_available not in text:
        raise RuntimeError("model-queries availableModels marker missing")

    old_filter = "if(d?a.has(e.model):!e.hidden){"
    new_filter = (
        "if((e.model===`deepseek-v4-flash`||e.model===`deepseek-v4-pro`)"
        "&&(d?a.has(e.model):!e.hidden)){"
    )
    if old_filter in text:
        text = text.replace(old_filter, new_filter, 1)
        changed = True
    elif new_filter not in text:
        raise RuntimeError("model-queries DeepSeek filter marker missing")

    old_statement_fallback = (
        "let s=[{model:`deepseek-v4-flash`,displayName:`DeepSeek Flash`,"
        "description:`DeepSeek V4 Flash`,isDefault:n===`deepseek-v4-flash`,hidden:!1,"
        "supportedReasoningEfforts:[{reasoningEffort:`high`,description:`思考`},"
        "{reasoningEffort:`xhigh`,description:`深度思考`}],defaultReasoningEffort:`high`,inputModalities:[`text`]},"
        "{model:`deepseek-v4-pro`,displayName:`DeepSeek Pro`,description:`DeepSeek V4 Pro`,"
        "isDefault:n===`deepseek-v4-pro`,hidden:!1,supportedReasoningEfforts:[{reasoningEffort:`high`,"
        "description:`思考`},{reasoningEffort:`xhigh`,description:`深度思考`}],defaultReasoningEffort:`high`,"
        "inputModalities:[`text`]}];for(let e of s)i.some(t=>t.model===e.model)||i.push(e);"
    )
    fallback = (
        "[{model:`deepseek-v4-flash`,displayName:`DeepSeek Flash`,"
        "description:`DeepSeek V4 Flash`,isDefault:n===`deepseek-v4-flash`,hidden:!1,"
        "supportedReasoningEfforts:[{reasoningEffort:`high`,description:`思考`},"
        "{reasoningEffort:`xhigh`,description:`深度思考`}],defaultReasoningEffort:`high`,inputModalities:[`text`]},"
        "{model:`deepseek-v4-pro`,displayName:`DeepSeek Pro`,description:`DeepSeek V4 Pro`,"
        "isDefault:n===`deepseek-v4-pro`,hidden:!1,supportedReasoningEfforts:[{reasoningEffort:`high`,"
        "description:`思考`},{reasoningEffort:`xhigh`,description:`深度思考`}],defaultReasoningEffort:`high`,"
        "inputModalities:[`text`]}].forEach(e=>i.some(t=>t.model===e.model)||i.push(e)),"
    )
    if old_statement_fallback in text:
        text = text.replace(old_statement_fallback, fallback, 1)
        changed = True
    if "displayName:`DeepSeek Flash`" not in text:
        marker = "o??=i.find(e=>e.model===n)??null,{models:i,defaultModel:o}"
        replacement = fallback + "o??=i.find(e=>e.model===n)??i[0]??null,{models:i,defaultModel:o}"
        if marker not in text:
            raise RuntimeError("model-queries defaultModel fallback marker missing")
        text = text.replace(marker, replacement, 1)
        changed = True
    elif "o??=i.find(e=>e.model===n)??i[0]??null" not in text:
        text = text.replace("o??=i.find(e=>e.model===n)??null", "o??=i.find(e=>e.model===n)??i[0]??null", 1)
        changed = True

    verify_new_frontend_patch(text, None)
    return text.encode("utf-8") if changed else data


def patch_use_model_settings_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    if "`gpt-5.5`" not in text:
        if "`deepseek-v4-flash`" in text:
            verify_new_frontend_patch(None, text)
            return data
        raise RuntimeError("use-model-settings fallback marker missing")
    text = text.replace("`gpt-5.5`", "`deepseek-v4-flash`")
    if "`gpt-5.5`" in text:
        raise RuntimeError("use-model-settings still contains gpt-5.5 after patch")
    return text.encode("utf-8")


def patch_thread_management_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    if "`gpt-5.5`" not in text:
        return data
    return text.replace("`gpt-5.5`", "`deepseek-v4-flash`").encode("utf-8")


def verify_new_frontend_patch(model_queries: str | None, use_model_settings: str | None) -> None:
    if model_queries is not None:
        if "var p=`deepseek-v4-flash`" not in model_queries:
            raise RuntimeError("model-queries default model is not DeepSeek")
        if "e.model===`deepseek-v4-flash`||e.model===`deepseek-v4-pro`" not in model_queries:
            raise RuntimeError("model-queries DeepSeek-only filter missing")
        if "displayName:`DeepSeek Flash`" not in model_queries or "displayName:`DeepSeek Pro`" not in model_queries:
            raise RuntimeError("model-queries static DeepSeek fallback missing")
    if use_model_settings is not None and "`gpt-5.5`" in use_model_settings:
        raise RuntimeError("use-model-settings still contains GPT fallback")


def patch_old_composer_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    if "var FR = [`deepseek-v4-flash`, `deepseek-v4-pro`];" in text and "function LRR(e)" in text:
        return data
    match = re.search(r"var FR = \[[^\]]*\];", text)
    if not match:
        raise RuntimeError("old composer featured model list not found")
    text = text[: match.start()] + "var FR = [`deepseek-v4-flash`, `deepseek-v4-pro`];" + text[match.end() :]
    if "function LRR(e)" not in text:
        raise RuntimeError("old composer shape lacks DeepSeek filter hook; update patcher before applying")
    return text.encode("utf-8")


def extract_require_var(text: str, module_name: str) -> str:
    match = re.search(rf"(?:^|[;,])\s*(?:let\s+|const\s+)?([A-Za-z_$][\w$]*)=require\(`{re.escape(module_name)}`\)", text)
    if not match:
        raise RuntimeError(f"main process require not found: {module_name}")
    return match.group(1)


def controlled_update_helpers(electron_var: str, child_process_var: str) -> str:
    helper = """
function DCXUReadPlist(e,t){try{return __CHILD__.execFileSync(`/usr/libexec/PlistBuddy`,[`-c`,`Print :${t}`,`${e}/Contents/Info.plist`],{encoding:`utf8`,stdio:[`ignore`,`pipe`,`ignore`]}).trim()}catch{return null}}
function DCXUHome(){return process.env.DEEPCODEX_HOME||`${process.env.HOME}/.codex-deepseek`}
function DCXUScript(e){return `${DCXUHome()}/bin/${e}`}
function DCXUUpdateAvailable(){let e=DCXUReadPlist(process.env.CODEX_APP||`/Applications/Codex.app`,`CFBundleVersion`),t=DCXUReadPlist(process.env.DEEPCODEX_APP||`/Applications/Deepcodex.app`,`CFBundleVersion`);return e!=null&&t!=null&&e!==t}
function DCXUNotifyUpdateState(e,t){let n=DCXUUpdateAvailable();e.send(t,{type:`app-update-ready-changed`,isUpdateReady:n}),e.send(t,{type:`app-update-lifecycle-state-changed`,lifecycleState:n?`ready`:`idle`})}
function DCXUSendProgress(e,t,n,r=`installing`){try{e.send(t,{type:`app-update-lifecycle-state-changed`,lifecycleState:r}),e.send(t,{type:`app-update-install-progress-changed`,installProgressPercent:n})}catch{}}
function DCXUProgressForOutput(e){if(e.includes(`copying Codex.app`))return 10;if(e.includes(`patching staged app.asar`))return 25;if(e.includes(`staged app.asar integrity`))return 40;if(e.includes(`codesigning staged bundle`))return 55;if(e.includes(`DeepSeek no-proxy smoke OK`))return 72;if(e.includes(`Stage OK:`))return 82;return null}
function DCXURunSync(e,t,n){return new Promise((r,i)=>{let a=``,o=__CHILD__.spawn(DCXUScript(`deepcodex-sync-upstream.py`),e,{stdio:[`ignore`,`pipe`,`pipe`],env:{...process.env,CODEX_DEEPCODEX_BUTTON_UPDATE:`1`}}),s=e=>{a+=e.toString();let r=DCXUProgressForOutput(a);r!=null&&DCXUSendProgress(t,n,r)};o.stdout.on(`data`,s),o.stderr.on(`data`,s),o.on(`error`,i),o.on(`close`,e=>{e===0?r(a):i(Error(a||`DeepCodex update command failed with exit code ${e}`))})})}
async function DCXUStartControlledUpdate(e,t,r){if(!DCXUUpdateAvailable()){let i={type:`info`,buttons:[`OK`],defaultId:0,noLink:!0,title:`DeepCodex 暂无可用更新`,message:`DeepCodex 暂无可用更新`,detail:`没有检测到比当前 DeepCodex 更新的 Codex.app 版本。`};await(e==null?__ELECTRON__.dialog.showMessageBox(i):__ELECTRON__.dialog.showMessageBox(e,i));return}let i={type:`warning`,buttons:[`更新`,`取消`],defaultId:0,cancelId:1,noLink:!0,title:`现在更新 DeepCodex？`,message:`现在更新 DeepCodex？`,detail:`DeepCodex 将先预构建并验证新版。进度条会显示预检进度；通过后会退出并替换应用，失败会保留当前版本。`};if((e==null?await __ELECTRON__.dialog.showMessageBox(i):await __ELECTRON__.dialog.showMessageBox(e,i)).response!==0)return;try{DCXUSendProgress(t,r,3);let e=await DCXURunSync([`--stage`,`--keep-staged`],t,r),i=/Stage OK: ([^\\n]+)/.exec(e);if(!i)throw Error(`staged bundle path not found in update output`);DCXUSendProgress(t,r,88);__CHILD__.spawn(DCXUScript(`deepcodex-sync-upstream.py`),[`--apply-staged`,i[1]],{detached:!0,stdio:`ignore`,env:{...process.env,CODEX_DEEPCODEX_BUTTON_UPDATE:`1`}}).unref();setTimeout(()=>__ELECTRON__.app.quit(),350)}catch(i){DCXUSendProgress(t,r,null,`ready`);let a=i instanceof Error?i.message:String(i),o={type:`error`,buttons:[`OK`],defaultId:0,noLink:!0,title:`DeepCodex 更新预检失败`,message:`DeepCodex 更新预检失败`,detail:a.slice(0,1800)};await(e==null?__ELECTRON__.dialog.showMessageBox(o):__ELECTRON__.dialog.showMessageBox(e,o))}}
"""
    return helper.replace("__ELECTRON__", electron_var).replace("__CHILD__", child_process_var)


def deepseek_config_helpers(electron_var: str, child_process_var: str) -> str:
    helper = r"""
let DCXCfgWindow=null,DCXCfgIpcRegistered=!1;
function DCXCfgHome(){return process.env.DEEPCODEX_HOME||`${process.env.HOME}/.codex-deepseek`}
function DCXCfgScript(e){return `${DCXCfgHome()}/bin/${e}`}
function DCXCfgRun(e,t=null){return new Promise((n,r)=>{let i=``,a=``,o=__CHILD__.spawn(DCXCfgScript(`deepcodex-configure-deepseek.py`),e,{stdio:[t==null?`ignore`:`pipe`,`pipe`,`pipe`],env:{...process.env,CODEX_DEEPSEEK_CONFIG_WINDOW:`1`}});o.stdout.on(`data`,e=>{i+=e.toString()}),o.stderr.on(`data`,e=>{a+=e.toString()}),o.on(`error`,r),o.on(`close`,e=>{e===0?n(i):r(Error((i+a).trim()||`DeepSeek configuration failed with exit code ${e}`))}),t!=null&&(o.stdin.write(t),o.stdin.end())})}
async function DCXCfgStatus(){try{let e=await DCXCfgRun([`--status-json`]);return JSON.parse(e)}catch(e){return{configured:!1,base_url:`https://api.deepseek.com`,upstream_api_key_present:!1,missing:[e instanceof Error?e.message:String(e)]}}}
function DCXCfgHtml(e){return `<!doctype html><html><head><meta charset="utf-8"><meta name="color-scheme" content="dark light"><title>DeepCodex DeepSeek 配置</title><style>body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#101114;color:#f5f5f5}.wrap{padding:28px}h1{font-size:22px;margin:0 0 8px}.sub{color:#a7a7ad;font-size:13px;line-height:1.5;margin-bottom:22px}.field{margin:0 0 16px}label{display:block;font-size:13px;color:#c8c8cd;margin-bottom:8px}input{box-sizing:border-box;width:100%;height:38px;border:1px solid #3a3b42;border-radius:8px;background:#1b1c22;color:#fff;padding:0 12px;font-size:14px;outline:none}input:focus{border-color:#4b9dff;box-shadow:0 0 0 3px rgba(75,157,255,.18)}.hint{font-size:12px;color:#8f9097;line-height:1.45;margin-top:7px}.row{display:flex;gap:10px;align-items:center;margin-top:22px}button{height:36px;border:0;border-radius:8px;padding:0 14px;font-size:13px;color:#fff;background:#3478f6;cursor:pointer}button.secondary{background:#2b2c32;color:#d6d6db}button:disabled{opacity:.55;cursor:default}.status{min-height:40px;margin-top:18px;font-size:13px;line-height:1.45;color:#c9c9cf;white-space:pre-wrap}.error{color:#ff8a8a}.ok{color:#7ee787}</style></head><body><div class="wrap"><h1>配置 DeepSeek</h1><div class="sub">${e?`首次启动前需要填写 DeepSeek 上游地址和 API key。`:`可以在这里修改 DeepSeek 上游地址或 API key。`}DeepCodex 内部仍会通过本地 shim 与 ccx 转发。</div><form id="form"><div class="field"><label for="baseUrl">DeepSeek base URL</label><input id="baseUrl" autocomplete="off" spellcheck="false" placeholder="https://api.deepseek.com"><div class="hint">填写 OpenAI-compatible 上游地址，不要填写 127.0.0.1:3100。</div></div><div class="field"><label for="apiKey">DeepSeek API key</label><input id="apiKey" type="password" autocomplete="off" placeholder="留空则保留已配置的 key"><div id="keyHint" class="hint"></div></div><div class="row"><button id="save" type="submit">保存并重启</button><button id="close" class="secondary" type="button">稍后</button></div><div id="status" class="status">正在读取配置...</div></form></div><script>const{ipcRenderer}=require('electron'),baseUrl=document.getElementById('baseUrl'),apiKey=document.getElementById('apiKey'),keyHint=document.getElementById('keyHint'),statusEl=document.getElementById('status'),saveBtn=document.getElementById('save'),closeBtn=document.getElementById('close'),form=document.getElementById('form');function setStatus(t,c){statusEl.className='status '+(c||'');statusEl.textContent=t}ipcRenderer.invoke('dcx-deepseek-config-status').then(s=>{baseUrl.value=s.base_url||'https://api.deepseek.com';keyHint.textContent=s.upstream_api_key_present?'已配置 API key；留空会保留现有 key。':'未检测到 API key，首次配置必须填写。';setStatus(s.configured?'当前配置完整。':'配置不完整：'+(s.missing||[]).join(', '),s.configured?'ok':'')}).catch(e=>setStatus(String(e),'error'));form.addEventListener('submit',async e=>{e.preventDefault();saveBtn.disabled=true;setStatus('正在保存配置...');try{let r=await ipcRenderer.invoke('dcx-deepseek-config-save',{baseUrl:baseUrl.value,apiKey:apiKey.value});if(!r||!r.ok)throw Error(r&&r.error||'保存失败');setStatus('配置已保存，正在重启 DeepCodex...', 'ok');setTimeout(()=>ipcRenderer.invoke('dcx-deepseek-config-restart'),500)}catch(e){saveBtn.disabled=false;setStatus(String(e&&e.message||e),'error')}});closeBtn.addEventListener('click',()=>window.close());</script></body></html>`}
function DCXCfgRegisterIpc(){if(DCXCfgIpcRegistered)return;DCXCfgIpcRegistered=!0;__ELECTRON__.ipcMain.handle(`dcx-deepseek-config-status`,async()=>DCXCfgStatus()),__ELECTRON__.ipcMain.handle(`dcx-deepseek-config-save`,async(e,t)=>{let n=String(t&&t.baseUrl||``).trim(),r=String(t&&t.apiKey||``).trim();if(!n)throw Error(`DeepSeek base URL 不能为空`);let i=[`--base-url`,n,`--restart-services`,`--no-confirm`],a=null;return r?(i.push(`--key-stdin`),a=r):i.push(`--keep-existing-key`),await DCXCfgRun(i,a),{ok:!0}}),__ELECTRON__.ipcMain.handle(`dcx-deepseek-config-restart`,async()=>{__ELECTRON__.app.relaunch(),__ELECTRON__.app.exit(0)})}
function DCXCfgOpen(e=!1){DCXCfgRegisterIpc();if(DCXCfgWindow&&!DCXCfgWindow.isDestroyed()){DCXCfgWindow.focus();return}DCXCfgWindow=new __ELECTRON__.BrowserWindow({width:540,height:500,title:`DeepCodex DeepSeek 配置`,resizable:!1,minimizable:!1,maximizable:!1,fullscreenable:!1,webPreferences:{nodeIntegration:!0,contextIsolation:!1}}),DCXCfgWindow.on(`closed`,()=>{DCXCfgWindow=null}),DCXCfgWindow.loadURL(`data:text/html;base64,`+Buffer.from(DCXCfgHtml(e),`utf8`).toString(`base64`))}
function DCXCfgMenuPresent(e){return !!(e&&e.items&&e.items.some(e=>e.submenu&&e.submenu.items&&e.submenu.items.some(e=>e.label===`配置 DeepSeek...`)))}
function DCXCfgInstallMenu(){try{let e=__ELECTRON__.Menu.getApplicationMenu();if(DCXCfgMenuPresent(e))return!0;let t=new __ELECTRON__.MenuItem({label:`配置 DeepSeek...`,click(){DCXCfgOpen(!1)}});if(e){let n=e.items.find(e=>e.submenu&&(e.label===`Codex`||e.label===`Deepcodex`||e.label===__ELECTRON__.app.name))||e.items[0],r=e.items.find(e=>e.submenu&&e.label===`Help`);if(n&&n.submenu)n.submenu.append(new __ELECTRON__.MenuItem({type:`separator`})),n.submenu.append(t);else if(r&&r.submenu)r.submenu.append(new __ELECTRON__.MenuItem({type:`separator`})),r.submenu.append(t);else e.append(new __ELECTRON__.MenuItem({label:`DeepCodex`,submenu:[{label:`配置 DeepSeek...`,click(){DCXCfgOpen(!1)}}]}));__ELECTRON__.Menu.setApplicationMenu(e);return DCXCfgMenuPresent(__ELECTRON__.Menu.getApplicationMenu())}let n=new __ELECTRON__.Menu;return n.append(new __ELECTRON__.MenuItem({label:`DeepCodex`,submenu:[{label:`配置 DeepSeek...`,click(){DCXCfgOpen(!1)}}]})),__ELECTRON__.Menu.setApplicationMenu(n),!0}catch(e){return console.error(`[DeepCodex] failed to install DeepSeek config menu`,e),!1}}
function DCXCfgEnsureMenu(){let e=0,t=setInterval(()=>{DCXCfgInstallMenu(),++e>=20&&clearInterval(t)},1000)}
function DCXCfgBootstrap(){DCXCfgRegisterIpc(),__ELECTRON__.app.whenReady().then(()=>setTimeout(async()=>{DCXCfgEnsureMenu();let e=await DCXCfgStatus();e.configured||DCXCfgOpen(!0)},1200))}
DCXCfgBootstrap();
"""
    return helper.replace("__ELECTRON__", electron_var).replace("__CHILD__", child_process_var)


def patch_main_js(data: bytes) -> bytes:
    text = data.decode("utf-8")
    electron_var = extract_require_var(text, "electron")
    child_process_var = extract_require_var(text, "node:child_process")
    changed = False

    helper_text = controlled_update_helpers(electron_var, child_process_var) + deepseek_config_helpers(electron_var, child_process_var)
    helper_start = text.find("function DCXUReadPlist(")
    if helper_start >= 0:
        next_function = re.search(r"\nfunction (?!DCXU|DCXCfg)", text[helper_start + 1 :])
        if not next_function:
            raise RuntimeError("main process controlled update helper boundary not found")
        helper_end = helper_start + 1 + next_function.start() + 1
        if text[helper_start:helper_end] != helper_text:
            text = text[:helper_start] + helper_text + text[helper_end:]
            changed = True
    else:
        insert_at = text.find("function ")
        if insert_at < 0:
            raise RuntimeError("main process function insertion point not found")
        text = text[:insert_at] + helper_text + text[insert_at:]
        changed = True

    ready_pattern = re.compile(
        r"r\.send\(([A-Za-z_$][\w$]*),\{type:`app-update-ready-changed`,isUpdateReady:this\.sparkleManager\.getIsUpdateReady\(\)\}\),"
        r"r\.send\(\1,\{type:`app-update-lifecycle-state-changed`,lifecycleState:this\.sparkleManager\.getUpdateLifecycleState\(\)\}\),"
    )
    ready_match = ready_pattern.search(text)
    if ready_match:
        update_channel = ready_match.group(1)
        text = ready_pattern.sub(f"DCXUNotifyUpdateState(r,{update_channel}),", text, count=1)
        changed = True
    else:
        existing = re.search(r"DCXUNotifyUpdateState\(r,([A-Za-z_$][\w$]*)\)", text)
        if not existing:
            raise RuntimeError("main process app-update lifecycle send shape changed")
        update_channel = existing.group(1)

    handler_pattern = re.compile(
        r"case`check-app-update`:this\.sparkleManager\.checkForUpdates\(\);break;"
        r"case`install-app-update`:.*?this\.sparkleManager\.installUpdatesIfAvailable\(\);break;"
    )
    if handler_pattern.search(text):
        replacement = (
            f"case`check-app-update`:DCXUNotifyUpdateState(r,{update_channel});break;"
            f"case`install-app-update`:{{let e={electron_var}.BrowserWindow.fromWebContents(r)??this.windowManager.getPrimaryWindow();"
            f"await DCXUStartControlledUpdate(e,r,{update_channel});break}}"
        )
        text = handler_pattern.sub(replacement, text, count=1)
        changed = True
    else:
        text, count = re.subn(
            r"DCXUStartControlledUpdate\(e\);break",
            f"DCXUStartControlledUpdate(e,r,{update_channel});break",
            text,
            count=1,
        )
        if count:
            changed = True
    if "case`check-app-update`:DCXUNotifyUpdateState" not in text or "DCXUStartControlledUpdate(e,r," not in text:
        raise RuntimeError("main process app-update handler shape changed")

    if "this.sparkleManager.installUpdatesIfAvailable()" in text:
        raise RuntimeError("main process install-app-update still routes to Sparkle")
    if "deepcodex-sync-upstream.py" not in text or "DCXUStartControlledUpdate" not in text or "DCXURunSync" not in text:
        raise RuntimeError("main process controlled update patch verification failed")
    if "DCXCfgOpen" not in text or "dcx-deepseek-config-save" not in text or "deepcodex-configure-deepseek.py" not in text:
        raise RuntimeError("main process DeepSeek config window patch verification failed")

    menu_old = "Ge=[_e,{type:`separator`},b];"
    menu_new = "Ge=[_e,{type:`separator`},b,{type:`separator`},{label:`配置 DeepSeek...`,click:()=>DCXCfgOpen(!1)}];"
    if menu_old in text:
        text = text.replace(menu_old, menu_new, 1)
        changed = True
    elif menu_new not in text:
        raise RuntimeError("main process application menu template shape changed")

    return text.encode("utf-8") if changed else data


def validate_js_syntax(patches: dict[str, bytes]) -> None:
    with tempfile.TemporaryDirectory(prefix="deepcodex-js-check-") as tmp_dir:
        tmp = Path(tmp_dir)
        for rel_path, data in patches.items():
            if not rel_path.endswith(".js"):
                continue
            js = tmp / f"{rel_path.replace('/', '__')}.mjs"
            js.write_bytes(data)
            run(["node", "--check", str(js)])


def patch_app_asar(app: Path) -> str:
    asar = app / "Contents/Resources/app.asar"
    header, base_offset = read_asar_header(asar)
    patches: dict[str, bytes] = {}

    bootstrap_path = ".vite/build/bootstrap.js"
    patches[bootstrap_path] = patch_bootstrap_js(read_asar_file(asar, header, base_offset, bootstrap_path))

    main_paths = find_asar_files(header, r"\.vite/build/main-[^/]+\.js")
    if not main_paths:
        raise RuntimeError("main process bundle not found")
    main_path = main_paths[0]
    patches[main_path] = patch_main_js(read_asar_file(asar, header, base_offset, main_path))

    model_query_paths = find_asar_files(header, r"webview/assets/model-queries-[^/]+\.js")
    use_model_paths = find_asar_files(header, r"webview/assets/use-model-settings-[^/]+\.js")
    thread_tool_paths = find_asar_files(header, r"webview/assets/thread-management-dynamic-tools-[^/]+\.js")

    if model_query_paths and use_model_paths:
        model_path = model_query_paths[0]
        use_model_path = use_model_paths[0]
        patches[model_path] = patch_model_queries_js(read_asar_file(asar, header, base_offset, model_path))
        patches[use_model_path] = patch_use_model_settings_js(read_asar_file(asar, header, base_offset, use_model_path))
        for path in thread_tool_paths:
            patched = patch_thread_management_js(read_asar_file(asar, header, base_offset, path))
            if patched != read_asar_file(asar, header, base_offset, path):
                patches[path] = patched
    else:
        composer_path = find_first_js_containing(asar, header, base_offset, b"var FR = ")
        if composer_path is None:
            raise RuntimeError("no known model picker bundle found")
        patches[composer_path] = patch_old_composer_js(read_asar_file(asar, header, base_offset, composer_path))

    validate_js_syntax(patches)
    patched = asar.with_suffix(".asar.patched")
    new_hash = write_asar(asar, patched, patches)
    patched.replace(asar)
    write_asar_integrity(app, new_hash)
    verify_asar_patch(app)
    return new_hash


def write_asar_integrity(app: Path, header_hash: str) -> None:
    info = read_plist(app)
    integrity = info.setdefault("ElectronAsarIntegrity", {})
    app_asar = integrity.setdefault("Resources/app.asar", {})
    app_asar["algorithm"] = "SHA256"
    app_asar["hash"] = header_hash
    write_plist(app, info)


def read_asar_json_hash(app: Path) -> str:
    asar = app / "Contents/Resources/app.asar"
    with asar.open("rb") as fh:
        _first, _header_size, _json_size, json_len = struct.unpack("<IIII", fh.read(16))
        return hashlib.sha256(fh.read(json_len)).hexdigest()


def verify_asar_patch(app: Path) -> None:
    asar = app / "Contents/Resources/app.asar"
    data = asar.read_bytes()
    if b"CODEX_SPARKLE_ENABLED!==`false`" not in data:
        raise RuntimeError("asar verification failed: Sparkle gate missing")
    if b"appendSwitch(`password-store`,`basic`)" not in data or b"appendSwitch(`use-mock-keychain`)" not in data:
        raise RuntimeError("asar verification failed: keychain switches missing")
    if b"DCXUNotifyUpdateState" not in data or b"DCXURunSync" not in data or b"deepcodex-sync-upstream.py" not in data:
        raise RuntimeError("asar verification failed: controlled update button patch missing")
    if b"DCXCfgOpen" not in data or b"dcx-deepseek-config-save" not in data or b"DeepSeek base URL" not in data or "配置 DeepSeek...".encode("utf-8") not in data:
        raise RuntimeError("asar verification failed: DeepSeek config window patch missing")
    old_picker_ok = b"var FR = [`deepseek-v4-flash`, `deepseek-v4-pro`]" in data and b"function LRR(e)" in data
    new_picker_ok = (
        b"var p=`deepseek-v4-flash`" in data
        and b"e.model===`deepseek-v4-flash`||e.model===`deepseek-v4-pro`" in data
        and b"displayName:`DeepSeek Flash`" in data
        and b"displayName:`DeepSeek Pro`" in data
    )
    if not (old_picker_ok or new_picker_ok):
        raise RuntimeError("asar verification failed: DeepSeek-only picker patch missing")
    info_hash = read_plist(app).get("ElectronAsarIntegrity", {}).get("Resources/app.asar", {}).get("hash")
    actual_hash = read_asar_json_hash(app)
    if info_hash != actual_hash:
        raise RuntimeError(f"asar integrity mismatch: plist={info_hash}, actual={actual_hash}")


def verify_staged_app(app: Path) -> None:
    info = read_plist(app)
    env = info.get("LSEnvironment", {})
    checks = {
        "CFBundleDisplayName": info.get("CFBundleDisplayName") == "DeepCodex",
        "CFBundleName": info.get("CFBundleName") == "Codex",
        "CFBundleIdentifier": info.get("CFBundleIdentifier") == "com.openai.codex.deepcodex",
        "CODEX_HOME": env.get("CODEX_HOME") == str(DEEPCODEX_HOME),
        "CODEX_SPARKLE_ENABLED": env.get("CODEX_SPARKLE_ENABLED") == "false",
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"staged app overlay verification failed: {', '.join(failed)}")
    verify_icon_overlay(app)
    verify_asar_patch(app)


def wait_tcp(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def smoke_deepseek_route(timeout: int = 25) -> None:
    if not wait_tcp("127.0.0.1", 3100, 8):
        raise RuntimeError("DeepSeek shim port 3100 is not reachable")
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    key = auth.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("missing OPENAI_API_KEY in DeepCodex auth.json")
    body = json.dumps({
        "model": "deepseek-v4-flash",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "ping"}]}],
        "reasoning": {"effort": "high"},
        "store": False,
    }).encode("utf-8")
    env = os.environ.copy()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(name, None)
    env["NO_PROXY"] = "127.0.0.1,localhost,::1"
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(env)
        request = urllib.request.Request(
            "http://127.0.0.1:3100/v1/responses",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        start = time.time()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        elapsed = time.time() - start
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    if payload.get("model") != "deepseek-v4-flash" or payload.get("status") != "completed":
        raise RuntimeError(f"DeepSeek smoke returned unexpected payload: model={payload.get('model')} status={payload.get('status')}")
    log(f"DeepSeek no-proxy smoke OK in {elapsed:.2f}s")


def run_doctor_repair_and_verify() -> None:
    repair = run([str(DOCTOR), "--repair"], check=False)
    print(repair.stdout, end="")
    verify = run([str(DOCTOR)], check=False)
    print(verify.stdout, end="")
    if "FAIL=0" not in verify.stdout:
        raise RuntimeError("doctor verification failed after apply")


def process_exists(pattern: str) -> bool:
    return run(["pgrep", "-f", pattern], check=False).returncode == 0


def probe_frontend_ready() -> tuple[bool, str]:
    deepcodex_app_path = str(DEEPCODEX_APP).replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "System Events"\n'
        '  set targetProcess to missing value\n'
        '  repeat with p in every process whose name is "Codex"\n'
        '    try\n'
        f'      if POSIX path of (application file of p as alias) is "{deepcodex_app_path}" then\n'
        '        set targetProcess to p\n'
        '        exit repeat\n'
        '      end if\n'
        '    end try\n'
        '  end repeat\n'
        '  if targetProcess is missing value then error "DeepCodex process not found"\n'
        '  get entire contents of window 1 of targetProcess\n'
        'end tell'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return False, "System Events frontend probe timed out"

    output = result.stdout or ""
    if result.returncode != 0:
        lower = output.lower()
        permission_markers = ("not authorized", "not allowed", "未被授权", "不允许", "assistive access")
        if any(marker in lower for marker in permission_markers):
            return True, f"frontend probe skipped: {output.strip()}"
        return False, output.strip() or f"System Events returned {result.returncode}"

    has_model_button = "DeepSeek Flash" in output or "DeepSeek Pro" in output
    if has_model_button:
        return True, "DeepCodex window and DeepSeek model button are visible"
    return False, "window exists but DeepSeek model UI is not visible yet"


def wait_frontend_ready(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        ok, detail = probe_frontend_ready()
        last = detail
        if ok:
            log(f"frontend check OK: {detail}")
            return
        time.sleep(1)
    raise RuntimeError(f"frontend check failed: {last}")


def launch_and_wait() -> None:
    run(["open", "-a", str(DEEPCODEX_APP)])
    deadline = time.time() + 25
    while time.time() < deadline:
        main_ok = process_exists(str(DEEPCODEX_APP / "Contents/MacOS/Codex"))
        renderer_ok = process_exists(re.escape(str(DEEPCODEX_APP / "Contents/Frameworks/Codex Helper (Renderer).app")))
        server_ok = process_exists(re.escape(str(DEEPCODEX_APP / "Contents/Resources")) + r"/codex(\.real)? app-server")
        if main_ok and renderer_ok and server_ok:
            log("launch check OK: main, renderer, and app-server are running")
            wait_frontend_ready()
            return
        time.sleep(1)
    raise RuntimeError("launch check failed: DeepCodex did not reach main+renderer+app-server state")


def backup_current(ts: str) -> Path | None:
    if not DEEPCODEX_APP.exists():
        return None
    APP_BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = APP_BACKUPS / f"Deepcodex.app.before-controlled-upgrade-{ts}"
    run(["ditto", "--noqtn", str(DEEPCODEX_APP), str(backup)])
    return backup


def rollback_from_backup(backup: Path | None) -> None:
    if backup is None or not backup.exists():
        log("rollback skipped: no previous DeepCodex backup")
        return
    log(f"rolling back from {backup}")
    stop_deepcodex()
    if DEEPCODEX_APP.exists():
        shutil.rmtree(DEEPCODEX_APP)
    run(["ditto", "--noqtn", str(backup), str(DEEPCODEX_APP)])
    codesign_and_register(DEEPCODEX_APP)


def stage_upstream(ts: str) -> tuple[Path, str]:
    if not CODEX_APP.exists():
        raise SystemExit(f"missing upstream app: {CODEX_APP}")
    if not DEEPCODEX_HOME.exists():
        raise SystemExit(f"missing DeepCodex home: {DEEPCODEX_HOME}")

    existing_env = {}
    if DEEPCODEX_APP.exists():
        existing_env = read_plist(DEEPCODEX_APP).get("LSEnvironment", {})

    tmp = DEEPCODEX_APP.with_name(f"{DEEPCODEX_APP.name}.tmp-controlled-upgrade-{ts}")
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        log("copying Codex.app to staged DeepCodex bundle")
        run(["ditto", "--noqtn", str(CODEX_APP), str(tmp)])
        apply_overlay(tmp, existing_env)
        log("patching staged app.asar")
        asar_hash = patch_app_asar(tmp)
        log(f"staged app.asar integrity {asar_hash}")
        log("codesigning staged bundle")
        codesign_and_register(tmp)
        verify_staged_app(tmp)
        smoke_deepseek_route()
        return tmp, asar_hash
    except Exception:
        if tmp.exists():
            shutil.rmtree(tmp)
        raise


def apply_staged_app(staged: Path, ts: str, *, launch_check: bool) -> Path | None:
    backup = backup_current(ts)
    try:
        log("staged checks passed; replacing live DeepCodex")
        stop_deepcodex()
        if DEEPCODEX_APP.exists():
            shutil.rmtree(DEEPCODEX_APP)
        staged.rename(DEEPCODEX_APP)
        codesign_and_register(DEEPCODEX_APP)
        cache_backup = clear_runtime_caches(ts)
        if cache_backup is not None:
            log(f"moved regenerable Electron caches to {cache_backup}")
        run_doctor_repair_and_verify()
        smoke_deepseek_route()
        if launch_check:
            launch_and_wait()
        return backup
    except Exception:
        rollback_from_backup(backup)
        raise


def print_status() -> tuple[dict, dict]:
    source = read_plist(CODEX_APP) if CODEX_APP.exists() else {}
    target = read_plist(DEEPCODEX_APP) if DEEPCODEX_APP.exists() else {}
    print(f"Codex.app:     {version(source) if source else 'missing'}")
    print(f"Deepcodex.app: {version(target) if target else 'missing'}")
    print("Policy: manual-only; DeepCodex never self-updates via Sparkle.")
    print(
        "Gate: stage -> patch app.asar -> ESM syntax -> integrity -> codesign -> "
        "DeepSeek smoke -> doctor -> cache refresh -> process+frontend launch check."
    )
    if source and target and version_key(source) == version_key(target):
        print("Status: versions match.")
    elif source and target:
        print("Status: Codex.app version differs from DeepCodex; run --stage to preflight or --apply to update.")
    return source, target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually rebuild DeepCodex from the currently installed Codex.app with safety gates.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="show version drift and policy; no writes")
    mode.add_argument("--stage", action="store_true", help="build, patch, sign, and smoke-test a temporary bundle; do not replace live DeepCodex")
    mode.add_argument("--apply", action="store_true", help="explicitly replace live DeepCodex after all staged checks pass")
    mode.add_argument("--apply-staged", metavar="PATH", help="replace live DeepCodex with an already staged and verified bundle")
    parser.add_argument("--force", action="store_true", help="stage/apply even when Codex.app and DeepCodex.app versions already match")
    parser.add_argument("--keep-staged", action="store_true", help="keep the temporary staged app after --stage")
    parser.add_argument("--skip-launch-check", action="store_true", help="after --apply, skip opening DeepCodex and waiting for renderer/app-server")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source, target = print_status()
    if args.dry_run:
        return 0
    if not source:
        raise SystemExit(
            "\n".join(
                [
                    f"missing upstream app: {CODEX_APP}",
                    "DeepCodeX source mode rebuilds from a local Codex.app and cannot create a full app without it.",
                    "普通用户：请下载维护者提供的 DeepCodeX 成品包，然后首次启动时填写 DeepSeek base URL 和 API key。",
                    "维护者：请先安装官方 Codex desktop app，或在合规允许的私有环境中准备成品包。",
                ]
            )
        )
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.apply_staged:
        staged = Path(args.apply_staged)
        if not staged.exists():
            raise SystemExit(f"missing staged app: {staged}")
        try:
            verify_staged_app(staged)
            backup = apply_staged_app(staged, ts, launch_check=not args.skip_launch_check)
            print(f"Apply OK: DeepCodex rebuilt from staged app. Backup: {backup}")
            return 0
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 2
    if target and version_key(source) == version_key(target) and not args.force:
        print("No update staged because versions already match. Use --force to rebuild anyway.")
        return 0

    staged: Path | None = None
    try:
        staged, asar_hash = stage_upstream(ts)
        if args.stage:
            print(f"Stage OK: {staged}")
            print(f"Staged app.asar integrity: {asar_hash}")
            if not args.keep_staged:
                shutil.rmtree(staged)
                print("Staged bundle removed; live DeepCodex was not changed.")
            else:
                print("Staged bundle kept for inspection; live DeepCodex was not changed.")
            return 0

        backup = apply_staged_app(staged, ts, launch_check=not args.skip_launch_check)
        staged = None
        print(f"Apply OK: DeepCodex rebuilt from Codex.app. Backup: {backup}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    finally:
        if staged is not None and staged.exists() and not args.keep_staged:
            shutil.rmtree(staged)


if __name__ == "__main__":
    sys.exit(main())
