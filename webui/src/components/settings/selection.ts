export function optionIsEnabled(
  selected: string[] | null,
  name: string,
): boolean {
  return selected === null || selected.includes(name);
}

export function setOptionsEnabled(
  selected: string[] | null,
  targetNames: string[],
  enabled: boolean,
  availableNames: string[],
): string[] | null {
  if (!targetNames.length) return selected;

  const next =
    selected === null ? new Set(availableNames) : new Set(selected);
  for (const name of targetNames) {
    if (enabled) next.add(name);
    else next.delete(name);
  }

  return enabled && availableNames.every((name) => next.has(name))
    ? null
    : Array.from(next);
}
