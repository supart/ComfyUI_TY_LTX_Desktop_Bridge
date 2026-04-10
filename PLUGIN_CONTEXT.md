# Plugin Context

This file is a concise project memory for `ComfyUI_TY_LTX_Desktop_Bridge`.

## Purpose

This plugin lets ComfyUI drive a local LTX Desktop backend instead of using native ComfyUI generation nodes.

Primary flow:

`ComfyUI node -> local LTX Desktop HTTP API -> generated image/video -> save back into ComfyUI output`

## Target Frontend Compatibility

- Main target: `LTX2.3-1.0.4`
- Backward compatibility target: local `1.0.3` style deployments

## Key Compatibility Rules

- Preferred backend URL: `http://127.0.0.1:3000`
- Local fallback probing: `3000` and `3100`
- Launcher auto-discovery prefers the newest `LTX2.3-x.y.z` folder it can find
- `1.0.4` adds `/api/vram-limit`
- Older backends may not expose `/api/vram-limit`, so VRAM-limit nodes must degrade gracefully

## Main Node Groups

- Core: `Config`, `Generate Image`, `Generate Video`, `Save Video`
- System: output dir, GPU switch, GPU clear, `LowVramMode`, `SetVramLimit`, `GetVramLimit`
- LoRA: `SetLoraDir`, `GetLoraDir`, `ListLoras`, `SelectLora`, `SetLoraPath`
- Utility: history nodes, batch video, delete file

## Important UX Decisions

- Do not require the user to type full LoRA file paths for daily use
- `Select LoRA` should work from a configured `lora_dir` and dropdown list
- Low-VRAM tuning in `1.0.4` should be exposed as:
  1. `Set VRAM Limit`
- `Set VRAM Limit` now carries the `low_vram_mode` switch and is the single recommended VRAM-policy node for the branch
- `Config.low_vram_mode = true` is treated as an explicit runtime policy, not passive metadata
- If low-VRAM mode is effective, any configured `vram_limit_gb` should be reported as stored but ignored for that run

## Known Failure Pattern

If `TYLTXDesktopGenerateVideo` shows obviously wrong fields such as:

- `control_after_generate`
- `camera_motion = true`
- `audio_path = 8`
- `inference_steps = 0`

then the user is not using a valid current node instance. That means an old workflow or stale tab state is being interpreted by a newer plugin version.

Recommended fix:

1. Recreate the `Generate Video` node, or
2. Re-import the updated example workflow, or
3. Hard refresh ComfyUI, then reload the workflow

The runtime now also raises a clear error for this legacy misbinding pattern.

## Important Example Files

- `examples workflows/t2v_lora_workflow.json`
- `examples workflows/qwentts_i2v_workflow.json`
- `examples workflows/image_to_video_i2v_workflow.json`
- `examples workflows/start_end_i2v_workflow.json`

Bundled input assets:

- `examples workflows/input_assets/cat_announcer.png`
- `examples workflows/input_assets/racecar_start.jpg`
- `examples workflows/input_assets/racecar_end.jpg`

Example dependency note:

- `t2v_lora_workflow.json` uses `Display Any (rgthree)`
- `qwentts_i2v_workflow.json` uses QwenTTS-related custom nodes and `comfyui-easy-use`
- Public examples are packaged without hard-coded local paths
- Preview images for the README live in `assets/workflow_previews/`

## Live Deployment Note

The user often edits a workspace copy first, but ComfyUI actually loads the live plugin from:

`E:\ComfyUI\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI_TY_LTX_Desktop_Bridge`

When debugging "why it still behaves like the old version", always verify the live custom node directory and the currently running ComfyUI process.
