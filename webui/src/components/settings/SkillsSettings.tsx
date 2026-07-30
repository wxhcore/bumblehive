import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  ApiError,
  deleteSkill,
  importSkillArchives,
  refreshSkills,
} from "../../api/http";
import type {
  SettingsOptions,
  SettingsSkillOption,
} from "../../types/api";
import {
  setSkillsEnabled,
  skillIsEnabled,
} from "./skill-selection";

interface SkillsSettingsProps {
  skills: SettingsSkillOption[];
  errors: SettingsOptions["skill_errors"];
  selectedNames: string[] | null;
  disabled: boolean;
  onSelectedNamesChange: (names: string[] | null) => void;
  onOptionsChange: (options: SettingsOptions) => void;
}

type SkillAction = "refresh" | "import" | `delete:${string}`;

export function SkillsSettings({
  skills,
  errors,
  selectedNames,
  disabled,
  onSelectedNamesChange,
  onOptionsChange,
}: SkillsSettingsProps) {
  const [query, setQuery] = useState("");
  const [selectedSkillName, setSelectedSkillName] = useState<string | null>(
    null,
  );
  const [action, setAction] = useState<SkillAction | null>(null);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);
  const [isDraggingArchives, setIsDraggingArchives] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const availableNames = useMemo(
    () => skills.map((skill) => skill.name),
    [skills],
  );
  const selectedSkill =
    skills.find((skill) => skill.name === selectedSkillName) ?? null;
  const normalizedQuery = query.trim().toLowerCase();
  const visibleSkills = skills.filter((skill) =>
    `${skill.name} ${skill.description}`
      .toLowerCase()
      .includes(normalizedQuery),
  );
  const enabledCount = availableNames.filter((name) =>
    skillIsEnabled(selectedNames, name),
  ).length;
  const allEnabled =
    availableNames.length > 0 && enabledCount === availableNames.length;

  useEffect(() => {
    if (selectedSkillName && !selectedSkill) setSelectedSkillName(null);
  }, [selectedSkill, selectedSkillName]);

  function setEnabled(targetNames: string[], enabled: boolean) {
    onSelectedNamesChange(
      setSkillsEnabled(
        selectedNames,
        targetNames,
        enabled,
        availableNames,
      ),
    );
  }

  async function reloadCatalog() {
    setAction("refresh");
    setMessage(null);
    try {
      const options = await refreshSkills();
      onOptionsChange(options);
      setMessage({
        tone: "success",
        text: `技能列表已刷新，共 ${options.skills.length} 个技能`,
      });
    } catch (reason) {
      setMessage({
        tone: "error",
        text: reason instanceof Error ? reason.message : "技能刷新失败",
      });
    } finally {
      setAction(null);
    }
  }

  async function uploadArchives(files: File[], replace = false) {
    return importSkillArchives(files, replace);
  }

  async function importArchives(files: File[]) {
    if (!files.length) return;
    const invalidFiles = files.filter(
      (file) => !file.name.toLowerCase().endsWith(".zip"),
    );
    if (invalidFiles.length) {
      setMessage({
        tone: "error",
        text: `仅支持 ZIP 技能包：${invalidFiles.map((file) => file.name).join("、")}`,
      });
      return;
    }

    setAction("import");
    setMessage(null);
    try {
      let options: SettingsOptions;
      try {
        options = await uploadArchives(files);
      } catch (reason) {
        if (
          reason instanceof ApiError &&
          reason.status === 409 &&
          window.confirm("存在同名技能。要使用导入的版本覆盖吗？")
        ) {
          options = await uploadArchives(files, true);
        } else {
          throw reason;
        }
      }
      const previousNames = new Set(skills.map((skill) => skill.name));
      const imported = options.skills.filter(
        (skill) => !previousNames.has(skill.name),
      );
      onOptionsChange(options);
      if (imported.length) {
        onSelectedNamesChange(
          setSkillsEnabled(
            selectedNames,
            imported.map((skill) => skill.name),
            true,
            options.skills.map((skill) => skill.name),
          ),
        );
      }
      setMessage({
        tone: "success",
        text: `${files.length} 个 ZIP 包已导入，当前共 ${options.skills.length} 个技能`,
      });
    } catch (reason) {
      setMessage({
        tone: "error",
        text: reason instanceof Error ? reason.message : "技能导入失败",
      });
    } finally {
      setAction(null);
    }
  }

  function selectArchives(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    void importArchives(files);
  }

  function isFileDrag(event: DragEvent<HTMLElement>) {
    return Array.from(event.dataTransfer.types).includes("Files");
  }

  function beginArchiveDrag(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    if (disabled || action !== null) return;
    dragDepthRef.current += 1;
    setIsDraggingArchives(true);
  }

  function continueArchiveDrag(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect =
      disabled || action !== null ? "none" : "copy";
  }

  function endArchiveDrag(event: DragEvent<HTMLElement>) {
    if (dragDepthRef.current === 0) return;
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDraggingArchives(false);
  }

  function dropArchives(event: DragEvent<HTMLElement>) {
    if (!isFileDrag(event) && !event.dataTransfer.files.length) return;
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDraggingArchives(false);
    if (disabled || action !== null) return;
    void importArchives(Array.from(event.dataTransfer.files));
  }

  async function removeSelectedSkill() {
    if (!selectedSkill) return;
    if (!window.confirm(`删除技能“${selectedSkill.name}”？`)) return;
    const name = selectedSkill.name;
    setAction(`delete:${name}`);
    setMessage(null);
    try {
      const options = await deleteSkill(name);
      onOptionsChange(options);
      if (selectedNames !== null) {
        onSelectedNamesChange(
          selectedNames.filter((selected) => selected !== name),
        );
      }
      setSelectedSkillName(null);
      setMessage({ tone: "success", text: `已删除技能“${name}”` });
    } catch (reason) {
      setMessage({
        tone: "error",
        text: reason instanceof Error ? reason.message : "技能删除失败",
      });
    } finally {
      setAction(null);
    }
  }

  return (
    <div className="skill-page">
      <div className="skill-toolbar">
        <label className="tool-page-search">
          <span aria-hidden="true" />
          <input
            value={query}
            placeholder="搜索技能"
            aria-label="搜索技能"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="skill-toolbar-actions">
          <button
            type="button"
            disabled={disabled || action !== null}
            onClick={() => void reloadCatalog()}
          >
            <span
              className={action === "refresh" ? "mcp-refresh-spinning" : ""}
              aria-hidden="true"
            >
              ↻
            </span>
            刷新
          </button>
          <button
            className="primary"
            type="button"
            disabled={disabled || action !== null}
            onClick={() => {
              if (fileInputRef.current) fileInputRef.current.value = "";
              fileInputRef.current?.click();
            }}
          >
            <span aria-hidden="true">＋</span>
            {action === "import" ? "正在导入…" : "导入技能"}
          </button>
          <input
            ref={fileInputRef}
            className="skill-file-input"
            type="file"
            accept=".zip,application/zip"
            multiple
            aria-label="选择技能 ZIP 包"
            onChange={selectArchives}
          />
        </div>
      </div>

      {disabled ? (
        <div className="settings-page-alert">
          有任务正在运行，任务完成后才能导入、删除或刷新技能。
        </div>
      ) : null}
      {message ? (
        <div
          className={`skill-message ${message.tone}`}
          role={message.tone === "error" ? "alert" : "status"}
        >
          {message.text}
        </div>
      ) : null}

      <section
        className={`skill-catalog${isDraggingArchives ? " is-dragging" : ""}`}
        aria-label="已安装技能；可拖入一个或多个 ZIP 技能包"
        onDragEnter={beginArchiveDrag}
        onDragOver={continueArchiveDrag}
        onDragLeave={endArchiveDrag}
        onDrop={dropArchives}
      >
        {isDraggingArchives ? (
          <div className="skill-drop-overlay" role="status">
            <span className="skill-drop-overlay-icon" aria-hidden="true">↓</span>
            <strong>松开以导入技能</strong>
            <span>支持一次拖入多个 ZIP 技能包</span>
          </div>
        ) : null}
        <header className="skill-catalog-header">
          <div>
            <strong>已安装技能</strong>
            <span>
              {skills.length
                ? `已启用 ${enabledCount} / ${skills.length}`
                : "导入后可以选择发送给模型的技能"}
            </span>
          </div>
          <button
            type="button"
            disabled={!availableNames.length}
            onClick={() => setEnabled(availableNames, !allEnabled)}
          >
            {allEnabled ? "全部关闭" : "全部开启"}
          </button>
        </header>

        {visibleSkills.length ? (
          <div className="skill-list">
            {visibleSkills.map((skill) => {
              const enabled = skillIsEnabled(selectedNames, skill.name);
              return (
                <div className="skill-row" key={skill.name}>
                  <button
                    className="skill-row-main"
                    type="button"
                    onClick={() => setSelectedSkillName(skill.name)}
                  >
                    <span className="skill-row-icon" aria-hidden="true">✦</span>
                    <span className="skill-row-copy">
                      <strong>{skill.name}</strong>
                      <span title={skill.description}>
                        {skill.description || "暂无描述"}
                      </span>
                    </span>
                  </button>
                  <label className="tool-toggle">
                    <input
                      type="checkbox"
                      role="switch"
                      checked={enabled}
                      aria-label={`${enabled ? "关闭" : "开启"}技能 ${skill.name}`}
                      onChange={() => setEnabled([skill.name], !enabled)}
                    />
                    <span aria-hidden="true" />
                  </label>
                  <button
                    className="skill-row-disclosure"
                    type="button"
                    aria-label={`查看技能 ${skill.name}`}
                    onClick={() => setSelectedSkillName(skill.name)}
                  >
                    ›
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="settings-empty-state skill-empty">
            <div className="settings-empty-icon" aria-hidden="true">✦</div>
            <strong>
              {query.trim() ? "没有匹配的技能" : "还没有安装技能"}
            </strong>
            <span>
              {query.trim()
                ? "尝试搜索其他名称或描述。"
                : "将 ZIP 拖到此处，或一次选择多个技能包批量导入。"}
            </span>
          </div>
        )}
      </section>

      {errors.length ? (
        <details className="skill-load-errors">
          <summary>{errors.length} 个技能未能加载</summary>
          <div>
            {errors.map((error) => (
              <p key={`${error.path}:${error.message}`}>
                <strong title={error.path}>{error.path}</strong>
                <span>{error.message}</span>
              </p>
            ))}
          </div>
        </details>
      ) : null}

      {selectedSkill
        ? createPortal(
            <div
              className="skill-sheet-backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setSelectedSkillName(null);
                }
              }}
            >
              <section
                className="skill-sheet"
                role="dialog"
                aria-modal="true"
                aria-labelledby="skill-sheet-title"
              >
                <header className="skill-sheet-header">
                  <div className="skill-sheet-identity">
                    <span aria-hidden="true">✦</span>
                    <div>
                      <h2 id="skill-sheet-title">{selectedSkill.name}</h2>
                      <p>本地技能</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    aria-label="关闭技能详情"
                    onClick={() => setSelectedSkillName(null)}
                  >
                    ×
                  </button>
                </header>
                <div className="skill-sheet-body">
                  <section>
                    <h3>描述</h3>
                    <p>{selectedSkill.description || "暂无描述"}</p>
                  </section>
                  <section className="skill-sheet-enable">
                    <div>
                      <h3>提供给模型</h3>
                      <p>开启后，模型可以在需要时读取并使用此技能。</p>
                    </div>
                    <label className="tool-toggle">
                      <input
                        type="checkbox"
                        role="switch"
                        checked={skillIsEnabled(
                          selectedNames,
                          selectedSkill.name,
                        )}
                        aria-label={`提供技能 ${selectedSkill.name} 给模型`}
                        onChange={(event) =>
                          setEnabled(
                            [selectedSkill.name],
                            event.target.checked,
                          )
                        }
                      />
                      <span aria-hidden="true" />
                    </label>
                  </section>
                  <div className="skill-sheet-note">
                    技能文件保存在本机，不会上传到 BumbleHive 之外。
                  </div>
                </div>
                <footer className="skill-sheet-footer">
                  <button
                    className="danger"
                    type="button"
                    disabled={
                      disabled || action === `delete:${selectedSkill.name}`
                    }
                    onClick={() => void removeSelectedSkill()}
                  >
                    {action === `delete:${selectedSkill.name}`
                      ? "正在删除…"
                      : "删除技能"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedSkillName(null)}
                  >
                    完成
                  </button>
                </footer>
              </section>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
