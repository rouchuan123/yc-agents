import { useEffect, useState } from "react";

export interface SettingsPanelProps {
  initialModel?: string;
  initialBaseUrl?: string;
  hasApiKey?: boolean;
  onSave: (settings: { model: string; base_url: string; api_key: string }) => void | Promise<void>;
}

export function SettingsPanel({
  initialModel = "",
  initialBaseUrl = "",
  hasApiKey = false,
  onSave,
}: SettingsPanelProps) {
  const [model, setModel] = useState(initialModel);
  const [baseUrl, setBaseUrl] = useState(initialBaseUrl);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setModel(initialModel);
    setBaseUrl(initialBaseUrl);
    setApiKey("");
  }, [initialModel, initialBaseUrl, hasApiKey]);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave({ model, base_url: baseUrl, api_key: apiKey });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="settings-panel" aria-label="Settings panel">
      <h2>模型设置</h2>
      <label>
        模型
        <input value={model} onChange={(event) => setModel(event.target.value)} />
      </label>
      <label>
        Base URL
        <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
      </label>
      <label>
        API Key
        <input
          type="password"
          value={apiKey}
          placeholder={hasApiKey ? "已配置，留空则不修改" : "未配置"}
          onChange={(event) => setApiKey(event.target.value)}
        />
      </label>
      <button aria-label="Save settings" disabled={saving} onClick={handleSave}>
        保存设置
      </button>
    </section>
  );
}
