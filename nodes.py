from __future__ import annotations

import base64
import io
import json
import os
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


def _base_url(config: dict) -> str:
    return config["base_url"].rstrip("/")


def _parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _can_connect(base_url: str, timeout: float = 2.0) -> bool:
    host, port = _parse_host_port(base_url)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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


def _start_launcher_if_needed(config: dict) -> None:
    base_url = _base_url(config)
    if _can_connect(base_url):
        return

    if not config.get("auto_start"):
        raise RuntimeError(
            f"LTX Desktop 后端未运行: {base_url}。请先启动官方桌面版或这个项目的 run.bat。"
        )

    launcher_root = str(config.get("launcher_root", "") or "").strip()
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

    _wait_for_server(config)


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


def _clone_config(config: dict) -> dict:
    return dict(config or {})


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
        health_timeout_s: int,
        request_timeout_s: int,
    ):
        config = {
            "base_url": base_url.strip(),
            "launcher_root": launcher_root.strip(),
            "auto_start": bool(auto_start),
            "output_dir": output_dir.strip(),
            "gpu_id": int(gpu_id),
            "clear_gpu_before_run": bool(clear_gpu_before_run),
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
                "preset": (list(IMAGE_PRESET_SIZES.keys()),),
                "width": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "num_steps": ("INT", {"default": 28, "min": 1, "max": 50, "step": 1}),
                "num_images": ("INT", {"default": 1, "min": 1, "max": 8, "step": 1}),
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
        preset: str,
        width: int,
        height: int,
        num_steps: int,
        num_images: int,
    ):
        if not str(prompt or "").strip():
            raise RuntimeError("prompt 不能为空。请在 TY LTX Desktop Generate Image 节点顶部填写图片提示词。")

        selected_size = IMAGE_PRESET_SIZES.get(preset)
        if selected_size is not None:
            width, height = selected_size

        _prepare_runtime(config)
        _reset_state(config)
        payload = {
            "prompt": prompt,
            "width": int(width),
            "height": int(height),
            "numSteps": int(num_steps),
            "numImages": int(num_images),
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
            },
            "optional": {
                "image": ("IMAGE",),
                "start_frame": ("IMAGE",),
                "end_frame": ("IMAGE",),
                "ref_audio": ("AUDIO",),
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
        image: torch.Tensor | None = None,
        start_frame: torch.Tensor | None = None,
        end_frame: torch.Tensor | None = None,
        ref_audio=None,
    ):
        if not str(prompt or "").strip():
            raise RuntimeError("prompt 不能为空。请在 LTX Desktop Generate Video 节点顶部填写视频提示词。")

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

        if start_frame is not None and end_frame is not None:
            start_frame_path = _upload_tensor(config, start_frame, "start_frame")
            end_frame_path = _upload_tensor(config, end_frame, "end_frame")
        elif start_frame is not None:
            image_path = _upload_tensor(config, start_frame, "reference_frame")
        elif image is not None:
            image_path = _upload_tensor(config, image, "reference_image")

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
        }

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


class LTXDesktopUpscaleVideoNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config": ("LTX_DESKTOP_CONFIG",),
                "video_path": ("STRING", {"default": ""}),
                "resolution": (_choice_keys(UPSCALE_RESOLUTION_LABELS),),
                "prompt": (
                    "STRING",
                    {"multiline": True, "default": "high quality, detailed, 4k"},
                ),
                "strength": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "upscale"
    CATEGORY = "LTX Desktop"

    def upscale(
        self,
        config: dict,
        video_path: str,
        resolution: str,
        prompt: str,
        strength: float,
    ):
        _prepare_runtime(config)
        _reset_state(config)

        raw_video_path = video_path.strip()
        if not raw_video_path:
            raise RuntimeError("video_path 不能为空。")

        local_path = Path(raw_video_path).expanduser()
        if not local_path.exists() or not local_path.is_file():
            raise RuntimeError(f"找不到待超分视频: {local_path}")
        final_video_path = str(local_path)

        payload = {
            "video_path": final_video_path,
            "resolution": _normalize_choice(resolution, UPSCALE_RESOLUTION_LABELS),
            "prompt": prompt,
            "strength": float(strength),
        }
        data = _json_request(
            "POST",
            f"{_base_url(config)}/api/system/upscale-video",
            payload,
            timeout=int(config.get("request_timeout_s", 1800)),
        )
        result_path = data.get("video_path")
        if not result_path:
            raise RuntimeError("LTX Desktop 没有返回超分后视频路径。")
        return (str(result_path),)


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
        src = Path(video_path.strip()).expanduser()
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


NODE_CLASS_MAPPINGS = {
    "LTXDesktopConfig": LTXDesktopConfigNode,
    "TYLTXDesktopConfig": LTXDesktopConfigNode,
    "LTXDesktopSetOutputDir": LTXDesktopSetOutputDirNode,
    "TYLTXDesktopSetOutputDir": LTXDesktopSetOutputDirNode,
    "LTXDesktopSwitchGPU": LTXDesktopSwitchGPUNode,
    "TYLTXDesktopSwitchGPU": LTXDesktopSwitchGPUNode,
    "LTXDesktopClearGPU": LTXDesktopClearGPUNode,
    "TYLTXDesktopClearGPU": LTXDesktopClearGPUNode,
    "LTXDesktopGenerateImage": LTXDesktopGenerateImageNode,
    "TYLTXDesktopGenerateImage": LTXDesktopGenerateImageNode,
    "LTXDesktopGenerateVideo": LTXDesktopGenerateVideoNode,
    "TYLTXDesktopGenerateVideo": LTXDesktopGenerateVideoNode,
    "LTXDesktopUpscaleVideo": LTXDesktopUpscaleVideoNode,
    "TYLTXDesktopUpscaleVideo": LTXDesktopUpscaleVideoNode,
    "LTXDesktopHistory": LTXDesktopHistoryNode,
    "TYLTXDesktopHistory": LTXDesktopHistoryNode,
    "LTXDesktopHistoryItem": LTXDesktopHistoryItemNode,
    "TYLTXDesktopHistoryItem": LTXDesktopHistoryItemNode,
    "LTXDesktopLoadHistoryImage": LTXDesktopLoadHistoryImageNode,
    "TYLTXDesktopLoadHistoryImage": LTXDesktopLoadHistoryImageNode,
    "LTXDesktopSaveVideo": LTXDesktopSaveVideoNode,
    "TYLTXDesktopSaveVideo": LTXDesktopSaveVideoNode,
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
    "LTXDesktopUpscaleVideo": "LTX Desktop Upscale Video 视频超分",
    "TYLTXDesktopUpscaleVideo": "TY LTX Desktop Upscale Video 视频超分",
    "LTXDesktopHistory": "LTX Desktop History 历史记录",
    "TYLTXDesktopHistory": "TY LTX Desktop History 历史记录",
    "LTXDesktopHistoryItem": "LTX Desktop History Item 历史项",
    "TYLTXDesktopHistoryItem": "TY LTX Desktop History Item 历史项",
    "LTXDesktopLoadHistoryImage": "LTX Desktop Load History Image 历史图片",
    "TYLTXDesktopLoadHistoryImage": "TY LTX Desktop Load History Image 历史图片",
    "LTXDesktopSaveVideo": "LTX Desktop Save Video 保存视频",
    "TYLTXDesktopSaveVideo": "TY LTX Desktop Save Video 保存视频",
}
