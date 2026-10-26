export function HomeView({ workspace }: { workspace: string | null }) {
  return <header className="hero">
    <h1>{workspace ? <>你想在 <span>{workspace}</span> 中构建什么？</> : "今天想让 Bumblehive 做点什么？"}</h1>
  </header>;
}
