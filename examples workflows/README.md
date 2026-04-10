# Example Workflows

This folder contains the maintained public example workflows for `ComfyUI_TY_LTX_Desktop_Bridge`.

## Workflow Files

- `t2v_lora_workflow.json`
  - Text-to-video with LoRA dropdown selection
  - Optional dependency: `rgthree-comfy`

- `qwentts_i2v_workflow.json`
  - QwenTTS voice + portrait driven image-to-video workflow
  - Optional dependencies: `qwen3-tts-comfyui`, `comfyui-easy-use`

- `image_to_video_i2v_workflow.json`
  - Generate an image first, then turn it into video
  - Uses bridge nodes plus built-in ComfyUI nodes

- `start_end_i2v_workflow.json`
  - Start / end frame interpolation workflow
  - Uses bundled demo input assets

## Input Assets

Files in `input_assets/` are public demo inputs for the workflows:

- `cat_announcer.png`
- `racecar_start.jpg`
- `racecar_end.jpg`

Copy them into your ComfyUI `input` folder after importing the workflow, or replace them with your own media.

## Notes

- Public workflow JSON files do not contain hard-coded personal paths.
- Public preview images for the GitHub homepage are stored in `../assets/workflow_previews/`.
- If a node schema changed after plugin update, recreate the node or re-import the workflow JSON.
