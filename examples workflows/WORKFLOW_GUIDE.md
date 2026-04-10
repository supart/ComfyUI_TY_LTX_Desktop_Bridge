# Workflow Guide

## 1. `t2v_lora_workflow.json`

Use this when you want a simple text-to-video workflow with LoRA dropdown selection.

Recommended when:

- You already have a LoRA directory configured in LTX Desktop
- You want the shortest day-to-day T2V workflow
- You optionally use `rgthree-comfy` for display/debug nodes

## 2. `qwentts_i2v_workflow.json`

Use this when you want a QwenTTS-driven talking portrait or digital-human workflow.

Required extra nodes:

- `qwen3-tts-comfyui`
- `comfyui-easy-use`

Bundled input:

- `input_assets/cat_announcer.png`

## 3. `image_to_video_i2v_workflow.json`

Use this when you want the workflow to first generate an image, then send that image into LTX video generation.

This is the most self-contained I2V example in the repo.

## 4. `start_end_i2v_workflow.json`

Use this when you want a start-frame / end-frame interpolation workflow.

Bundled inputs:

- `input_assets/racecar_start.jpg`
- `input_assets/racecar_end.jpg`

## General Import Notes

- Import the JSON into ComfyUI.
- Fill your own `launcher_root` if you want automatic desktop startup.
- Public examples default to `auto_start = true`.
- Copy bundled input assets into the ComfyUI `input` directory if the workflow uses `LoadImage`.
