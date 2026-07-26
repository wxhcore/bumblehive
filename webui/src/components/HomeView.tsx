const suggestions = [
  {
    label: "分析项目",
    prompt: "分析这个项目的结构、风险和改进方向",
    icon: "analysis-icon",
  },
  {
    label: "规划功能",
    prompt: "帮我规划这个功能的实现方案和步骤",
    icon: "plan-icon",
  },
  {
    label: "审查代码",
    prompt: "审查代码并指出潜在问题",
    icon: "code-icon",
  },
];

interface HomeViewProps {
  onSelectPrompt: (prompt: string) => void;
}

export function HomeView({ onSelectPrompt }: HomeViewProps) {
  return (
    <header className="hero">
      <h1>
        <span>今天想让</span>
        <img
          className="hero-wordmark"
          src="/brand/bumblehive-wordmark.png"
          alt="BumbleHive"
        />
        <span>做点什么？</span>
      </h1>
      <div className="suggestions" aria-label="任务建议">
        {suggestions.map((suggestion) => (
          <button
            className="suggestion"
            type="button"
            key={suggestion.label}
            onClick={() => onSelectPrompt(suggestion.prompt)}
          >
            <span
              className={`suggest-icon ${suggestion.icon}`}
              aria-hidden="true"
            >
              {suggestion.icon === "plan-icon" ? (
                <span className="node" />
              ) : null}
            </span>
            <span>{suggestion.label}</span>
          </button>
        ))}
      </div>
    </header>
  );
}
