interface ModelOptionsProps {
  models: string[];
  selectedModel: string;
  onSelect: (model: string) => void;
  emptyMessage?: string;
}

export function ModelOptions({
  models,
  selectedModel,
  onSelect,
  emptyMessage = "没有可用的模型",
}: ModelOptionsProps) {
  if (!models.length) {
    return <div className="model-option-empty">{emptyMessage}</div>;
  }

  return models.map((model) => (
    <button
      key={model}
      type="button"
      role="option"
      aria-selected={model === selectedModel}
      className={model === selectedModel ? "model-option active" : "model-option"}
      onClick={() => onSelect(model)}
    >
      <span className="model-option-id">{model}</span>
    </button>
  ));
}
