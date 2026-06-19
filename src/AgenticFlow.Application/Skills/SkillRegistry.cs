using AgenticFlow.Application.Abstractions;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace AgenticFlow.Application.Skills;

public class SkillRegistry : ISkillRegistry
{
    private readonly Dictionary<string, string> _prefixes = new(StringComparer.OrdinalIgnoreCase);

    public SkillRegistry()
    {
        var yamlPath = Path.Combine(AppContext.BaseDirectory, "Skills", "role_skills_registry.yaml");
        if (!File.Exists(yamlPath)) return;

        var yaml = File.ReadAllText(yamlPath);
        var deserializer = new DeserializerBuilder()
            .WithNamingConvention(UnderscoredNamingConvention.Instance)
            .IgnoreUnmatchedProperties()
            .Build();

        var data = deserializer.Deserialize<Dictionary<string, SkillEntry>>(yaml);
        if (data == null) return;

        foreach (var entry in data)
        {
            _prefixes[entry.Key] = entry.Value.PromptPrefix ?? string.Empty;
        }
    }

    public string GetPrefixForRole(string role) =>
        _prefixes.TryGetValue(role, out var prefix) ? prefix : string.Empty;

    private class SkillEntry
    {
        public List<string> Skills { get; set; } = new();
        public List<string> McpServers { get; set; } = new();
        public string PromptPrefix { get; set; } = string.Empty;
    }
}
