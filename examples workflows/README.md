These files are GUI workflow JSON examples for ComfyUI.

Included workflows:

- `text_to_image.json`
- `text_to_video.json`
- `image_to_video.json`
- `upscale_video.json`
- `qwen3_tts_to_ltx_video.json`

Before running:

1. Import the workflow into ComfyUI.
2. Set `launcher_root` to the folder that contains `run.bat`.
3. Replace any placeholder local media paths if the workflow contains them.
4. Restart ComfyUI and re-import if you still see stale node fields from an older plugin version.

Notes:

- `text_to_image.json` and the helper image node inside `image_to_video.json` support image aspect presets plus custom width / height input.
- `image_to_video.json` uses a generated reference image by default.
- `upscale_video.json` generates a source video first, then upscales it.
