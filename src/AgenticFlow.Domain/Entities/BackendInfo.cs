using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Entities;

/// <summary>
/// Information about an available AI backend/runner.
/// </summary>
public class BackendInfo
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("available")]
    public bool Available { get; set; }

    [JsonPropertyName("priority")]
    public int Priority { get; set; }

    [JsonPropertyName("supportsSkillActivation")]
    public bool SupportsSkillActivation { get; set; }

    [JsonPropertyName("metadata")]
    public Dictionary<string, object> Metadata { get; set; } = new();
}
