from core.skills_registry import SkillsRegistry


def test_registry_loads_and_returns_prefix():
    registry = SkillsRegistry("core/role_skills_registry.yaml")
    prefix = registry.get_prompt_prefix("architect", supports_skill_activation=True)
    assert "Activa la skill 'dotnet'" in prefix
    assert "Activa la skill 'code-review'" in prefix


def test_registry_fallback_when_no_skill_activation():
    registry = SkillsRegistry("core/role_skills_registry.yaml")
    prefix = registry.get_prompt_prefix("architect", supports_skill_activation=False)
    assert "Activa la skill" not in prefix
    assert "patrones técnicos" in prefix
