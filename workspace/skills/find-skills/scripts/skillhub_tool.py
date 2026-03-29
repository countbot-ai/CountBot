#!/usr/bin/env python3
"""技能搜索、安装与管理工具。"""

import argparse
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


LOCKFILE_NAME = ".skills_store_lock.json"
SKILLS_CONFIG_NAME = ".skills_config.json"
SKILLHUB_INSTALL_KIT_URL = (
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/latest.tar.gz"
)
# Direct search/install is adapted from the public SkillHub Tencent site endpoints.
SKILLHUB_SITE_URL = "https://skillhub.tencent.com/"
SKILLHUB_INDEX_URL = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json"
SKILLHUB_SEARCH_URL = "https://lightmake.site/api/v1/search"
SKILLHUB_PRIMARY_DOWNLOAD_URL_TEMPLATE = "https://lightmake.site/api/v1/download?slug={slug}"
SKILLHUB_FALLBACK_DOWNLOAD_URL_TEMPLATE = (
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills/{slug}.zip"
)
SKILLHUB_SOURCE_LABEL = "skillhub.tencent.com"
SKILLHUB_USER_AGENT = "countbot-find-skills/1.0"
VALID_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]
WORKSPACE_ROOT = REPO_ROOT / "workspace"
DEFAULT_INSTALL_ROOT = WORKSPACE_ROOT / "skills"
LOCKFILE_PATH = DEFAULT_INSTALL_ROOT / LOCKFILE_NAME
SKILLS_CONFIG_PATH = WORKSPACE_ROOT / SKILLS_CONFIG_NAME


def default_skillhub_bin_dir() -> Path:
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA", "").strip()
        if localappdata:
            return Path(localappdata).expanduser().resolve() / "skillhub" / "bin"
        return (Path.home() / "AppData" / "Local" / "skillhub" / "bin").resolve()
    return (Path.home() / ".local" / "bin").resolve()


def default_openclaw_home() -> Path:
    userprofile = os.environ.get("USERPROFILE", "").strip()
    if os.name == "nt" and userprofile:
        return (Path(userprofile).expanduser().resolve() / ".openclaw").resolve()
    return (Path.home() / ".openclaw").resolve()


SKILLHUB_BIN_DIR = default_skillhub_bin_dir()
SKILLHUB_BIN_NAME = "skillhub.cmd" if os.name == "nt" else "skillhub"
LEGACY_SKILLHUB_BIN_NAME = "oc-skills.cmd" if os.name == "nt" else "oc-skills"
SKILLHUB_BIN_PATH = SKILLHUB_BIN_DIR / SKILLHUB_BIN_NAME


def normalize_limit(value: int) -> int:
    return max(1, min(int(value), 50))


def normalize_slug(value: str) -> str:
    slug = value.strip()
    if not slug:
        raise RuntimeError("slug is required")
    if not VALID_SLUG_RE.fullmatch(slug):
        raise RuntimeError(f"invalid slug: {slug}")
    return slug


def clone_json(value: Any) -> Any:
    return copy.deepcopy(value)


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return clone_json(default)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json file: {path}") from exc


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_lockfile() -> Dict[str, Any]:
    payload = read_json_file(LOCKFILE_PATH, {"skills": {}})
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid lockfile: {LOCKFILE_PATH}")

    skills = payload.get("skills")
    if not isinstance(skills, dict):
        payload["skills"] = {}
    return payload


def save_lockfile(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("lockfile payload must be an object")
    skills = payload.get("skills")
    if not isinstance(skills, dict):
        payload["skills"] = {}
    write_json_file(LOCKFILE_PATH, payload)


def read_skills_config() -> Dict[str, Any]:
    payload = read_json_file(SKILLS_CONFIG_PATH, {})
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid skills config: {SKILLS_CONFIG_PATH}")
    return payload


def save_skills_config(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("skills config payload must be an object")
    cleaned = clone_json(payload)
    if not cleaned:
        if SKILLS_CONFIG_PATH.exists():
            SKILLS_CONFIG_PATH.unlink()
        return
    write_json_file(SKILLS_CONFIG_PATH, cleaned)


def load_disabled_skills() -> Set[str]:
    config = read_skills_config()
    raw = config.get("disabled_skills", [])
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def save_disabled_skills(disabled_skills: Set[str]) -> None:
    config = read_skills_config()
    disabled_list = sorted(disabled_skills)
    if disabled_list:
        config["disabled_skills"] = disabled_list
    else:
        config.pop("disabled_skills", None)
    save_skills_config(config)


def workspace_skill_dir(slug: str) -> Path:
    return DEFAULT_INSTALL_ROOT / slug


def workspace_skill_file(slug: str) -> Path:
    return workspace_skill_dir(slug) / "SKILL.md"


def workspace_skill_exists(slug: str) -> bool:
    return workspace_skill_file(slug).is_file()


def require_workspace_skill(slug: str) -> Path:
    skill_file = workspace_skill_file(slug)
    if not skill_file.is_file():
        raise RuntimeError(f"skill not found: {slug}")
    return skill_file


def http_request(url: str, accept: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": SKILLHUB_USER_AGENT,
            "Accept": accept,
            "Referer": SKILLHUB_SITE_URL,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"http error {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {url}: {exc.reason}") from exc


def read_json_url(url: str, timeout: int = 20) -> Any:
    payload = http_request(url, "application/json", timeout=timeout)
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json response: {url}") from exc


def normalize_remote_skill(item: Dict[str, Any]) -> Dict[str, Any]:
    slug = str(item.get("slug", "")).strip()
    if not slug:
        return {}
    result: Dict[str, Any] = {
        "slug": slug,
        "name": str(item.get("displayName") or item.get("name") or slug).strip() or slug,
        "description": str(item.get("summary") or item.get("description") or "").strip(),
        "version": str(item.get("version") or "").strip(),
    }
    return {key: value for key, value in result.items() if value not in ("", None, [], {})}


def fetch_search_results(query: str, limit: int, timeout: int = 10) -> List[Dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query.strip(), "limit": normalize_limit(limit)})
    url = f"{SKILLHUB_SEARCH_URL}?{params}"
    payload = read_json_url(url, timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("invalid search response")

    results = payload.get("results", [])
    if not isinstance(results, list):
        raise RuntimeError("invalid search response")

    normalized: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        cleaned = normalize_remote_skill(item)
        if cleaned:
            normalized.append(cleaned)
    return normalized[: normalize_limit(limit)]


def load_index_skills(timeout: int = 20) -> List[Dict[str, Any]]:
    payload = read_json_url(SKILLHUB_INDEX_URL, timeout=timeout)
    if not isinstance(payload, dict):
        return []
    skills = payload.get("skills", [])
    if not isinstance(skills, list):
        return []
    return [item for item in skills if isinstance(item, dict)]


def find_index_skill(slug: str) -> Dict[str, Any]:
    for item in load_index_skills():
        if str(item.get("slug", "")).strip() == slug:
            return item
    return {}


def build_download_url(template: str, slug: str) -> str:
    return template.replace("{slug}", urllib.parse.quote(slug))


def download_file_or_raise(url: str, dest: Path) -> None:
    payload = http_request(url, "application/zip,application/octet-stream,*/*", timeout=30)
    dest.write_bytes(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"unsafe zip path: {member.filename}")
        archive.extractall(target_dir)


def remove_existing_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def install_skill_archive(
    slug: str,
    target_dir: Path,
    force: bool,
    download_urls: List[str],
    expected_sha256: str = "",
) -> None:
    if target_dir.exists() and not force:
        raise RuntimeError(f"target exists: {target_dir}")

    candidates = [url for url in download_urls if url]
    if not candidates:
        raise RuntimeError(f"no download url for {slug}")

    with tempfile.TemporaryDirectory(prefix="skillhub-install-") as temp_dir:
        temp_root = Path(temp_dir)
        zip_path = temp_root / f"{slug}.zip"
        stage_dir = temp_root / "stage"
        stage_dir.mkdir(parents=True, exist_ok=True)

        last_error = ""
        for url in candidates:
            try:
                download_file_or_raise(url, zip_path)
                last_error = ""
                break
            except Exception as exc:
                last_error = str(exc)
        if last_error:
            raise RuntimeError(last_error)

        if expected_sha256:
            actual_sha256 = sha256_file(zip_path).lower()
            if actual_sha256 != expected_sha256.lower():
                raise RuntimeError(
                    f"sha256 mismatch for {slug}: expected {expected_sha256}, got {actual_sha256}"
                )

        try:
            safe_extract_zip(zip_path, stage_dir)
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"invalid zip archive for {slug}") from exc

        if target_dir.exists():
            if not force:
                raise RuntimeError(f"target exists: {target_dir}")
            remove_existing_path(target_dir)

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage_dir), str(target_dir))


def format_search_results(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "未找到可安装技能"

    lines: List[str] = []
    for index, item in enumerate(results, 1):
        slug = item.get("slug", "unknown")
        name = item.get("name", slug)
        lines.append(f"[{index}] {slug}  {name}")
        if item.get("description"):
            lines.append(f"    {item['description']}")
        if item.get("version"):
            lines.append(f"    version: {item['version']}")
        if item.get("source"):
            lines.append(f"    source: {item['source']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def command_search(args: argparse.Namespace) -> None:
    query = args.query.strip()
    if not query:
        raise RuntimeError("query is required")

    results = fetch_search_results(query, args.limit)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(format_search_results(results))


def build_skill_record(slug: str, lock_skills: Dict[str, Any], disabled_skills: Set[str]) -> Dict[str, Any]:
    skill_path = workspace_skill_dir(slug)
    skill_file = workspace_skill_file(slug)
    exists = skill_file.is_file()
    managed = slug in lock_skills
    metadata = lock_skills.get(slug, {}) if managed else {}
    if not isinstance(metadata, dict):
        metadata = {}

    status = "missing"
    enabled = False
    if exists:
        enabled = slug not in disabled_skills
        status = "enabled" if enabled else "disabled"

    record: Dict[str, Any] = {
        "slug": slug,
        "path": str(skill_path),
        "status": status,
        "enabled": enabled,
        "managed": managed,
    }
    for key in ("name", "version", "source"):
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            record[key] = value
    return record


def collect_workspace_skills() -> List[Dict[str, Any]]:
    lockfile = read_lockfile()
    lock_skills = lockfile.get("skills", {})
    if not isinstance(lock_skills, dict):
        lock_skills = {}
    disabled_skills = load_disabled_skills()

    slugs: Set[str] = set(lock_skills.keys())
    if DEFAULT_INSTALL_ROOT.exists():
        for entry in sorted(DEFAULT_INSTALL_ROOT.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir():
                continue
            if (entry / "SKILL.md").is_file():
                slugs.add(entry.name)

    return [build_skill_record(slug, lock_skills, disabled_skills) for slug in sorted(slugs)]


def format_installed_skills(skills: List[Dict[str, Any]]) -> str:
    if not skills:
        return "未发现任何技能"

    lines: List[str] = []
    for item in skills:
        line = f"{item['slug']}  {item['status']}"
        if item.get("version"):
            line += f"  {item['version']}"
        if item.get("managed"):
            line += "  skillhub"
        lines.append(line)
    return "\n".join(lines)


def build_skill_state_result(slug: str, status: str | None = None) -> Dict[str, Any]:
    lockfile = read_lockfile()
    lock_skills = lockfile.get("skills", {})
    if not isinstance(lock_skills, dict):
        lock_skills = {}
    disabled_skills = load_disabled_skills()
    record = build_skill_record(slug, lock_skills, disabled_skills)
    if status:
        record["status"] = status
    return record


def ensure_skill_enabled(slug: str) -> None:
    disabled_skills = load_disabled_skills()
    if slug in disabled_skills:
        disabled_skills.discard(slug)
        save_disabled_skills(disabled_skills)


def resolve_install_metadata(slug: str) -> Dict[str, Any]:
    search_results = fetch_search_results(slug, limit=20)
    exact_match = next((item for item in search_results if item.get("slug") == slug), None)
    if exact_match:
        metadata = dict(exact_match)
        metadata["source"] = SKILLHUB_SOURCE_LABEL
        return metadata

    index_skill = find_index_skill(slug)
    if index_skill:
        metadata = normalize_remote_skill(index_skill)
        metadata["source"] = SKILLHUB_SOURCE_LABEL
        expected_sha256 = str(index_skill.get("sha256") or index_skill.get("checksum") or "").strip()
        if expected_sha256:
            metadata["sha256"] = expected_sha256
        return metadata

    return {
        "slug": slug,
        "name": slug,
        "source": SKILLHUB_SOURCE_LABEL,
    }


def command_install(args: argparse.Namespace) -> None:
    slug = normalize_slug(args.slug)
    metadata = resolve_install_metadata(slug)
    install_skill_archive(
        slug=slug,
        target_dir=workspace_skill_dir(slug),
        force=args.force,
        download_urls=[
            build_download_url(SKILLHUB_PRIMARY_DOWNLOAD_URL_TEMPLATE, slug),
            build_download_url(SKILLHUB_FALLBACK_DOWNLOAD_URL_TEMPLATE, slug),
        ],
        expected_sha256=str(metadata.get("sha256", "")).strip(),
    )

    lockfile = read_lockfile()
    skills = lockfile.get("skills", {})
    if not isinstance(skills, dict):
        skills = {}
        lockfile["skills"] = skills
    skills[slug] = {
        "name": metadata.get("name", slug),
        "zip_url": build_download_url(SKILLHUB_PRIMARY_DOWNLOAD_URL_TEMPLATE, slug),
        "source": metadata.get("source", SKILLHUB_SOURCE_LABEL),
        "version": metadata.get("version", ""),
    }
    save_lockfile(lockfile)

    require_workspace_skill(slug)
    ensure_skill_enabled(slug)
    install_result = build_skill_state_result(slug, status="installed")
    install_result["enabled"] = True

    if args.json:
        print(json.dumps(install_result, ensure_ascii=False, indent=2))
        return
    print(format_installed_skills([install_result]))


def command_list(args: argparse.Namespace) -> None:
    skills = collect_workspace_skills()
    if args.json:
        print(json.dumps(skills, ensure_ascii=False, indent=2))
        return
    print(format_installed_skills(skills))


def set_skill_enabled(slug: str, enabled: bool) -> Dict[str, Any]:
    require_workspace_skill(slug)
    disabled_skills = load_disabled_skills()
    if enabled:
        disabled_skills.discard(slug)
        status = "enabled"
    else:
        disabled_skills.add(slug)
        status = "disabled"
    save_disabled_skills(disabled_skills)
    return build_skill_state_result(slug, status=status)


def command_enable(args: argparse.Namespace) -> None:
    slug = normalize_slug(args.slug)
    result = set_skill_enabled(slug, enabled=True)
    result["enabled"] = True
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(format_installed_skills([result]))


def command_disable(args: argparse.Namespace) -> None:
    slug = normalize_slug(args.slug)
    result = set_skill_enabled(slug, enabled=False)
    result["enabled"] = False
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(format_installed_skills([result]))


def delete_skill_state(slug: str) -> Dict[str, Any]:
    skill_dir = workspace_skill_dir(slug)
    lockfile = read_lockfile()
    lock_skills = lockfile.get("skills", {})
    if not isinstance(lock_skills, dict):
        lock_skills = {}
        lockfile["skills"] = lock_skills
    disabled_skills = load_disabled_skills()

    has_state = skill_dir.exists() or slug in lock_skills or slug in disabled_skills
    if not has_state:
        raise RuntimeError(f"skill not found: {slug}")

    if skill_dir.is_dir():
        shutil.rmtree(skill_dir)
    elif skill_dir.exists():
        skill_dir.unlink()

    if slug in lock_skills:
        del lock_skills[slug]
        save_lockfile(lockfile)

    if slug in disabled_skills:
        disabled_skills.discard(slug)
        save_disabled_skills(disabled_skills)

    return {
        "slug": slug,
        "path": str(skill_dir),
        "status": "deleted",
        "enabled": False,
        "managed": False,
    }


def command_delete(args: argparse.Namespace) -> None:
    slug = normalize_slug(args.slug)
    result = delete_skill_state(slug)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(format_installed_skills([result]))


def safe_extract_tar(archive_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            member_path = (target_dir / member.name).resolve()
            if member_path != target_root and target_root not in member_path.parents:
                raise RuntimeError(f"unsafe archive path: {member.name}")
        archive.extractall(path=target_dir)


def resolve_kit_paths(extract_dir: Path) -> Dict[str, Path]:
    layouts = [
        {
            "cli": extract_dir / "cli",
            "plugin": extract_dir / "cli" / "plugin",
            "skill": extract_dir / "cli" / "skill",
        },
        {
            "cli": extract_dir,
            "plugin": extract_dir / "plugin",
            "skill": extract_dir / "skill",
        },
    ]

    for layout in layouts:
        if (layout["cli"] / "skills_store_cli.py").is_file():
            return layout
    raise RuntimeError(f"invalid skillhub kit layout: {extract_dir}")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def skillhub_install_base() -> Path:
    return (Path.home() / ".skillhub").resolve()


def skillhub_config_path() -> Path:
    return skillhub_install_base() / "config.json"


def current_workspace_skills_dir() -> Path:
    return DEFAULT_INSTALL_ROOT


def openclaw_plugin_dir() -> Path:
    return default_openclaw_home() / "extensions" / "skillhub"


def find_openclaw_bin() -> str:
    binary = shutil.which("openclaw")
    if binary:
        return binary
    if os.name != "nt":
        fallback = Path.home() / ".local" / "share" / "pnpm" / "openclaw"
        if fallback.is_file() and os.access(fallback, os.X_OK):
            return str(fallback)
    return ""


def set_workspace_skills_preference(enabled: bool) -> None:
    config_path = skillhub_config_path()
    default_update_url = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/version.json"
    raw: Dict[str, Any] = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}

    if not isinstance(raw.get("self_update_url"), str) or not raw["self_update_url"].strip():
        raw["self_update_url"] = default_update_url
    raw["install_workspace_skills"] = enabled
    write_json_file(config_path, raw)


def install_cli_from_kit(cli_src_dir: Path) -> None:
    cli_target_dir = skillhub_install_base()
    cli_target = cli_target_dir / "skills_store_cli.py"
    upgrade_target = cli_target_dir / "skills_upgrade.py"
    version_target = cli_target_dir / "version.json"
    metadata_target = cli_target_dir / "metadata.json"
    index_target = cli_target_dir / "skills_index.local.json"
    wrapper_target = SKILLHUB_BIN_PATH
    legacy_wrapper_target = SKILLHUB_BIN_DIR / LEGACY_SKILLHUB_BIN_NAME

    cli_target_dir.mkdir(parents=True, exist_ok=True)
    SKILLHUB_BIN_DIR.mkdir(parents=True, exist_ok=True)

    required = {
        "skills_store_cli.py": cli_target,
        "skills_upgrade.py": upgrade_target,
        "version.json": version_target,
        "metadata.json": metadata_target,
    }
    for filename, target in required.items():
        source = cli_src_dir / filename
        if not source.is_file():
            raise RuntimeError(f"missing {filename} in skillhub kit")
        shutil.copyfile(source, target)

    local_index = cli_src_dir / "skills_index.local.json"
    if local_index.is_file():
        shutil.copyfile(local_index, index_target)

    config_target = skillhub_config_path()
    if not config_target.exists():
        write_json_file(
            config_target,
            {
                "self_update_url": (
                    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/version.json"
                )
            },
        )

    if os.name == "nt":
        wrapper = (
            "@echo off\r\n"
            "setlocal\r\n"
            "set \"BASE=%USERPROFILE%\\.skillhub\"\r\n"
            "set \"CLI=%BASE%\\skills_store_cli.py\"\r\n"
            "if not exist \"%CLI%\" (\r\n"
            "  echo Error: CLI not found at %CLI% 1>&2\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "where py >nul 2>nul\r\n"
            "if %ERRORLEVEL%==0 (\r\n"
            "  py -3 \"%CLI%\" %*\r\n"
            "  exit /b %ERRORLEVEL%\r\n"
            ")\r\n"
            "where python >nul 2>nul\r\n"
            "if %ERRORLEVEL%==0 (\r\n"
            "  python \"%CLI%\" %*\r\n"
            "  exit /b %ERRORLEVEL%\r\n"
            ")\r\n"
            "echo Error: python launcher not found 1>&2\r\n"
            "exit /b 1\r\n"
        )
        legacy_wrapper = (
            "@echo off\r\n"
            f"\"{wrapper_target}\" %*\r\n"
        )
        write_text_file(wrapper_target, wrapper)
        write_text_file(legacy_wrapper_target, legacy_wrapper)
    else:
        wrapper = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            "BASE=\"${HOME}/.skillhub\"\n"
            "CLI=\"${BASE}/skills_store_cli.py\"\n\n"
            "if [[ ! -f \"${CLI}\" ]]; then\n"
            "  echo \"Error: CLI not found at ${CLI}\" >&2\n"
            "  exit 1\n"
            "fi\n\n"
            "exec python3 \"${CLI}\" \"$@\"\n"
        )
        legacy_wrapper = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "exec \"${HOME}/.local/bin/skillhub\" \"$@\"\n"
        )
        write_text_file(wrapper_target, wrapper)
        write_text_file(legacy_wrapper_target, legacy_wrapper)
        wrapper_target.chmod(0o755)
        legacy_wrapper_target.chmod(0o755)


def install_skill_templates_from_kit(skill_src_dir: Path) -> None:
    find_skill_src = skill_src_dir / "SKILL.md"
    preference_skill_src = skill_src_dir / "SKILL.skillhub-preference.md"
    workspace_skills_dir = current_workspace_skills_dir()

    if find_skill_src.is_file():
        target = workspace_skills_dir / "find-skills" / "SKILL.md"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(find_skill_src, target)
    if preference_skill_src.is_file():
        target = workspace_skills_dir / "skillhub-preference" / "SKILL.md"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(preference_skill_src, target)


def install_plugin_from_kit(plugin_src_dir: Path) -> None:
    target_dir = openclaw_plugin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("index.ts", "openclaw.plugin.json"):
        source = plugin_src_dir / filename
        if not source.is_file():
            raise RuntimeError(f"missing {filename} in skillhub kit")
        shutil.copyfile(source, target_dir / filename)


def disable_plugin_if_present() -> None:
    openclaw_bin = find_openclaw_bin()
    if not openclaw_bin:
        return
    subprocess.run(
        [openclaw_bin, "config", "unset", "plugins.entries.skillhub"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def configure_plugin() -> None:
    openclaw_bin = find_openclaw_bin()
    if not openclaw_bin:
        return
    commands = [
        ["config", "set", "plugins.entries.skillhub.enabled", "true"],
        ["config", "set", "plugins.entries.skillhub.config.primaryCli", "skillhub"],
        ["config", "set", "plugins.entries.skillhub.config.fallbackCli", "clawhub"],
        ["config", "set", "plugins.entries.skillhub.config.primaryLabel", "cn-optimized"],
        ["config", "set", "plugins.entries.skillhub.config.fallbackLabel", "public-registry"],
    ]
    for arguments in commands:
        subprocess.run(
            [openclaw_bin, *arguments],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )


def restart_gateway_if_needed() -> None:
    openclaw_bin = find_openclaw_bin()
    if not openclaw_bin:
        return
    subprocess.Popen(
        [openclaw_bin, "gateway", "run", "--bind", "loopback", "--port", "18789", "--force"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_skillhub_from_kit(extract_dir: Path, args: argparse.Namespace) -> None:
    paths = resolve_kit_paths(extract_dir)
    mode = "all"
    if args.cli_only:
        mode = "cli"
    elif args.skill_only:
        mode = "skill"
    elif args.plugin_only:
        mode = "plugin"

    if mode in ("all", "cli"):
        install_cli_from_kit(paths["cli"])

    if args.no_skills:
        set_workspace_skills_preference(False)
    elif args.with_skills:
        set_workspace_skills_preference(True)

    if mode in ("all", "skill"):
        if not args.no_skills:
            install_skill_templates_from_kit(paths["skill"])
        disable_plugin_if_present()

    if mode == "plugin":
        install_plugin_from_kit(paths["plugin"])
        configure_plugin()

    if args.restart_gateway:
        restart_gateway_if_needed()


def detect_skillhub_version() -> str:
    if not SKILLHUB_BIN_PATH.is_file():
        return ""
    command = [str(SKILLHUB_BIN_PATH), "--version"]
    if os.name == "nt":
        command = ["cmd", "/c", str(SKILLHUB_BIN_PATH), "--version"]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or result.stderr).strip()


def command_bootstrap(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="skillhub-kit-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / "latest.tar.gz"

        with urllib.request.urlopen(args.kit_url, timeout=60) as response:
            payload = response.read()
        archive_path.write_bytes(payload)

        safe_extract_tar(archive_path, temp_root)
        install_skillhub_from_kit(temp_root, args)

    bootstrap_result: Dict[str, Any] = {
        "status": "installed",
        "kit_url": args.kit_url,
        "installer": "python-bootstrap",
    }
    if SKILLHUB_BIN_PATH.is_file():
        bootstrap_result["skillhub_bin"] = str(SKILLHUB_BIN_PATH)
    version = detect_skillhub_version()
    if version:
        bootstrap_result["skillhub_version"] = version

    if args.json:
        print(json.dumps(bootstrap_result, ensure_ascii=False, indent=2))
        return

    lines = [f"status: {bootstrap_result['status']}"]
    if bootstrap_result.get("skillhub_bin"):
        lines.append(f"skillhub_bin: {bootstrap_result['skillhub_bin']}")
    if bootstrap_result.get("skillhub_version"):
        lines.append(f"skillhub_version: {bootstrap_result['skillhub_version']}")
    print("\n".join(lines))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="技能搜索、安装与管理工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="搜索技能")
    search.add_argument("query", help="搜索关键词")
    search.add_argument("--limit", type=int, default=10, help="返回数量")
    search.add_argument("--json", action="store_true", help="输出 JSON")
    search.set_defaults(func=command_search)

    install = subparsers.add_parser("install", help="安装技能")
    install.add_argument("slug", help="技能 slug")
    install.add_argument("--force", action="store_true", help="覆盖已存在目录")
    install.add_argument("--json", action="store_true", help="输出 JSON")
    install.set_defaults(func=command_install)

    list_parser = subparsers.add_parser("list", help="列出当前 workspace 技能")
    list_parser.add_argument("--json", action="store_true", help="输出 JSON")
    list_parser.set_defaults(func=command_list)

    enable = subparsers.add_parser("enable", help="启用技能")
    enable.add_argument("slug", help="技能 slug")
    enable.add_argument("--json", action="store_true", help="输出 JSON")
    enable.set_defaults(func=command_enable)

    disable = subparsers.add_parser("disable", help="禁用技能")
    disable.add_argument("slug", help="技能 slug")
    disable.add_argument("--json", action="store_true", help="输出 JSON")
    disable.set_defaults(func=command_disable)

    delete = subparsers.add_parser("delete", help="删除技能")
    delete.add_argument("slug", help="技能 slug")
    delete.add_argument("--json", action="store_true", help="输出 JSON")
    delete.set_defaults(func=command_delete)

    bootstrap = subparsers.add_parser("bootstrap", help="安装 SkillHub CLI")
    mode_group = bootstrap.add_mutually_exclusive_group()
    mode_group.add_argument("--cli-only", action="store_true", help="仅安装 CLI")
    mode_group.add_argument("--skill-only", action="store_true", help="仅安装 SkillHub 自带技能")
    mode_group.add_argument("--plugin-only", action="store_true", help="仅安装插件")
    preference_group = bootstrap.add_mutually_exclusive_group()
    preference_group.add_argument("--no-skills", action="store_true", help="跳过 workspace skills")
    preference_group.add_argument("--with-skills", action="store_true", help="强制安装 workspace skills")
    bootstrap.add_argument("--restart-gateway", action="store_true", help="安装后重启 gateway")
    bootstrap.add_argument("--kit-url", default=SKILLHUB_INSTALL_KIT_URL, help=argparse.SUPPRESS)
    bootstrap.add_argument("--json", action="store_true", help="输出 JSON")
    bootstrap.set_defaults(func=command_bootstrap)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
