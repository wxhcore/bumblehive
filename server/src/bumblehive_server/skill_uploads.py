import shutil
import stat
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from fastapi import UploadFile


MAX_ARCHIVES = 50
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_SKILLS = 100


def extract_skill_archives(
    uploads: Sequence[UploadFile],
    destination: Path,
) -> list[Path]:
    """Safely extract uploaded ZIP archives and return skill package roots."""
    if not uploads:
        raise ValueError("请选择至少一个技能 ZIP 包")
    if len(uploads) > MAX_ARCHIVES:
        raise ValueError(f"一次最多导入 {MAX_ARCHIVES} 个 ZIP 包")

    destination.mkdir(parents=True, exist_ok=True)
    sources: list[Path] = []
    total_archive_bytes = 0
    total_extracted_bytes = 0
    total_entries = 0

    for index, upload in enumerate(uploads):
        filename = Path(upload.filename or "").name
        if not filename.lower().endswith(".zip"):
            raise ValueError(f"只支持 ZIP 技能包：{filename or '未命名文件'}")

        upload.file.seek(0, 2)
        total_archive_bytes += upload.file.tell()
        upload.file.seek(0)
        if total_archive_bytes > MAX_ARCHIVE_BYTES:
            raise ValueError("上传的技能包总大小不能超过 100 MB")

        archive_root = destination / str(index)
        archive_root.mkdir()
        try:
            with ZipFile(upload.file) as archive:
                entries = archive.infolist()
                total_entries += len(entries)
                total_extracted_bytes += sum(info.file_size for info in entries)
                if total_entries > MAX_ARCHIVE_ENTRIES:
                    raise ValueError("技能包包含的文件数量过多")
                if total_extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise ValueError("技能包解压后的总大小不能超过 250 MB")
                _extract_zip(archive, entries, archive_root)
        except BadZipFile as exc:
            raise ValueError(f"无效的 ZIP 技能包：{filename}") from exc

        sources.extend(_find_skill_roots(archive_root))
        if len(sources) > MAX_SKILLS:
            raise ValueError(f"一次最多导入 {MAX_SKILLS} 个技能")

    if not sources:
        raise ValueError("技能包中没有找到 SKILL.md")
    return sources


def _extract_zip(
    archive: ZipFile,
    entries: Sequence[ZipInfo],
    destination: Path,
) -> None:
    destination = destination.resolve()
    for info in entries:
        relative = _safe_archive_path(info)
        if relative is None:
            continue
        target = destination.joinpath(*relative.parts)
        if not target.is_relative_to(destination):
            raise ValueError(f"技能包包含不安全路径：{info.filename}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
        except FileExistsError as exc:
            raise ValueError(f"技能包包含重复路径：{info.filename}") from exc


def _safe_archive_path(info: ZipInfo) -> PurePosixPath | None:
    filename = info.filename
    if "\\" in filename:
        raise ValueError(f"技能包包含不安全路径：{filename}")
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"技能包包含不安全路径：{filename}")
    if not path.parts or "__MACOSX" in path.parts:
        return None
    if path.name.startswith("._"):
        return None
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"技能包不能包含符号链接：{filename}")
    return path


def _find_skill_roots(root: Path) -> list[Path]:
    candidates = sorted(
        {
            skill_file.parent.resolve()
            for skill_file in root.rglob("SKILL.md")
            if skill_file.is_file()
        },
        key=lambda path: (len(path.parts), path.as_posix()),
    )
    selected: list[Path] = []
    for candidate in candidates:
        if any(parent == candidate or parent in candidate.parents for parent in selected):
            continue
        selected.append(candidate)
    return selected
