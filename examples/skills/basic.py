from pathlib import Path

from bumblehive.skills import SkillsManager


SKILLS_DIR = Path(__file__).parent


def main() -> None:
    manager = SkillsManager(SKILLS_DIR)
    catalog = manager.list_skills()
    print("Skills:", [skill.name for skill in catalog.skills])
    print(manager.load_skill_content("project-summary"))


if __name__ == "__main__":
    main()
