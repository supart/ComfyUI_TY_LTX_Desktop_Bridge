import { app } from "../../scripts/app.js";

const TARGETS = new Set(["LTXDesktopSelectLora", "TYLTXDesktopSelectLora"]);
const NODE_SIZE_PROPERTY = "__ty_lora_selector_size";

const PLACEHOLDERS = {
  waiting: "<leave lora_dir empty to use the desktop saved/default LoRA dir>",
  loading: "<loading LoRA list...>",
  empty: "<no LoRA files found in the active directory>",
  error: "<failed to read LoRA list, check lora_dir / base_url>",
};

const CONFIG_NODE_TYPES = new Set(["LTXDesktopConfig", "TYLTXDesktopConfig"]);

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name) ?? null;
}

function shouldSerializeWidget(widget) {
  return Boolean(widget) && widget.options?.serialize !== false;
}

function getHiddenLoraWidget(node) {
  return getWidget(node, "lora_name");
}

function getSelectorWidget(node) {
  return node?.__tyLoraSelectorWidget ?? null;
}

function isPlaceholderValue(value) {
  const raw = String(value || "").trim();
  return raw.startsWith("<") && raw.endsWith(">");
}

function isConfigNode(node) {
  if (!node) {
    return false;
  }
  if (CONFIG_NODE_TYPES.has(node.type)) {
    return true;
  }
  return Boolean(getWidget(node, "base_url") && getWidget(node, "launcher_root"));
}

function getUpstreamConfigNode(node, visited = new Set()) {
  if (!node || !node.graph || visited.has(node.id)) {
    return null;
  }
  visited.add(node.id);

  const configInput = node.inputs?.find((input) => input.name === "config");
  const linkId = configInput?.link;
  if (linkId == null) {
    return null;
  }
  const link = node.graph.links?.[linkId];
  if (!link) {
    return null;
  }

  const upstreamNode = node.graph.getNodeById(link.origin_id) ?? null;
  if (!upstreamNode) {
    return null;
  }
  if (isConfigNode(upstreamNode)) {
    return upstreamNode;
  }
  return getUpstreamConfigNode(upstreamNode, visited);
}

function getConfigNode(node) {
  if (isConfigNode(node)) {
    return node;
  }
  return getUpstreamConfigNode(node);
}

function getConfigValue(configNode, index, fallback = "") {
  if (!configNode) {
    return fallback;
  }
  const widget = configNode.widgets?.[index];
  if (widget?.value != null) {
    return widget.value;
  }
  const values = configNode.widgets_values;
  if (Array.isArray(values) && values[index] != null) {
    return values[index];
  }
  return fallback;
}

function normalizeBaseUrl(url) {
  return String(url || "").trim().replace(/\/+$/, "");
}

function collapseWidget(widget) {
  if (!widget || widget.__tyCollapsed) {
    return;
  }
  widget.__tyCollapsed = true;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
}

function normalizeNodeSize(size) {
  if (!Array.isArray(size) || size.length < 2) {
    return null;
  }
  const width = Number(size[0]);
  const height = Number(size[1]);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    return null;
  }
  return [Math.max(1, width), Math.max(1, height)];
}

function ensureNodeProperties(node) {
  if (!node.properties || typeof node.properties !== "object") {
    node.properties = {};
  }
  return node.properties;
}

function readPersistedNodeSize(node) {
  const raw = node?.properties?.[NODE_SIZE_PROPERTY];
  if (Array.isArray(raw)) {
    return normalizeNodeSize(raw);
  }
  if (raw && typeof raw === "object") {
    return normalizeNodeSize([raw.width, raw.height]);
  }
  return null;
}

function writePersistedNodeSize(node, size) {
  const normalized = normalizeNodeSize(size);
  if (!node || !normalized) {
    return null;
  }
  ensureNodeProperties(node)[NODE_SIZE_PROPERTY] = [...normalized];
  node.__tyPreferredSize = [...normalized];
  return normalized;
}

function getPreferredNodeSize(node) {
  const runtimeSize = normalizeNodeSize(node?.__tyPreferredSize);
  if (runtimeSize) {
    return runtimeSize;
  }
  const persistedSize = readPersistedNodeSize(node);
  if (persistedSize) {
    node.__tyPreferredSize = [...persistedSize];
    return persistedSize;
  }
  const currentSize = normalizeNodeSize(node?.size);
  if (currentSize) {
    writePersistedNodeSize(node, currentSize);
    return currentSize;
  }
  return null;
}

function enforcePreferredNodeSize(node, requestedSize) {
  const preferred = getPreferredNodeSize(node);
  const requested = normalizeNodeSize(requestedSize);
  if (!preferred) {
    return requested;
  }
  if (!requested) {
    return [...preferred];
  }
  return [
    Math.max(requested[0], preferred[0]),
    Math.max(requested[1], preferred[1]),
  ];
}

function applyPreferredNodeSize(node, requestedSize = null) {
  if (!node) {
    return null;
  }
  const nextSize = enforcePreferredNodeSize(
    node,
    requestedSize ?? normalizeNodeSize(node.size) ?? getPreferredNodeSize(node),
  );
  if (!nextSize) {
    return null;
  }
  node.__tyApplyingPreferredSize = true;
  try {
    node.setSize?.(nextSize);
  } finally {
    queueMicrotask(() => {
      node.__tyApplyingPreferredSize = false;
    });
  }
  return nextSize;
}

function resizeNodePreservingUserSize(node) {
  if (!node) {
    return;
  }
  const computedSize = node.computeSize?.();
  const normalizedComputed = normalizeNodeSize(computedSize);
  if (!normalizedComputed) {
    return;
  }
  const currentSize = normalizeNodeSize(node.size) ?? normalizedComputed;
  const nextSize = [
    Math.max(currentSize[0], normalizedComputed[0]),
    Math.max(currentSize[1], normalizedComputed[1]),
  ];
  applyPreferredNodeSize(node, nextSize);
}

function bindNodeSizePersistence(node) {
  if (!node || node.__tySizePersistenceBound) {
    return;
  }
  node.__tySizePersistenceBound = true;

  const initialSize = readPersistedNodeSize(node) ?? normalizeNodeSize(node.size);
  if (initialSize) {
    writePersistedNodeSize(node, initialSize);
  }

  const originalComputeSize = node.computeSize;
  node.computeSize = function (...args) {
    const computed = typeof originalComputeSize === "function"
      ? originalComputeSize.apply(this, args)
      : this.size;
    const normalizedComputed = normalizeNodeSize(computed);
    if (!normalizedComputed) {
      return computed;
    }
    const preferred = getPreferredNodeSize(this);
    if (!preferred) {
      return normalizedComputed;
    }
    return [
      Math.max(normalizedComputed[0], preferred[0]),
      Math.max(normalizedComputed[1], preferred[1]),
    ];
  };

  const originalOnResize = node.onResize;
  node.onResize = function (size) {
    const nextSize = normalizeNodeSize(size) ?? normalizeNodeSize(this.size);
    if (nextSize && !this.__tyApplyingPreferredSize) {
      writePersistedNodeSize(this, nextSize);
    }
    return originalOnResize?.apply(this, arguments);
  };

  const originalOnConfigure = node.onConfigure;
  node.onConfigure = function (info) {
    const result = originalOnConfigure?.apply(this, arguments);
    const configuredSize = readPersistedNodeSize({ properties: info?.properties })
      ?? normalizeNodeSize(info?.size)
      ?? readPersistedNodeSize(this)
      ?? normalizeNodeSize(this.size);
    if (configuredSize) {
      writePersistedNodeSize(this, configuredSize);
      queueMicrotask(() => {
        applyPreferredNodeSize(this, configuredSize);
        this.setDirtyCanvas?.(true, true);
      });
    }
    return result;
  };

  const originalOnSerialize = node.onSerialize;
  node.onSerialize = function (serialized) {
    const result = originalOnSerialize?.apply(this, arguments);
    const currentSize = getPreferredNodeSize(this) ?? normalizeNodeSize(this.size);
    if (currentSize) {
      writePersistedNodeSize(this, currentSize);
      if (serialized && typeof serialized === "object") {
        serialized.size = [...currentSize];
        serialized.properties = serialized.properties || {};
        serialized.properties[NODE_SIZE_PROPERTY] = [...currentSize];
      }
    }
    return result;
  };

  queueMicrotask(() => {
    const preferred = getPreferredNodeSize(node);
    if (preferred) {
      applyPreferredNodeSize(node, preferred);
      node.setDirtyCanvas?.(true, true);
    }
  });
}

function insertWidgetAfter(node, widget, anchorWidget) {
  if (!node || !widget || !anchorWidget || !Array.isArray(node.widgets)) {
    return;
  }
  const widgets = node.widgets;
  const widgetIndex = widgets.indexOf(widget);
  const anchorIndex = widgets.indexOf(anchorWidget);
  if (widgetIndex === -1 || anchorIndex === -1) {
    return;
  }
  widgets.splice(widgetIndex, 1);
  widgets.splice(anchorIndex + 1, 0, widget);
}

function setHiddenLoraValue(node, value) {
  const hiddenWidget = getHiddenLoraWidget(node);
  if (!hiddenWidget) {
    return;
  }
  const normalized = String(value || "").trim();
  const nextValue = isPlaceholderValue(normalized) ? "" : normalized;
  hiddenWidget.value = nextValue;
  hiddenWidget.callback?.(nextValue, app.canvas, node, hiddenWidget);
}

function getSelectedLoraValue(node) {
  const hiddenWidget = getHiddenLoraWidget(node);
  const hiddenValue = String(hiddenWidget?.value || "").trim();
  if (hiddenValue) {
    return hiddenValue;
  }
  const selectorWidget = getSelectorWidget(node);
  const selectorValue = String(selectorWidget?.value || "").trim();
  return isPlaceholderValue(selectorValue) ? "" : selectorValue;
}

function ensureSelectorWidget(node) {
  const existing = getSelectorWidget(node);
  if (existing) {
    return existing;
  }

  const hiddenWidget = getHiddenLoraWidget(node);
  if (!hiddenWidget) {
    return null;
  }

  collapseWidget(hiddenWidget);

  const initialValue = String(hiddenWidget.value || "").trim() || PLACEHOLDERS.waiting;
  const selectorWidget = node.addWidget(
    "combo",
    "lora_name",
    initialValue,
    (value) => {
      setHiddenLoraValue(node, value);
      syncWidgetsValues(node);
      node.setDirtyCanvas?.(true, true);
    },
    {
      values: [initialValue],
      serialize: false,
    },
  );

  node.__tyLoraSelectorWidget = selectorWidget;
  insertWidgetAfter(node, selectorWidget, hiddenWidget);
  return selectorWidget;
}

function setComboValues(node, values, preferredValue = "") {
  const selectorWidget = ensureSelectorWidget(node);
  if (!selectorWidget) {
    return;
  }
  const normalizedValues = (Array.isArray(values) ? values : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const safeValues = normalizedValues.length ? normalizedValues : [PLACEHOLDERS.empty];
  selectorWidget.options = selectorWidget.options || {};
  selectorWidget.options.values = [...safeValues];
  if (preferredValue && safeValues.includes(preferredValue)) {
    selectorWidget.value = preferredValue;
  } else {
    selectorWidget.value = safeValues[0] ?? "";
  }
  setHiddenLoraValue(node, selectorWidget.value);
  syncWidgetsValues(node);
  resizeNodePreservingUserSize(node);
  node.setDirtyCanvas?.(true, true);
}

function formatErrorPlaceholder(error) {
  const message = String(error?.message || error || "").trim().replace(/\s+/g, " ");
  if (!message) {
    return PLACEHOLDERS.error;
  }
  const compact = message.length > 42 ? `${message.slice(0, 42)}...` : message;
  return `<failed to read: ${compact}>`;
}

async function refreshLoraList(node, { preserveSelection = true } = {}) {
  const dirWidget = getWidget(node, "lora_dir");
  const selectorWidget = ensureSelectorWidget(node);
  if (!dirWidget || !selectorWidget) {
    return;
  }

  const dir = String(dirWidget.value || "").trim();
  const configNode = getConfigNode(node);
  const config = {
    base_url: normalizeBaseUrl(getConfigValue(configNode, 0, "http://127.0.0.1:3000")),
    launcher_root: String(getConfigValue(configNode, 1, "") || "").trim(),
    auto_start: Boolean(getConfigValue(configNode, 2, false)),
    output_dir: String(getConfigValue(configNode, 3, "") || "").trim(),
    gpu_id: Number(getConfigValue(configNode, 4, -1)),
    clear_gpu_before_run: Boolean(getConfigValue(configNode, 5, false)),
    low_vram_mode: Boolean(getConfigValue(configNode, 6, false)),
    health_timeout_s: Number(getConfigValue(configNode, 7, 60)),
    request_timeout_s: Number(getConfigValue(configNode, 8, 1800)),
  };

  const previousValue = preserveSelection ? getSelectedLoraValue(node) : "";
  setComboValues(node, [PLACEHOLDERS.loading], PLACEHOLDERS.loading);

  try {
    const response = await fetch("/ty_ltx_bridge/loras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        config,
        lora_dir: dir,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error || `HTTP ${response.status}`);
    }

    const resolvedDir = String(data?.loras_dir || "").trim();
    if (resolvedDir && !dir) {
      dirWidget.value = resolvedDir;
    }

    const values = Array.isArray(data?.loras)
      ? data.loras
          .map((item) => String(item?.name || "").trim())
          .filter(Boolean)
      : [];

    if (!values.length) {
      setComboValues(node, [PLACEHOLDERS.empty], PLACEHOLDERS.empty);
      return;
    }

    setComboValues(node, values, previousValue);
  } catch (error) {
    console.warn("[TY_LTX_Desktop_Bridge] Failed to refresh LoRA list:", error);
    const placeholder = formatErrorPlaceholder(error);
    setComboValues(node, [placeholder], placeholder);
  }
}

function bindSelectorNode(node) {
  if (node.__tyLoraSelectorBound) {
    return;
  }
  node.__tyLoraSelectorBound = true;
  bindNodeSizePersistence(node);

  const dirWidget = getWidget(node, "lora_dir");
  if (!dirWidget) {
    return;
  }

  const selectorWidget = ensureSelectorWidget(node);
  if (!selectorWidget) {
    return;
  }

  const originalCallback = dirWidget.callback;
  dirWidget.callback = (...args) => {
    if (typeof originalCallback === "function") {
      originalCallback.apply(dirWidget, args);
    }
    refreshLoraList(node, { preserveSelection: false });
  };

  if (!getWidget(node, "refresh_loras")) {
    const refreshWidget = node.addWidget(
      "button",
      "refresh_loras",
      "Refresh LoRAs",
      () => {
        refreshLoraList(node, { preserveSelection: true });
      },
      { serialize: false },
    );
    insertWidgetAfter(node, refreshWidget, selectorWidget);
  }

  queueMicrotask(() => {
    const currentDir = String(dirWidget.value || "").trim();
    if (currentDir || getConfigNode(node)) {
      refreshLoraList(node, { preserveSelection: true });
    } else {
      setComboValues(node, [PLACEHOLDERS.waiting], PLACEHOLDERS.waiting);
    }
  });
}

app.registerExtension({
  name: "TY_LTX_Desktop_Bridge.LoraSelector",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TARGETS.has(nodeData.name)) {
      return;
    }

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      bindSelectorNode(this);
      return result;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      bindSelectorNode(this);
      return result;
    };

    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = onConnectionsChange?.apply(this, arguments);
      queueMicrotask(() => refreshLoraList(this, { preserveSelection: true }));
      return result;
    };
  },
});

const CONFIG_TARGETS = new Set(["LTXDesktopConfig", "TYLTXDesktopConfig"]);
const GENERATE_TARGETS = new Set(["LTXDesktopGenerateVideo", "TYLTXDesktopGenerateVideo"]);
const GENERATE_WIDGET_ORDER = [
  "prompt",
  "resolution",
  "aspect_ratio",
  "duration",
  "fps",
  "seed_mode",
  "seed",
  "camera_motion",
  "audio",
  "negative_prompt",
  "audio_path",
  "inference_steps",
  "lora_path",
  "lora_strength",
  "model_path",
  "keyframe_strengths",
  "keyframe_times",
];
const LEGACY_SEED_CONTROLS = new Set(["randomize", "fixed", "increment", "decrement"]);

function updateWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) {
    return;
  }
  widget.value = value;
  widget.callback?.(value, app.canvas, node, widget);
}

function syncWidgetsValues(node) {
  if (!Array.isArray(node.widgets)) {
    return;
  }
  node.widgets_values = node.widgets
    .filter((widget) => shouldSerializeWidget(widget))
    .map((widget) => widget.value);
  resizeNodePreservingUserSize(node);
  node.setDirtyCanvas?.(true, true);
}

function migrateConfigNode(node) {
  if (!Array.isArray(node.widgets_values) || node.widgets_values.length < 8) {
    return;
  }

  const values = [...node.widgets_values];
  if (typeof values[6] === "boolean") {
    return;
  }

  const migrated = [
    values[0] ?? "http://127.0.0.1:3000",
    values[1] ?? "",
    Boolean(values[2]),
    values[3] ?? "",
    Number(values[4] ?? -1),
    Boolean(values[5]),
    false,
    Number(values[6] ?? 60),
    Number(values[7] ?? 1800),
  ];

  const widgetNames = [
    "base_url",
    "launcher_root",
    "auto_start",
    "output_dir",
    "gpu_id",
    "clear_gpu_before_run",
    "low_vram_mode",
    "health_timeout_s",
    "request_timeout_s",
  ];

  widgetNames.forEach((name, index) => updateWidgetValue(node, name, migrated[index]));
  syncWidgetsValues(node);
  console.info("[TY_LTX_Desktop_Bridge] Migrated legacy LTXDesktopConfig widget values.");
}

function migrateGenerateVideoNode(node) {
  if (!Array.isArray(node.widgets_values) || node.widgets_values.length < 15) {
    return;
  }

  const values = [...node.widgets_values];
  let migrated = null;

  if (LEGACY_SEED_CONTROLS.has(String(values[7] ?? "").trim())) {
    const withoutLegacySeedControl = [...values.slice(0, 7), ...values.slice(8)];
    while (withoutLegacySeedControl.length < GENERATE_WIDGET_ORDER.length) {
      withoutLegacySeedControl.push("");
    }
    migrated = [
      withoutLegacySeedControl[0] ?? "",
      withoutLegacySeedControl[1] ?? "",
      withoutLegacySeedControl[2] ?? "",
      Number(withoutLegacySeedControl[3] ?? 5),
      withoutLegacySeedControl[4] ?? "24",
      withoutLegacySeedControl[5] ?? "fixed (鍥哄畾绉嶅瓙)",
      Number(withoutLegacySeedControl[6] ?? 123456789),
      withoutLegacySeedControl[7] ?? "static (闈欐鏈轰綅)",
      Boolean(withoutLegacySeedControl[8]),
      withoutLegacySeedControl[9] ?? "",
      withoutLegacySeedControl[10] ?? "",
      Number(withoutLegacySeedControl[11] ?? 8),
      withoutLegacySeedControl[12] ?? "",
      Number(withoutLegacySeedControl[13] ?? 1.0),
      withoutLegacySeedControl[14] ?? "",
      withoutLegacySeedControl[15] ?? "",
      withoutLegacySeedControl[16] ?? "",
    ];
  } else if (values.length === 15) {
    migrated = [...values, "", ""];
  }

  if (!migrated) {
    return;
  }

  GENERATE_WIDGET_ORDER.forEach((name, index) => updateWidgetValue(node, name, migrated[index]));
  syncWidgetsValues(node);
  console.info("[TY_LTX_Desktop_Bridge] Migrated legacy LTXDesktopGenerateVideo widget values.");
}

function bindLegacyMigration(node, nodeName) {
  queueMicrotask(() => {
    if (CONFIG_TARGETS.has(nodeName)) {
      migrateConfigNode(node);
    }
    if (GENERATE_TARGETS.has(nodeName)) {
      migrateGenerateVideoNode(node);
    }
  });
}

app.registerExtension({
  name: "TY_LTX_Desktop_Bridge.LegacyWorkflowMigration",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!CONFIG_TARGETS.has(nodeData.name) && !GENERATE_TARGETS.has(nodeData.name)) {
      return;
    }

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      bindLegacyMigration(this, nodeData.name);
      return result;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      bindLegacyMigration(this, nodeData.name);
      return result;
    };
  },
});
