from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np
import torch
from PIL import Image


LOCAL_BASE_URL_PORTS = (3000, 3100)
LOCAL_BASE_URL_HOSTS = ("127.0.0.1", "localhost")
LTX_VERSION_PATTERN = re.compile(r"ltx2\.3-(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


VIDEO_RESOLUTION_LABELS = {
    "1080p (1080P 高清)": "1080p",
    "720p (720P 标准)": "720p",
    "540p (540P 预览)": "540p",
}

UPSCALE_RESOLUTION_LABELS = {
    "1080p (1080P 高清)": "1080p",
    "720p (720P 标准)": "720p",
    "544p (544P 预览)": "544p",
}

ASPECT_RATIO_LABELS = {
    "16:9 (横屏)": "16:9",
    "9:16 (竖屏)": "9:16",
}

CAMERA_MOTION_LABELS = {
    "static (静止机位)": "static",
    "dolly_in (推进)": "dolly_in",
    "dolly_out (拉远)": "dolly_out",
    "dolly_left (向左)": "dolly_left",
    "dolly_right (向右)": "dolly_right",
    "jib_up (升臂)": "jib_up",
    "jib_down (降臂)": "jib_down",
    "focus_shift (焦点)": "focus_shift",
}

IMAGE_PRESET_SIZES = {
    "1:1 Square (1024x1024)": (1024, 1024),
    "16:9 Landscape (1280x720)": (1280, 720),
    "9:16 Portrait (720x1280)": (720, 1280),
    "Custom 自定义...": None,
}

# 图片比例预设（不含具体尺寸）
IMAGE_ASPECT_RATIOS = {
    "1:1 (正方形)": (1, 1),
    "16:9 (横屏)": (16, 9),
    "9:16 (竖屏)": (9, 16),
    "4:3 (传统横屏)": (4, 3),
    "3:4 (传统竖屏)": (3, 4),
    "21:9 (超宽屏)": (21, 9),
    "3:2 (摄影横屏)": (3, 2),
    "2:3 (摄影竖屏)": (2, 3),
    "Custom 自定义...": None,
}

SEED_MODE_LABELS = {
    "fixed (固定种子)": "fixed",
    "random (每次随机)": "random",
}


def _choice_keys(mapping: dict[str, str]) -> list[str]:
    return list(mapping.keys())


def _normalize_choice(value: str, mapping: dict[str, str]) -> str:
    if value in mapping:
        return mapping[value]
    if value in mapping.values():
        return value
    return value


def _json_request(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body or f"HTTP {exc.code}"}
        raise RuntimeError(parsed.get("detail") or parsed.get("error") or f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _read_bytes(url: str, timeout: int = 60) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"下载结果失败: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"下载结果失败: {exc.reason}") from exc


def _normalize_base_url_text(base_url: str) -> str:
    text = str(base_url or "").strip()
    if not text:
        return "http://127.0.0.1:3000"
    if "://" not in text:
        text = f"http://{text}"
    return text.rstrip("/")


def _base_url(config: dict) -> str:
    return _normalize_base_url_text(
        str(config.get("_resolved_base_url") or config.get("base_url") or "")
    )


def _parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(_normalize_base_url_text(base_url))
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _candidate_base_urls(config: dict) -> list[str]:
    primary = _normalize_base_url_text(str(config.get("base_url") or ""))
    candidates: list[str] = []

    def _append(url: str) -> None:
        normalized = _normalize_base_url_text(url)
        if normalized not in candidates:
            candidates.append(normalized)

    _append(primary)

    parsed = urllib.parse.urlparse(primary)
    host = parsed.hostname or "127.0.0.1"
    scheme = parsed.scheme or "http"
    if host in {"127.0.0.1", "localhost", "0.0.0.0"}:
        for local_host in LOCAL_BASE_URL_HOSTS:
            for port in LOCAL_BASE_URL_PORTS:
                _append(f"{scheme}://{local_host}:{port}")

    return candidates


def _can_connect(base_url: str, timeout: float = 2.0) -> bool:
    host, port = _parse_host_port(base_url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_base_url(base_url: str, timeout: int = 5) -> bool:
    if not _can_connect(base_url):
        return False
    try:
        _json_request("GET", f"{_normalize_base_url_text(base_url)}/health", timeout=timeout)
        return True
    except Exception:
        return False


def _resolve_active_base_url(config: dict, timeout: int = 5) -> str | None:
    for candidate in _candidate_base_urls(config):
        if _probe_base_url(candidate, timeout=timeout):
            config["_resolved_base_url"] = candidate
            return candidate
    return None


def _is_missing_route_error(exc: Exception) -> bool:
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, urllib.error.HTTPError) and cause.code == 404:
        return True

    text = str(exc or "").strip().lower()
    return "404" in text or "not found" in text or "no route" in text


def _normalize_vram_limit_value(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if text.lower() in {"none", "null", "default", "auto", "off"}:
        return ""

    try:
        number = float(text)
    except ValueError as exc:
        raise RuntimeError("vram_limit_gb must be a number, 0, or empty.") from exc

    if number < 0:
        raise RuntimeError("vram_limit_gb must be >= 0.")
    if number == 0:
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _post_vram_limit(config: dict, value: str, timeout: int = 30) -> dict:
    return _json_request(
        "POST",
        f"{_base_url(config)}/api/vram-limit",
        {"vramLimit": value},
        timeout=timeout,
    )


def _get_vram_limit(config: dict, timeout: int = 30) -> dict:
    return _json_request(
        "GET",
        f"{_base_url(config)}/api/vram-limit",
        timeout=timeout,
    )


def _get_low_vram_mode_state(config: dict, timeout: int = 30) -> dict:
    return _json_request(
        "GET",
        f"{_base_url(config)}/api/system/low-vram-mode",
        timeout=timeout,
    )


def _is_low_vram_mode_effective(config: dict, timeout: int = 10) -> bool:
    if bool(config.get("low_vram_mode_locked")):
        return bool(config.get("low_vram_mode"))
    try:
        data = _get_low_vram_mode_state(config, timeout=timeout)
        return bool(data.get("enabled", False))
    except Exception:
        return False


def _sync_vram_limit_with_low_vram_policy(config: dict, timeout: int = 30) -> tuple[bool | None, bool]:
    low_vram_effective = _is_low_vram_mode_effective(config, timeout=min(timeout, 10))
    if low_vram_effective:
        try:
            _post_vram_limit(config, "", timeout=timeout)
            return (True, True)
        except Exception as exc:
            if _is_missing_route_error(exc):
                return (False, True)
            raise

    if bool(config.get("vram_limit_locked")):
        normalized_vram_limit = _normalize_vram_limit_value(config.get("vram_limit", ""))
        config["vram_limit"] = normalized_vram_limit
        try:
            _post_vram_limit(config, normalized_vram_limit, timeout=timeout)
            return (True, False)
        except Exception as exc:
            if _is_missing_route_error(exc):
                return (False, False)
            raise

    return (None, False)


def _is_low_vram_mode_requested(config: dict) -> bool:
    return bool(config.get("low_vram_mode_locked")) and bool(config.get("low_vram_mode"))


def _mark_vram_limit_ignored(status: dict) -> dict:
    status["ignored"] = True
    status["reason"] = "low_vram_mode_enabled"
    status["effectiveVramLimit"] = ""
    return status


def _wait_for_server(config: dict) -> None:
    base_url = _base_url(config)
    deadline = time.time() + int(config.get("health_timeout_s", 60))
    last_error = None
    while time.time() < deadline:
        if _can_connect(base_url):
            try:
                _json_request("GET", f"{base_url}/health", timeout=5)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(2)
    raise RuntimeError(f"LTX Desktop 后端未就绪: {last_error or base_url}")


def _wait_for_resolved_server(config: dict) -> None:
    deadline = time.time() + int(config.get("health_timeout_s", 60))
    last_error = None
    candidates = _candidate_base_urls(config)
    while time.time() < deadline:
        for candidate in candidates:
            if not _can_connect(candidate):
                continue
            try:
                _json_request("GET", f"{candidate}/health", timeout=5)
                config["_resolved_base_url"] = candidate
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(2)
    raise RuntimeError(f"LTX Desktop 后端未就绪: {last_error or ', '.join(candidates)}")


def _looks_like_launcher_root(path: Path) -> bool:
    try:
        return (
            path.exists()
            and path.is_dir()
            and (path / "run.bat").exists()
            and ((path / "patches" / "launcher.py").exists() or (path / "main.py").exists())
        )
    except OSError:
        return False


def _launcher_version_key(path: Path) -> tuple[int, int, int]:
    match = LTX_VERSION_PATTERN.search(str(path))
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def _discover_launcher_root(requested_root: str = "") -> Path | None:
    search_roots: list[Path] = []
    for root in (Path.cwd(), Path.home() / "Desktop", Path.home() / "Downloads"):
        try:
            if root.exists() and root.is_dir():
                search_roots.append(root)
        except OSError:
            continue

    requested_text = str(requested_root or "").strip().replace("\\", "/")
    requested_name = Path(requested_text).name.lower() if requested_text else ""

    candidates: list[Path] = []
    seen: set[str] = set()
    for root in search_roots:
        try:
            for run_bat in root.rglob("run.bat"):
                candidate = run_bat.parent
                key = str(candidate).lower()
                if key in seen or not _looks_like_launcher_root(candidate):
                    continue
                seen.add(key)
                candidates.append(candidate)
        except Exception:
            continue

    if not candidates:
        return None

    def _score(path: Path) -> tuple[int, int, int, int, int]:
        name = path.name.lower()
        full = str(path).lower().replace("\\", "/")
        version = _launcher_version_key(path)
        return (
            0 if requested_name and name == requested_name else 1,
            0 if requested_text and requested_text.split("/")[-1] in full else 1,
            -version[0],
            -version[1],
            -version[2],
            len(full),
        )

    candidates.sort(key=_score)
    return candidates[0]


def _resolve_launcher_root(config: dict) -> Path:
    requested_root = str(config.get("launcher_root", "") or "").strip()
    if requested_root:
        requested_path = Path(requested_root).expanduser()
        if _looks_like_launcher_root(requested_path):
            return requested_path

    discovered = _discover_launcher_root(requested_root)
    if discovered is not None:
        config["launcher_root"] = str(discovered)
        return discovered

    if requested_root:
        raise RuntimeError(f"找不到启动脚本: {Path(requested_root) / 'run.bat'}")
    raise RuntimeError("已开启自动启动，但没有找到可用的 LTX Desktop run.bat。请检查 launcher_root。")


def _start_launcher_if_needed(config: dict) -> None:
    resolved_base_url = _resolve_active_base_url(config, timeout=5)
    if resolved_base_url:
        return

    base_url = _base_url(config)
    if _probe_base_url(base_url, timeout=5):
        return

    if not config.get("auto_start"):
        raise RuntimeError(
            f"LTX Desktop 后端未运行: {base_url}。请先启动官方桌面版或这个项目的 run.bat。"
        )

    launcher_root = str(_resolve_launcher_root(config))
    if not launcher_root:
        raise RuntimeError("已开启自动启动，但没有提供 launcher_root。")

    run_bat = Path(launcher_root) / "run.bat"
    if not run_bat.exists():
        raise RuntimeError(f"找不到启动脚本: {run_bat}")

    if os.name == "nt":
        launch_error = None
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        commands = [
            ["cmd", "/d", "/c", "start", "", "/d", str(run_bat.parent), str(run_bat)],
            ["cmd", "/d", "/c", str(run_bat)],
        ]
        for command in commands:
            try:
                subprocess.Popen(
                    command,
                    cwd=str(run_bat.parent),
                    creationflags=creationflags,
                )
                launch_error = None
                break
            except Exception as exc:
                launch_error = exc
        if launch_error is not None:
            raise RuntimeError(f"自动启动 run.bat 失败: {launch_error}") from launch_error
    else:
        subprocess.Popen([str(run_bat)], cwd=str(run_bat.parent))

    _wait_for_resolved_server(config)


def _prepare_runtime(config: dict) -> None:
    _start_launcher_if_needed(config)
    base_url = _base_url(config)

    output_dir = str(config.get("output_dir", "") or "").strip()
    if output_dir:
        _json_request(
            "POST",
            f"{base_url}/api/system/set-dir",
            {"directory": output_dir},
            timeout=30,
        )

    if bool(config.get("low_vram_mode_locked")):
        _json_request(
            "POST",
            f"{base_url}/api/system/low-vram-mode",
            {"enabled": bool(config.get("low_vram_mode"))},
            timeout=30,
        )

    supported, ignored = _sync_vram_limit_with_low_vram_policy(config, timeout=30)
    if supported is not None:
        config["_vram_limit_supported"] = supported
    config["_vram_limit_ignored_due_to_low_vram"] = bool(ignored)

    gpu_id = int(config.get("gpu_id", -1))
    if gpu_id >= 0:
        gpus = _json_request("GET", f"{base_url}/api/system/list-gpus", timeout=30).get("gpus", [])
        active = next((gpu for gpu in gpus if gpu.get("active")), None)
        if not active or int(active.get("id", -1)) != gpu_id:
            _json_request(
                "POST",
                f"{base_url}/api/system/switch-gpu",
                {"gpu_id": gpu_id},
                timeout=max(60, int(config.get("request_timeout_s", 1800))),
            )

    if bool(config.get("clear_gpu_before_run")):
        _json_request("POST", f"{base_url}/api/system/clear-gpu", {}, timeout=120)


def _reset_state(config: dict) -> None:
    try:
        _json_request("POST", f"{_base_url(config)}/api/system/reset-state", {}, timeout=15)
    except Exception:
        pass


def _tensor_to_pil(image: torch.Tensor) -> Image.Image:
    tensor = image.detach().cpu()
    if tensor.ndim == 4:
        tensor = tensor[0]
    tensor = tensor.clamp(0.0, 1.0)
    array = (tensor.numpy() * 255.0).round().astype(np.uint8)
    if array.ndim == 2:
        return Image.fromarray(array, mode="L").convert("RGB")
    if array.shape[-1] == 4:
        return Image.fromarray(array, mode="RGBA").convert("RGB")
    return Image.fromarray(array, mode="RGB")


def _pil_to_tensor(image: Image.Image) -> torch.Tensor:
    rgb = image.convert("RGB")
    array = np.asarray(rgb).astype(np.float32) / 255.0
    return torch.from_numpy(array)[None, ...]


def _save_tensor_temp(image: torch.Tensor, prefix: str) -> tuple[bytes, str]:
    pil = _tensor_to_pil(image)
    buffer = io.BytesIO()
    pil.save(buffer, format="PNG")
    return buffer.getvalue(), f"{prefix}.png"


def _upload_blob(config: dict, blob: bytes, filename: str) -> str:
    payload = {
        "image": base64.b64encode(blob).decode("ascii"),
        "filename": filename,
    }
    data = _json_request(
        "POST",
        f"{_base_url(config)}/api/system/upload-image",
        payload,
        timeout=max(60, int(config.get("request_timeout_s", 1800))),
    )
    path = data.get("path")
    if not path:
        raise RuntimeError(f"上传失败: {filename}")
    return str(path)


def _upload_tensor(config: dict, image: torch.Tensor, prefix: str) -> str:
    blob, filename = _save_tensor_temp(image, prefix)
    return _upload_blob(config, blob, filename)


def _upload_local_file(config: dict, path: str, prefix: str) -> str:
    src = Path(path).expanduser()
    if not src.exists() or not src.is_file():
        raise RuntimeError(f"文件不存在: {src}")
    data = src.read_bytes()
    safe_name = f"{prefix}_{src.name}"
    return _upload_blob(config, data, safe_name)


def _audio_to_wav_bytes(audio_input) -> tuple[bytes, str]:
    if audio_input is None:
        raise RuntimeError("未提供 ComfyUI 音频输入。")
    if not isinstance(audio_input, dict):
        raise RuntimeError(f"不支持的音频输入类型: {type(audio_input).__name__}")

    waveform = audio_input.get("waveform")
    sample_rate = audio_input.get("sample_rate") or audio_input.get("sr") or audio_input.get("sampling_rate")

    if waveform is None or sample_rate is None:
        raise RuntimeError("ComfyUI 音频输入缺少 waveform/sample_rate。")

    if isinstance(waveform, np.ndarray):
        tensor = torch.from_numpy(waveform)
    elif isinstance(waveform, torch.Tensor):
        tensor = waveform.detach().cpu()
    else:
        tensor = torch.as_tensor(waveform)

    if tensor.ndim == 3:
        tensor = tensor[0]
    elif tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)

    if tensor.ndim != 2:
        raise RuntimeError(f"不支持的音频波形维度: {tuple(tensor.shape)}")

    tensor = tensor.to(torch.float32).clamp(-1.0, 1.0).contiguous()
    if tensor.shape[0] == 1:
        # LTX A2V local pipeline expects 2-channel audio features.
        tensor = tensor.repeat(2, 1)
    elif tensor.shape[0] > 2:
        tensor = tensor[:2, :]

    channels = int(tensor.shape[0])
    pcm = (tensor.transpose(0, 1).numpy() * 32767.0).round().astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm.tobytes())

    return buffer.getvalue(), "ref_audio.wav"


def _upload_audio_input(config: dict, audio_input, prefix: str) -> str:
    blob, filename = _audio_to_wav_bytes(audio_input)
    return _upload_blob(config, blob, f"{prefix}_{filename}")


def _resolve_fetch_url(config: dict, file_or_path: str) -> str:
    base_url = _base_url(config)
    if "\\" in file_or_path or "/" in file_or_path:
        query = urllib.parse.urlencode({"path": file_or_path})
        return f"{base_url}/api/system/file?{query}"
    return f"{base_url}/outputs/{urllib.parse.quote(file_or_path)}"


def _load_remote_image_tensor(config: dict, path: str) -> torch.Tensor:
    raw = _read_bytes(_resolve_fetch_url(config, path), timeout=120)
    return _pil_to_tensor(Image.open(io.BytesIO(raw)))


def _fetch_history_items(config: dict, limit: int) -> list[dict]:
    _prepare_runtime(config)
    data = _json_request(
        "GET",
        f"{_base_url(config)}/api/system/history?page=1&limit={int(limit)}",
        timeout=30,
    )
    return list(data.get("history") or [])


def _fetch_loras_data(config: dict, lora_dir: str = "") -> dict:
    _start_launcher_if_needed(config)
    params = {}
    target_dir = str(lora_dir or config.get("lora_dir") or "").strip()
    if target_dir:
        params["dir"] = target_dir
    query = urllib.parse.urlencode(params) if params else ""
    url = f"{_base_url(config)}/api/loras"
    if query:
        url = f"{url}?{query}"
    return _json_request("GET", url, timeout=30)


def _resolve_lora_path(config: dict, lora_ref: str, lora_dir: str = "") -> str:
    raw_value = str(lora_ref or "").strip()
    if not raw_value:
        return ""

    direct_path = Path(raw_value).expanduser()
    if direct_path.exists() and direct_path.is_file():
        return str(direct_path.resolve())

    data = _fetch_loras_data(config, lora_dir)
    candidates = list(data.get("loras") or [])
    if not candidates:
        raise RuntimeError("指定的 LoRA 目录下没有扫描到任何 LoRA 文件。")

    query = raw_value.lower()
    query_stem = Path(raw_value).stem.lower()

    def _name(item: dict) -> str:
        return str(item.get("name") or "").strip()

    def _path(item: dict) -> str:
        return str(item.get("path") or "").strip()

    def _pick(matches: list[dict]) -> str | None:
        if len(matches) == 1:
            return _path(matches[0])
        return None

    exact_name = [
        item for item in candidates if _name(item).lower() == query or Path(_name(item)).stem.lower() == query
    ]
    picked = _pick(exact_name)
    if picked:
        return picked

    exact_stem = [item for item in candidates if Path(_name(item)).stem.lower() == query_stem]
    picked = _pick(exact_stem)
    if picked:
        return picked

    prefix_matches = [
        item
        for item in candidates
        if _name(item).lower().startswith(query) or Path(_name(item)).stem.lower().startswith(query_stem)
    ]
    picked = _pick(prefix_matches)
    if picked:
        return picked

    fuzzy_matches = [
        item
        for item in candidates
        if query in _name(item).lower() or query_stem in Path(_name(item)).stem.lower()
    ]
    picked = _pick(fuzzy_matches)
    if picked:
        return picked

    if len(exact_name) > 1 or len(exact_stem) > 1 or len(prefix_matches) > 1 or len(fuzzy_matches) > 1:
        pool = exact_name or exact_stem or prefix_matches or fuzzy_matches
        names = ", ".join(_name(item) for item in pool[:10])
        raise RuntimeError(f"匹配到多个 LoRA，请填更完整的名字。候选: {names}")

    names = ", ".join(_name(item) for item in candidates[:10])
    raise RuntimeError(f"没有找到匹配的 LoRA: {raw_value}。当前目录候选: {names}")


def _normalize_lora_choice(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("<") and raw.endswith(">"):
        return ""
    return raw


def _clone_config(config: dict) -> dict:
    return dict(config or {})


def _resolve_video_reference(config: dict, video_ref: str) -> str:
    raw_value = str(video_ref or "").strip()
    if not raw_value:
        return ""

    local_path = Path(raw_value).expanduser()
    if local_path.exists() and local_path.is_file():
        return str(local_path.resolve())

    filename = local_path.name
    if not filename:
        return raw_value

    config_output_dir = str(config.get("output_dir", "") or "").strip()
    if config_output_dir:
        candidate = Path(config_output_dir).expanduser() / filename
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())

    try:
        for item in _fetch_history_items(config, 1000):
            if str(item.get("filename", "")) != filename:
                continue
            fullpath = str(item.get("fullpath", "")).strip()
            if not fullpath:
                continue
            history_path = Path(fullpath).expanduser()
            if history_path.exists() and history_path.is_file():
                return str(history_path.resolve())
            return fullpath
    except Exception:
        pass

    return raw_value


def _get_comfyui_output_dir() -> str:
    try:
        import folder_paths  # type: ignore

        output_dir = folder_paths.get_output_directory()
        if output_dir:
            return str(output_dir)
    except Exception:
        pass
    return ""


def _build_comfyui_video_ui_entry(path: Path) -> dict | None:
    output_dir = _get_comfyui_output_dir()
    if not output_dir:
        return None

    try:
        output_path = Path(output_dir).resolve()
        file_path = path.resolve()
        relative_parent = file_path.parent.relative_to(output_path)
    except Exception:
        return None

    subfolder = "" if str(relative_parent) == "." else relative_parent.as_posix()
    suffix = file_path.suffix.lower()
    format_map = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
    }
    return {
        "filename": file_path.name,
        "subfolder": subfolder,
        "type": "output",
        "format": format_map.get(suffix, "video/mp4"),
    }


def _make_safe_video_name(filename_prefix: str, suffix: str) -> str:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_prefix = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in filename_prefix.strip() or "ltx_video"
    )
    return f"{safe_prefix}_{timestamp}{suffix or '.mp4'}"


def _parse_number_list(raw: str, cast=float) -> list[float]:
    text = str(raw or "").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None

    values = parsed if isinstance(parsed, list) else text.replace("\r", "\n").replace(",", "\n").split("\n")
    result = []
    for item in values:
        token = str(item).strip()
        if not token:
            continue
        result.append(cast(token))
    return result


def _parse_text_list(raw: str) -> list[str]:
    text = str(raw or "").replace("\r", "\n")
    if not text.strip():
        return []
    return [line.strip() for line in text.split("\n") if line.strip()]


def _get_image_batch_size(image: torch.Tensor | None) -> int:
    if image is None:
        return 0
    if image.ndim == 4:
        return int(image.shape[0])
    return 1


def _slice_image_batch(image: torch.Tensor, index: int) -> torch.Tensor:
    if image.ndim == 4:
        return image[index : index + 1]
    return image


def _looks_like_legacy_generate_video_binding(
    camera_motion,
    audio,
    audio_path: str,
    inference_steps: int,
) -> bool:
    camera_motion_text = str(camera_motion or "").strip().lower()
    audio_path_text = str(audio_path or "").strip()
    if int(inference_steps) >= 1:
        return False
    if camera_motion_text not in {"true", "false"}:
        return False
    if audio_path_text and audio_path_text.isdigit():
        return True
    return isinstance(audio, bool)


class LTXDesktopConfigNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": "http://127.0.0.1:3000"}),
                "launcher_root": ("STRING", {"default": ""}),
                "auto_start": ("BOOLEAN", {"default": False}),
                "output_dir": ("STRING", {"default": ""}),
                "gpu_id": ("INT", {"default": -1, "min": -1, "max": 32, "step": 1}),
                "clear_gpu_before_run": ("BOOLEAN", {"default": False}),
                "low_vram_mode": ("BOOLEAN", {"default": False}),
                "health_timeout_s": ("INT", {"default": 60, "min": 5, "max": 600, "step": 1}),
                "request_timeout_s": ("INT", {"default": 1800, "min": 30, "max": 7200, "step": 30}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG",)
    RETURN_NAMES = ("config",)
    FUNCTION = "build"
    CATEGORY = "LTX Desktop"

    def build(
        self,
        base_url: str,
        launcher_root: str,
        auto_start: bool,
        output_dir: str,
        gpu_id: int,
        clear_gpu_before_run: bool,
        low_vram_mode: bool,
        health_timeout_s: int,
        request_timeout_s: int,
    ):
        config = {
            "base_url": _normalize_base_url_text(base_url),
            "launcher_root": launcher_root.strip(),
            "auto_start": bool(auto_start),
            "output_dir": output_dir.strip(),
            "gpu_id": int(gpu_id),
            "clear_gpu_before_run": bool(clear_gpu_before_run),
            "low_vram_mode": bool(low_vram_mode),
            # When Config explicitly enables low_vram_mode, treat that as the
            # active runtime policy so downstream VRAM-limit nodes cannot
            # silently override it.
            "low_vram_mode_locked": bool(low_vram_mode),
            "vram_limit": "",
            "vram_limit_locked": False,
            "health_timeout_s": int(health_timeout_s),
            "request_timeout_s": int(request_timeout_s),
        }
        return (config,)


class LTXDesktopSetOutputDirNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "output_dir": ("STRING", {"default": ""}),
                "apply_now": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING")
    RETURN_NAMES = ("config", "output_dir")
    FUNCTION = "apply"
    CATEGORY = "LTX Desktop/System"

    def apply(self, config: dict, output_dir: str, apply_now: bool):
        next_config = _clone_config(config)
        next_config["output_dir"] = output_dir.strip()

        if apply_now and output_dir.strip():
            _start_launcher_if_needed(next_config)
            _json_request(
                "POST",
                f"{_base_url(next_config)}/api/system/set-dir",
                {"directory": output_dir.strip()},
                timeout=30,
            )

        return (next_config, next_config["output_dir"])


class LTXDesktopSwitchGPUNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "gpu_id": ("INT", {"default": 0, "min": -1, "max": 32, "step": 1}),
                "apply_now": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING")
    RETURN_NAMES = ("config", "gpu_status_json")
    FUNCTION = "apply"
    CATEGORY = "LTX Desktop/System"

    def apply(self, config: dict, gpu_id: int, apply_now: bool):
        next_config = _clone_config(config)
        next_config["gpu_id"] = int(gpu_id)

        status = {"requested_gpu_id": int(gpu_id), "applied": False, "gpus": []}
        if apply_now and gpu_id >= 0:
            _start_launcher_if_needed(next_config)
            _json_request(
                "POST",
                f"{_base_url(next_config)}/api/system/switch-gpu",
                {"gpu_id": int(gpu_id)},
                timeout=max(60, int(next_config.get("request_timeout_s", 1800))),
            )
            status["applied"] = True

        try:
            status["gpus"] = _json_request(
                "GET",
                f"{_base_url(next_config)}/api/system/list-gpus",
                timeout=30,
            ).get("gpus", [])
        except Exception:
            pass

        return (next_config, json.dumps(status, ensure_ascii=False, indent=2))


class LTXDesktopClearGPUNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING")
    RETURN_NAMES = ("config", "status_json")
    FUNCTION = "clear"
    CATEGORY = "LTX Desktop/System"

    def clear(self, config: dict):
        next_config = _clone_config(config)
        _start_launcher_if_needed(next_config)
        result = _json_request(
            "POST",
            f"{_base_url(next_config)}/api/system/clear-gpu",
            {},
            timeout=120,
        )
        return (next_config, json.dumps(result, ensure_ascii=False, indent=2))


class LTXDesktopGenerateImageNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "aspect_ratio": (list(IMAGE_ASPECT_RATIOS.keys()),),
                "long_edge": ("INT", {"default": 2048, "min": 512, "max": 4096, "step": 64}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "num_steps": ("INT", {"default": 28, "min": 1, "max": 50, "step": 1}),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 8, "step": 1}),
                "seed_mode": (_choice_keys(SEED_MODE_LABELS),),
                "seed": ("INT", {"default": 123456789, "min": 0, "max": 2147483646, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "image_paths_json")
    FUNCTION = "generate"
    CATEGORY = "LTX Desktop"

    def generate(
        self,
        config: dict,
        prompt: str,
        aspect_ratio: str,
        long_edge: int,
        width: int,
        height: int,
        num_steps: int,
        num_images: int,
        seed_mode: str,
        seed: int,
    ):
        if not str(prompt or "").strip():
            raise RuntimeError("prompt 不能为空。请在 TY LTX Desktop Generate Image 节点顶部填写图片提示词。")

        # 根据比例和长边计算宽高
        ratio = IMAGE_ASPECT_RATIOS.get(aspect_ratio)
        
        if ratio is None:
            # 自定义模式，使用手动输入的宽高
            pass
        else:
            # 使用比例和长边计算
            ratio_w, ratio_h = ratio
            
            # 确定哪个是长边
            if ratio_w >= ratio_h:
                # 横屏或正方形，宽度是长边
                width = long_edge
                height = int(long_edge * ratio_h / ratio_w)
            else:
                # 竖屏，高度是长边
                height = long_edge
                width = int(long_edge * ratio_w / ratio_h)
            
            # 确保尺寸是32的倍数（AI模型通常需要）
            width = (width // 32) * 32
            height = (height // 32) * 32

        _prepare_runtime(config)
        _reset_state(config)
        
        # 处理种子模式
        actual_seed = seed
        if _normalize_choice(seed_mode, SEED_MODE_LABELS) == "random":
            import random
            actual_seed = random.randint(0, 2147483646)
        
        payload = {
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
            "numSteps": int(num_steps),
            "numImages": int(num_images),
            "seed": int(actual_seed),
        }
        data = _json_request(
            "POST",
            f"{_base_url(config)}/api/generate-image",
            payload,
            timeout=int(config.get("request_timeout_s", 1800)),
        )
        image_paths = data.get("image_paths") or []
        if not image_paths:
            raise RuntimeError("LTX Desktop 没有返回图像路径。")

        tensors = [_load_remote_image_tensor(config, str(path)) for path in image_paths]
        return (torch.cat(tensors, dim=0), json.dumps(image_paths, ensure_ascii=False))


class LTXDesktopGenerateVideoNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (_choice_keys(VIDEO_RESOLUTION_LABELS),),
                "aspect_ratio": (_choice_keys(ASPECT_RATIO_LABELS),),
                "duration": ("FLOAT", {"default": 5.0, "min": 1.0, "max": 30.0, "step": 0.5}),
                "fps": (["24", "25", "30", "48", "60"],),
                "seed_mode": (_choice_keys(SEED_MODE_LABELS),),
                "seed": ("INT", {"default": 123456789, "min": 0, "max": 2147483646, "step": 1}),
                "camera_motion": (_choice_keys(CAMERA_MOTION_LABELS),),
                "audio": ("BOOLEAN", {"default": True}),
                "negative_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "low quality, blurry, noisy, static noise, distorted",
                    },
                ),
                "audio_path": ("STRING", {"default": ""}),
                "inference_steps": ("INT", {"default": 8, "min": 1, "max": 50, "step": 1}),
                "lora_path": ("STRING", {"default": ""}),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "model_path": ("STRING", {"default": ""}),
                "keyframe_strengths": ("STRING", {"default": ""}),
                "keyframe_times": ("STRING", {"default": ""}),
            },
            "optional": {
                "image": ("IMAGE",),
                "start_frame": ("IMAGE",),
                "end_frame": ("IMAGE",),
                "ref_audio": ("AUDIO",),
                "keyframe_images": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "generate"
    CATEGORY = "LTX Desktop"

    def generate(
        self,
        config: dict,
        prompt: str,
        resolution: str,
        aspect_ratio: str,
        duration: float,
        fps: str,
        seed_mode: str,
        seed: int,
        camera_motion: str,
        audio: bool,
        negative_prompt: str,
        audio_path: str,
        inference_steps: int,
        lora_path: str,
        lora_strength: float,
        model_path: str,
        keyframe_strengths: str,
        keyframe_times: str,
        image: torch.Tensor | None = None,
        start_frame: torch.Tensor | None = None,
        end_frame: torch.Tensor | None = None,
        ref_audio=None,
        keyframe_images: torch.Tensor | None = None,
    ):
        if not str(prompt or "").strip():
            raise RuntimeError("prompt 不能为空。请在 LTX Desktop Generate Video 节点顶部填写视频提示词。")

        if _looks_like_legacy_generate_video_binding(
            camera_motion,
            audio,
            audio_path,
            inference_steps,
        ):
            raise RuntimeError(
                "This Generate Video node looks like an old workflow instance with misaligned fields. "
                "Please recreate the node or re-import the updated workflow, then set camera_motion and inference_steps again."
            )
        if int(inference_steps) < 1:
            raise RuntimeError("inference_steps must be >= 1.")

        _prepare_runtime(config)
        _reset_state(config)

        uploaded_audio_path = None
        if ref_audio is not None:
            uploaded_audio_path = _upload_audio_input(config, ref_audio, "audio")
        elif audio_path.strip():
            uploaded_audio_path = _upload_local_file(config, audio_path.strip(), "audio")

        image_path = None
        start_frame_path = None
        end_frame_path = None
        keyframe_paths = None
        keyframe_strengths = None
        keyframe_times_payload = None

        # 处理多关键帧
        if keyframe_images is not None and keyframe_images.shape[0] > 1:
            frame_count = int(keyframe_images.shape[0])
            keyframe_paths = []
            parsed_strengths = _parse_number_list(keyframe_strengths, float)
            parsed_times = _parse_number_list(keyframe_times, float)
            if parsed_strengths and len(parsed_strengths) not in (1, frame_count):
                raise RuntimeError(f"keyframe_strengths 数量需要为 1 或 {frame_count}。")
            if parsed_times and len(parsed_times) not in (1, frame_count):
                raise RuntimeError(f"keyframe_times 数量需要为 1 或 {frame_count}。")
            keyframe_strengths = []
            keyframe_times_payload = []
            for i in range(frame_count):
                frame = keyframe_images[i:i+1]
                path = _upload_tensor(config, frame, f"keyframe_{i}")
                keyframe_paths.append(path)
                # 自动计算强度：首尾帧强度高，中间帧强度递减
                if parsed_strengths:
                    keyframe_strengths.append(
                        float(parsed_strengths[i if len(parsed_strengths) > 1 else 0])
                    )
                elif i == 0 or i == frame_count - 1:
                    keyframe_strengths.append(1.0)
                else:
                    keyframe_strengths.append(0.7)
                if parsed_times:
                    keyframe_times_payload.append(
                        float(parsed_times[i if len(parsed_times) > 1 else 0])
                    )
        elif start_frame is not None and end_frame is not None:
            start_frame_path = _upload_tensor(config, start_frame, "start_frame")
            end_frame_path = _upload_tensor(config, end_frame, "end_frame")
        elif start_frame is not None:
            image_path = _upload_tensor(config, start_frame, "reference_frame")
        elif image is not None:
            image_path = _upload_tensor(config, image, "reference_image")

        resolved_lora_path = _resolve_lora_path(config, lora_path, str(config.get("lora_dir") or ""))

        payload = {
            "prompt": prompt,
            "resolution": _normalize_choice(resolution, VIDEO_RESOLUTION_LABELS),
            "model": "ltx-2",
            "cameraMotion": _normalize_choice(camera_motion, CAMERA_MOTION_LABELS),
            "negativePrompt": negative_prompt,
            "duration": str(duration),
            "fps": str(fps),
            "seedMode": _normalize_choice(seed_mode, SEED_MODE_LABELS),
            "seed": int(seed),
            "audio": "true" if audio else "false",
            "imagePath": image_path,
            "audioPath": uploaded_audio_path,
            "startFramePath": start_frame_path,
            "endFramePath": end_frame_path,
            "aspectRatio": _normalize_choice(aspect_ratio, ASPECT_RATIO_LABELS),
            "inferenceSteps": int(inference_steps),
            "loraPath": resolved_lora_path if resolved_lora_path else None,
            "loraStrength": float(lora_strength),
            "modelPath": model_path.strip() if model_path.strip() else None,
        }

        # 添加多关键帧参数
        if keyframe_paths:
            payload["keyframePaths"] = keyframe_paths
            payload["keyframeStrengths"] = keyframe_strengths
            if keyframe_times_payload:
                payload["keyframeTimes"] = keyframe_times_payload

        data = _json_request(
            "POST",
            f"{_base_url(config)}/api/generate",
            payload,
            timeout=int(config.get("request_timeout_s", 1800)),
        )
        video_path = data.get("video_path")
        if not video_path:
            raise RuntimeError("LTX Desktop 没有返回视频路径。")
        return (str(video_path),)


class LTXDesktopHistoryNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "limit": ("INT", {"default": 20, "min": 1, "max": 1000, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("latest_path", "history_json")
    FUNCTION = "fetch"
    CATEGORY = "LTX Desktop"

    def fetch(self, config: dict, limit: int):
        history = _fetch_history_items(config, limit)
        latest = history[0]["fullpath"] if history else ""
        return (latest, json.dumps(history, ensure_ascii=False, indent=2))


class LTXDesktopHistoryItemNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "limit": ("INT", {"default": 50, "min": 1, "max": 1000, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("path", "type", "item_json")
    FUNCTION = "pick"
    CATEGORY = "LTX Desktop/History"

    def pick(self, config: dict, index: int, limit: int):
        history = _fetch_history_items(config, limit)
        if index < 0 or index >= len(history):
            raise RuntimeError(f"历史资产索引越界: {index}, 当前只有 {len(history)} 项。")
        item = history[index]
        return (
            str(item.get("fullpath", "")),
            str(item.get("type", "")),
            json.dumps(item, ensure_ascii=False, indent=2),
        )


class LTXDesktopLoadHistoryImageNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "limit": ("INT", {"default": 50, "min": 1, "max": 1000, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "path", "item_json")
    FUNCTION = "load"
    CATEGORY = "LTX Desktop/History"

    def load(self, config: dict, index: int, limit: int):
        history = _fetch_history_items(config, limit)
        if index < 0 or index >= len(history):
            raise RuntimeError(f"历史资产索引越界: {index}, 当前只有 {len(history)} 项。")
        item = history[index]
        if item.get("type") != "image":
            raise RuntimeError(f"第 {index} 项不是图片，而是 {item.get('type')}.")
        path = str(item.get("fullpath", ""))
        image = _load_remote_image_tensor(config, path)
        return (image, path, json.dumps(item, ensure_ascii=False, indent=2))


class LTXDesktopSaveVideoNode:
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "video_path": ("STRING", {"default": ""}),
                "filename_prefix": ("STRING", {"default": "ltx_video"}),
                "target_dir": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_video_path",)
    FUNCTION = "save"
    CATEGORY = "LTX Desktop/Output"

    def save(self, config: dict, video_path: str, filename_prefix: str, target_dir: str):
        src = Path(_resolve_video_reference(config, video_path)).expanduser()
        if not src.exists() or not src.is_file():
            raise RuntimeError(f"找不到视频文件: {src}")

        ext = src.suffix or ".mp4"
        base_name = _make_safe_video_name(filename_prefix, ext)

        comfy_output_dir_str = _get_comfyui_output_dir().strip()
        comfy_dst = None
        if comfy_output_dir_str:
            comfy_output_dir = Path(comfy_output_dir_str).expanduser()
            comfy_output_dir.mkdir(parents=True, exist_ok=True)
            comfy_dst = comfy_output_dir / base_name
            shutil.copy2(src, comfy_dst)

        target_dir_str = target_dir.strip()
        primary_dst = comfy_dst
        if target_dir_str:
            user_dir = Path(target_dir_str).expanduser()
            user_dir.mkdir(parents=True, exist_ok=True)
            user_dst = user_dir / base_name
            if comfy_dst is None or user_dst.resolve() != comfy_dst.resolve():
                shutil.copy2(src, user_dst)
            primary_dst = user_dst
        elif primary_dst is None:
            config_dir_str = str(config.get("output_dir", "") or "").strip()
            if config_dir_str:
                config_dir = Path(config_dir_str).expanduser()
                config_dir.mkdir(parents=True, exist_ok=True)
                config_dst = config_dir / base_name
                shutil.copy2(src, config_dst)
                primary_dst = config_dst
            else:
                fallback_dst = src.parent / base_name
                if fallback_dst.resolve() != src.resolve():
                    shutil.copy2(src, fallback_dst)
                primary_dst = fallback_dst

        preview_dst = comfy_dst or primary_dst
        ui_entry = _build_comfyui_video_ui_entry(preview_dst)
        if ui_entry is not None:
            return {
                "ui": {
                    "images": [ui_entry],
                    "animated": (True,),
                },
                "result": (str(primary_dst),),
            }
        return (str(primary_dst),)


class LTXDesktopListLorasNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "lora_dir": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("loras_json",)
    FUNCTION = "list_loras"
    CATEGORY = "LTX Desktop/Debug"

    def list_loras(self, config: dict, lora_dir: str):
        data = _fetch_loras_data(config, lora_dir)
        return (json.dumps(data, ensure_ascii=False, indent=2),)


class LTXDesktopSetLoraPathNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "lora_path": ("STRING", {"default": ""}),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "lora_dir": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING", "FLOAT")
    RETURN_NAMES = ("lora_path", "lora_strength")
    FUNCTION = "set_lora"
    CATEGORY = "LTX Desktop/Debug"

    def set_lora(self, config: dict, lora_path: str, lora_strength: float, lora_dir: str):
        resolved = _resolve_lora_path(config, lora_path, lora_dir)
        return (resolved, float(lora_strength))


class LTXDesktopSelectLoraNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "lora_dir": ("STRING", {"default": ""}),
                "lora_name": ("STRING", {"default": ""}),
                "lora_strength": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "FLOAT", "STRING")
    RETURN_NAMES = ("lora_path", "lora_strength", "selected_name")
    FUNCTION = "select"
    CATEGORY = "LTX Desktop/LoRA"

    def select(self, config: dict, lora_dir: str, lora_name: str, lora_strength: float):
        selected_name = _normalize_lora_choice(lora_name)
        if not selected_name:
            return ("", float(lora_strength), "")
        resolved = _resolve_lora_path(config, selected_name, lora_dir)
        return (resolved, float(lora_strength), selected_name)


class LTXDesktopLowVramModeNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "enabled": ("BOOLEAN", {"default": False}),
                "apply_now": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING")
    RETURN_NAMES = ("config", "status_json")
    FUNCTION = "set_mode"
    CATEGORY = "LTX Desktop/System"

    def set_mode(self, config: dict, enabled: bool, apply_now: bool):
        next_config = _clone_config(config)
        next_config["low_vram_mode"] = bool(enabled)
        next_config["low_vram_mode_locked"] = True
        
        if apply_now:
            _start_launcher_if_needed(next_config)
            result = _json_request(
                "POST",
                f"{_base_url(next_config)}/api/system/low-vram-mode",
                {"enabled": bool(enabled)},
                timeout=30,
            )
            supported, ignored = _sync_vram_limit_with_low_vram_policy(next_config, timeout=30)
            if supported is not None:
                result["vramLimitSupported"] = supported
            if ignored:
                result["vramLimitIgnored"] = True
                result["vramLimitEffective"] = ""
            return (next_config, json.dumps(result, ensure_ascii=False, indent=2))

        result = {"enabled": bool(enabled), "applied": False}
        if _is_low_vram_mode_requested(next_config) and bool(next_config.get("vram_limit_locked")):
            result["vramLimitIgnored"] = True
            result["vramLimitEffective"] = ""
        return (next_config, json.dumps(result, ensure_ascii=False))


class LTXDesktopSetVramLimitNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "vram_limit_gb": ("STRING", {"default": ""}),
                "apply_now": ("BOOLEAN", {"default": True}),
                "low_vram_mode": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING", "STRING")
    RETURN_NAMES = ("config", "vram_limit_gb", "status_json")
    FUNCTION = "apply"
    CATEGORY = "LTX Desktop/System"

    def apply(self, config: dict, vram_limit_gb: str, apply_now: bool, low_vram_mode: bool):
        next_config = _clone_config(config)
        normalized = _normalize_vram_limit_value(vram_limit_gb)
        next_config["vram_limit"] = normalized
        next_config["vram_limit_locked"] = True
        next_config["low_vram_mode"] = bool(low_vram_mode)
        next_config["low_vram_mode_locked"] = True

        status = {
            "vramLimit": normalized,
            "applied": False,
            "supported": None,
            "lowVramMode": bool(low_vram_mode),
        }
        if apply_now:
            _start_launcher_if_needed(next_config)
            result = _json_request(
                "POST",
                f"{_base_url(next_config)}/api/system/low-vram-mode",
                {"enabled": bool(low_vram_mode)},
                timeout=30,
            )
            status["lowVramModeApplied"] = bool(result.get("enabled", low_vram_mode))
            supported, ignored = _sync_vram_limit_with_low_vram_policy(next_config, timeout=30)
            if supported is not None:
                status["supported"] = supported
            if ignored:
                _mark_vram_limit_ignored(status)
            elif supported is not False:
                status["applied"] = True
        elif _is_low_vram_mode_requested(next_config):
            _mark_vram_limit_ignored(status)

        return (next_config, normalized, json.dumps(status, ensure_ascii=False, indent=2))


class LTXDesktopGetVramLimitNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("LTX_DESKTOP_CONFIG",)}}

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING", "STRING")
    RETURN_NAMES = ("config", "vram_limit_gb", "status_json")
    FUNCTION = "fetch"
    CATEGORY = "LTX Desktop/System"

    def fetch(self, config: dict):
        next_config = _clone_config(config)
        _start_launcher_if_needed(next_config)

        try:
            fallback_value = _normalize_vram_limit_value(next_config.get("vram_limit", ""))
        except Exception:
            fallback_value = str(next_config.get("vram_limit") or "").strip()
        try:
            data = _get_vram_limit(next_config, timeout=30)
            value = _normalize_vram_limit_value(data.get("vramLimit", ""))
            next_config["vram_limit"] = value
            next_config["vram_limit_locked"] = True
            status = dict(data)
            status["vramLimit"] = value
            status["supported"] = True
            if _is_low_vram_mode_effective(next_config, timeout=10):
                _mark_vram_limit_ignored(status)
            return (next_config, value, json.dumps(status, ensure_ascii=False, indent=2))
        except Exception as exc:
            if not _is_missing_route_error(exc):
                raise
            status = {
                "vramLimit": fallback_value,
                "supported": False,
                "message": str(exc),
            }
            if _is_low_vram_mode_requested(next_config):
                _mark_vram_limit_ignored(status)
            return (next_config, fallback_value, json.dumps(status, ensure_ascii=False, indent=2))


class LTXDesktopListModelsNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "models_dir": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("models_json",)
    FUNCTION = "list_models"
    CATEGORY = "LTX Desktop/Models"

    def list_models(self, config: dict, models_dir: str):
        _start_launcher_if_needed(config)
        base_url = _base_url(config)
        
        params = {}
        if models_dir.strip():
            params["dir"] = models_dir.strip()
        
        query = urllib.parse.urlencode(params) if params else ""
        url = f"{base_url}/api/models"
        if query:
            url = f"{url}?{query}"
        
        data = _json_request("GET", url, timeout=30)
        return (json.dumps(data, ensure_ascii=False, indent=2),)


class LTXDesktopGetOutputDirNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("LTX_DESKTOP_CONFIG",)}}

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING", "STRING")
    RETURN_NAMES = ("config", "output_dir", "status_json")
    FUNCTION = "fetch"
    CATEGORY = "LTX Desktop/System"

    def fetch(self, config: dict):
        next_config = _clone_config(config)
        _start_launcher_if_needed(next_config)
        data = _json_request("GET", f"{_base_url(next_config)}/api/system/get-dir", timeout=30)
        directory = str(data.get("directory") or "").strip()
        if directory:
            next_config["output_dir"] = directory
        return (next_config, directory, json.dumps(data, ensure_ascii=False, indent=2))


class LTXDesktopBrowseOutputDirNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("LTX_DESKTOP_CONFIG",)}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("selected_dir", "status_json")
    FUNCTION = "browse"
    CATEGORY = "LTX Desktop/System"

    def browse(self, config: dict):
        _start_launcher_if_needed(config)
        data = _json_request("GET", f"{_base_url(config)}/api/system/browse-dir", timeout=120)
        directory = str(data.get("directory") or "").strip()
        return (directory, json.dumps(data, ensure_ascii=False, indent=2))


class LTXDesktopSetLoraDirNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "lora_dir": ("STRING", {"default": ""}),
                "apply_now": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("LTX_DESKTOP_CONFIG", "STRING", "STRING")
    RETURN_NAMES = ("config", "lora_dir", "status_json")
    FUNCTION = "apply"
    CATEGORY = "LTX Desktop/Debug"

    def apply(self, config: dict, lora_dir: str, apply_now: bool):
        next_config = _clone_config(config)
        next_config["lora_dir"] = lora_dir.strip()
        if apply_now:
            _start_launcher_if_needed(next_config)
            data = _json_request(
                "POST",
                f"{_base_url(next_config)}/api/lora-dir",
                {"loraDir": next_config["lora_dir"]},
                timeout=30,
            )
        else:
            data = {"status": "success", "loraDir": next_config["lora_dir"], "applied": False}
        return (next_config, next_config["lora_dir"], json.dumps(data, ensure_ascii=False, indent=2))


class LTXDesktopGetLoraDirNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": ("LTX_DESKTOP_CONFIG",)}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("lora_dir", "status_json")
    FUNCTION = "fetch"
    CATEGORY = "LTX Desktop/Debug"

    def fetch(self, config: dict):
        _start_launcher_if_needed(config)
        data = _json_request("GET", f"{_base_url(config)}/api/lora-dir", timeout=30)
        directory = str(data.get("loraDir") or "").strip()
        return (directory, json.dumps(data, ensure_ascii=False, indent=2))


class LTXDesktopDeleteFileNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "file_path": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status_json",)
    FUNCTION = "delete"
    CATEGORY = "LTX Desktop/System"

    def delete(self, config: dict, file_path: str):
        _prepare_runtime(config)
        target = str(file_path or "").strip()
        if not target:
            raise RuntimeError("file_path 不能为空。")
        filename = Path(target).name
        data = _json_request(
            "POST",
            f"{_base_url(config)}/api/system/delete-file",
            {"filename": filename},
            timeout=30,
        )
        return (json.dumps(data, ensure_ascii=False, indent=2),)


class LTXDesktopGenerateBatchVideoNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "start_frames": ("IMAGE",),
                "end_frames": ("IMAGE",),
                "prompts": ("STRING", {"multiline": True, "default": ""}),
                "durations": ("STRING", {"default": "5"}),
                "resolution": (_choice_keys(VIDEO_RESOLUTION_LABELS),),
                "aspect_ratio": (_choice_keys(ASPECT_RATIO_LABELS),),
                "fps": (["24", "25", "30", "48", "60"],),
                "camera_motion": (_choice_keys(CAMERA_MOTION_LABELS),),
                "audio": ("BOOLEAN", {"default": False}),
                "negative_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "low quality, blurry, noisy, static noise, distorted",
                    },
                ),
                "background_audio_path": ("STRING", {"default": ""}),
                "lora_path": ("STRING", {"default": ""}),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "model_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "background_audio": ("AUDIO",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "generate"
    CATEGORY = "LTX Desktop"

    def generate(
        self,
        config: dict,
        start_frames: torch.Tensor,
        end_frames: torch.Tensor,
        prompts: str,
        durations: str,
        resolution: str,
        aspect_ratio: str,
        fps: str,
        camera_motion: str,
        audio: bool,
        negative_prompt: str,
        background_audio_path: str,
        lora_path: str,
        lora_strength: float,
        model_path: str,
        background_audio=None,
    ):
        _prepare_runtime(config)
        _reset_state(config)

        start_count = _get_image_batch_size(start_frames)
        end_count = _get_image_batch_size(end_frames)
        if start_count <= 0 or end_count <= 0:
            raise RuntimeError("start_frames 和 end_frames 都不能为空。")
        if start_count != end_count:
            raise RuntimeError(f"start_frames / end_frames 数量不一致: {start_count} vs {end_count}")

        prompts_list = _parse_text_list(prompts)
        duration_values = _parse_number_list(durations, float) or [5.0]
        if prompts_list and len(prompts_list) not in (1, start_count):
            raise RuntimeError(f"prompts 行数需要为 1 或 {start_count}。")
        if duration_values and len(duration_values) not in (1, start_count):
            raise RuntimeError(f"durations 数量需要为 1 或 {start_count}。")

        segments = []
        for idx in range(start_count):
            start_path = _upload_tensor(config, _slice_image_batch(start_frames, idx), f"batch_start_{idx}")
            end_path = _upload_tensor(config, _slice_image_batch(end_frames, idx), f"batch_end_{idx}")
            prompt_text = prompts_list[idx if len(prompts_list) > 1 else 0] if prompts_list else ""
            duration_value = duration_values[idx if len(duration_values) > 1 else 0]
            segments.append(
                {
                    "startImage": start_path,
                    "endImage": end_path,
                    "prompt": prompt_text,
                    "duration": float(duration_value),
                }
            )

        uploaded_background_audio = None
        if background_audio is not None:
            uploaded_background_audio = _upload_audio_input(config, background_audio, "batch_bg_audio")
        elif background_audio_path.strip():
            uploaded_background_audio = _upload_local_file(
                config, background_audio_path.strip(), "batch_bg_audio"
            )

        resolved_lora_path = _resolve_lora_path(config, lora_path, str(config.get("lora_dir") or ""))

        payload = {
            "segments": segments,
            "resolution": _normalize_choice(resolution, VIDEO_RESOLUTION_LABELS),
            "aspectRatio": _normalize_choice(aspect_ratio, ASPECT_RATIO_LABELS),
            "negativePrompt": negative_prompt,
            "model": "ltx-2",
            "fps": str(fps),
            "audio": "true" if audio else "false",
            "cameraMotion": _normalize_choice(camera_motion, CAMERA_MOTION_LABELS),
            "modelPath": model_path.strip() if model_path.strip() else None,
            "loraPath": resolved_lora_path if resolved_lora_path else None,
            "loraStrength": float(lora_strength),
        }
        if uploaded_background_audio:
            payload["backgroundAudioPath"] = uploaded_background_audio

        data = _json_request(
            "POST",
            f"{_base_url(config)}/api/generate-batch",
            payload,
            timeout=int(config.get("request_timeout_s", 1800)),
        )
        video_path = data.get("video_path")
        if not video_path:
            raise RuntimeError("LTX Desktop 没有返回批量视频路径。")
        return (str(video_path),)


NODE_CLASS_MAPPINGS = {
    "LTXDesktopConfig": LTXDesktopConfigNode,
    "TYLTXDesktopConfig": LTXDesktopConfigNode,
    "LTXDesktopSetOutputDir": LTXDesktopSetOutputDirNode,
    "TYLTXDesktopSetOutputDir": LTXDesktopSetOutputDirNode,
    "LTXDesktopGetOutputDir": LTXDesktopGetOutputDirNode,
    "TYLTXDesktopGetOutputDir": LTXDesktopGetOutputDirNode,
    "LTXDesktopBrowseOutputDir": LTXDesktopBrowseOutputDirNode,
    "TYLTXDesktopBrowseOutputDir": LTXDesktopBrowseOutputDirNode,
    "LTXDesktopSwitchGPU": LTXDesktopSwitchGPUNode,
    "TYLTXDesktopSwitchGPU": LTXDesktopSwitchGPUNode,
    "LTXDesktopClearGPU": LTXDesktopClearGPUNode,
    "TYLTXDesktopClearGPU": LTXDesktopClearGPUNode,
    "LTXDesktopGenerateImage": LTXDesktopGenerateImageNode,
    "TYLTXDesktopGenerateImage": LTXDesktopGenerateImageNode,
    "LTXDesktopGenerateVideo": LTXDesktopGenerateVideoNode,
    "TYLTXDesktopGenerateVideo": LTXDesktopGenerateVideoNode,
    "LTXDesktopHistory": LTXDesktopHistoryNode,
    "TYLTXDesktopHistory": LTXDesktopHistoryNode,
    "LTXDesktopHistoryItem": LTXDesktopHistoryItemNode,
    "TYLTXDesktopHistoryItem": LTXDesktopHistoryItemNode,
    "LTXDesktopLoadHistoryImage": LTXDesktopLoadHistoryImageNode,
    "TYLTXDesktopLoadHistoryImage": LTXDesktopLoadHistoryImageNode,
    "LTXDesktopSaveVideo": LTXDesktopSaveVideoNode,
    "TYLTXDesktopSaveVideo": LTXDesktopSaveVideoNode,
    "LTXDesktopListLoras": LTXDesktopListLorasNode,
    "TYLTXDesktopListLoras": LTXDesktopListLorasNode,
    "LTXDesktopSetLoraPath": LTXDesktopSetLoraPathNode,
    "TYLTXDesktopSetLoraPath": LTXDesktopSetLoraPathNode,
    "LTXDesktopSelectLora": LTXDesktopSelectLoraNode,
    "TYLTXDesktopSelectLora": LTXDesktopSelectLoraNode,
    "LTXDesktopSetLoraDir": LTXDesktopSetLoraDirNode,
    "TYLTXDesktopSetLoraDir": LTXDesktopSetLoraDirNode,
    "LTXDesktopGetLoraDir": LTXDesktopGetLoraDirNode,
    "TYLTXDesktopGetLoraDir": LTXDesktopGetLoraDirNode,
    "TYLTXDesktopSetVramLimit": LTXDesktopSetVramLimitNode,
    "TYLTXDesktopGetVramLimit": LTXDesktopGetVramLimitNode,
    "LTXDesktopListModels": LTXDesktopListModelsNode,
    "TYLTXDesktopListModels": LTXDesktopListModelsNode,
    "LTXDesktopDeleteFile": LTXDesktopDeleteFileNode,
    "TYLTXDesktopDeleteFile": LTXDesktopDeleteFileNode,
    "LTXDesktopGenerateBatchVideo": LTXDesktopGenerateBatchVideoNode,
    "TYLTXDesktopGenerateBatchVideo": LTXDesktopGenerateBatchVideoNode,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDesktopConfig": "LTX Desktop Config 配置",
    "TYLTXDesktopConfig": "TY LTX Desktop Config 配置",
    "LTXDesktopSetOutputDir": "LTX Desktop Set Output Dir 输出目录",
    "TYLTXDesktopSetOutputDir": "TY LTX Desktop Set Output Dir 输出目录",
    "LTXDesktopSwitchGPU": "LTX Desktop Switch GPU 切换显卡",
    "TYLTXDesktopSwitchGPU": "TY LTX Desktop Switch GPU 切换显卡",
    "LTXDesktopClearGPU": "LTX Desktop Clear GPU 清理显存",
    "TYLTXDesktopClearGPU": "TY LTX Desktop Clear GPU 清理显存",
    "LTXDesktopGenerateImage": "LTX Desktop Generate Image 图片生成",
    "TYLTXDesktopGenerateImage": "TY LTX Desktop Generate Image 图片生成",
    "LTXDesktopGenerateVideo": "LTX Desktop Generate Video 视频生成",
    "TYLTXDesktopGenerateVideo": "TY LTX Desktop Generate Video 视频生成",
    "LTXDesktopHistory": "LTX Desktop History 历史记录",
    "TYLTXDesktopHistory": "TY LTX Desktop History 历史记录",
    "LTXDesktopHistoryItem": "LTX Desktop History Item 历史项",
    "TYLTXDesktopHistoryItem": "TY LTX Desktop History Item 历史项",
    "LTXDesktopLoadHistoryImage": "LTX Desktop Load History Image 历史图片",
    "TYLTXDesktopLoadHistoryImage": "TY LTX Desktop Load History Image 历史图片",
    "LTXDesktopSaveVideo": "LTX Desktop Save Video 保存视频",
    "TYLTXDesktopSaveVideo": "TY LTX Desktop Save Video 保存视频",
    "LTXDesktopListLoras": "[Debug] LTX Desktop List LoRAs LoRA列表",
    "TYLTXDesktopListLoras": "[Debug] TY LTX Desktop List LoRAs LoRA列表",
    "LTXDesktopSetLoraPath": "[Debug] LTX Desktop Set LoRA Path 设置LoRA",
    "TYLTXDesktopSetLoraPath": "[Debug] TY LTX Desktop Set LoRA Path 设置LoRA",
    "LTXDesktopSelectLora": "LTX Desktop Select LoRA 下拉选择LoRA",
    "TYLTXDesktopSelectLora": "TY LTX Desktop Select LoRA 下拉选择LoRA",
    "LTXDesktopListModels": "LTX Desktop List Models 模型列表",
    "TYLTXDesktopListModels": "TY LTX Desktop List Models 模型列表",
}
NODE_DISPLAY_NAME_MAPPINGS.update(
    {
        "LTXDesktopGetOutputDir": "LTX Desktop Get Output Dir 当前输出目录",
        "TYLTXDesktopGetOutputDir": "TY LTX Desktop Get Output Dir 当前输出目录",
        "LTXDesktopBrowseOutputDir": "LTX Desktop Browse Output Dir 选择输出目录",
        "TYLTXDesktopBrowseOutputDir": "TY LTX Desktop Browse Output Dir 选择输出目录",
        "LTXDesktopSetLoraDir": "[Debug] LTX Desktop Set LoRA Dir LoRA目录",
        "TYLTXDesktopSetLoraDir": "[Debug] TY LTX Desktop Set LoRA Dir LoRA目录",
        "LTXDesktopGetLoraDir": "[Debug] LTX Desktop Get LoRA Dir 当前LoRA目录",
        "TYLTXDesktopGetLoraDir": "[Debug] TY LTX Desktop Get LoRA Dir 当前LoRA目录",
        "LTXDesktopDeleteFile": "LTX Desktop Delete File 删除输出文件",
        "TYLTXDesktopDeleteFile": "TY LTX Desktop Delete File 删除输出文件",
        "LTXDesktopGenerateBatchVideo": "LTX Desktop Generate Batch Video 批量转场视频",
        "TYLTXDesktopGenerateBatchVideo": "TY LTX Desktop Generate Batch Video 批量转场视频",
    }
)

NODE_DISPLAY_NAME_MAPPINGS.update(
    {
        "TYLTXDesktopSetVramLimit": "TY LTX Desktop Set VRAM Limit",
        "TYLTXDesktopGetVramLimit": "TY LTX Desktop Get VRAM Limit",
    }
)


try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.post("/ty_ltx_bridge/loras")
    async def ty_ltx_bridge_loras(request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        config = payload.get("config") or {}
        lora_dir = str(payload.get("lora_dir") or "")
        try:
            data = _fetch_loras_data(config, lora_dir)
            return web.json_response(data)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
except Exception:
    pass
