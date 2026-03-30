# ComfyUI TY LTX Desktop Bridge

Version: `1.0.0`

ComfyUI bridge plugin for LTX Desktop.

Use ComfyUI nodes to call a locally running LTX Desktop backend for image generation, video generation, audio-to-video, video upscale, history loading, and output preview/saving.

Core flow:

`ComfyUI node -> local LTX Desktop API -> image/video result`

## Features

- text to image
- text to video
- image to video
- start / end frame interpolation
- audio-to-video with ComfyUI `AUDIO` input or local audio file path
- video upscale
- fixed seed / random seed control
- image preset aspect ratios with custom width / height fallback
- GPU switching and output directory switching
- history asset loading
- video preview and save-to-output support

## Install

1. Make sure LTX Desktop can run on this machine.
2. Make sure the launcher project can start successfully with `run.bat`.
3. Copy this folder into:
   `ComfyUI/custom_nodes/ComfyUI_TY_LTX_Desktop_Bridge`
4. Restart ComfyUI.

## Main Nodes

- `TY LTX Desktop Config 配置`
- `TY LTX Desktop Generate Image 图片生成`
- `TY LTX Desktop Generate Video 视频生成`
- `TY LTX Desktop Upscale Video 视频超分`
- `TY LTX Desktop Save Video 保存视频`

## Usage Notes

Use `LTX Desktop Config` or `TY LTX Desktop Config` first.

Recommended values:

- `base_url`: `http://127.0.0.1:3000`
- `launcher_root`: the launcher project folder that contains `run.bat`
- `auto_start`: `true` if you want ComfyUI to launch `run.bat` automatically
- `output_dir`: leave blank to keep the current LTX Desktop output directory
- `gpu_id`: `-1` to avoid automatic GPU switching

## Image Presets

`TY LTX Desktop Generate Image` supports:

- `1:1 Square (1024x1024)`
- `16:9 Landscape (1280x720)`
- `9:16 Portrait (720x1280)`
- `Custom 自定义...`

When `Custom 自定义...` is selected, the node uses manual `width` and `height`.

## Seed Control

`TY LTX Desktop Generate Video` supports:

- `seed_mode`: fixed or random
- `seed`: numeric seed for repeatable generation

## Audio Input

`TY LTX Desktop Generate Video` supports two A2V input styles:

- `ref_audio`: native ComfyUI `AUDIO` input, including `Qwen3-TTS VoiceDesign`
- `audio_path`: local audio file path

If `ref_audio` is connected, it takes priority over `audio_path`.

## Example Workflows

Example GUI workflows are in [examples workflows](./examples%20workflows).

Included examples:

- `text_to_image.json`
- `text_to_video.json`
- `image_to_video.json`
- `upscale_video.json`
- `qwen3_tts_to_ltx_video.json`

These examples are meant as editable templates. After import, update `launcher_root` and any placeholder media paths to match your environment.
