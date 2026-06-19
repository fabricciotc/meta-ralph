using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Skills;

public class SkillRegistry : ISkillRegistry
{
    public string GetPrefixForRole(string role) => string.Empty;
}
