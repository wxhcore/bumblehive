from pathlib import Path

from bumblehive.skills import SkillsManager


SKILLS_DIR = Path(__file__).parent


def main() -> None:
    manager = SkillsManager(SKILLS_DIR)
    result = manager.list_skills()
    skill = manager.get_skill("project-summary")
    if skill is None:
        raise RuntimeError("Bundled example skill was not found.")

    print("Skills:", [skill.name for skill in result.skills])
    print("Errors:", [error.message for error in result.errors])
    print("Selected:", skill.name)
    print("Scripts:", skill.scripts)
    print("References:", skill.references)
    print("Assets:", skill.assets)
    print("Content:", manager.load_skill_content(skill.name))
    print("Prompt summary:", manager.build_skills_summary([skill.name]))

    reloaded = manager.reload()
    print("Reloaded:", len(reloaded.skills))


if __name__ == "__main__":
    main()
