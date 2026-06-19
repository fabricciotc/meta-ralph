using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Entities;

/// <summary>
/// Execution plan composed of dependency-aware tasks.
/// </summary>
public class Plan
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [JsonPropertyName("tasks")]
    public List<TaskItem> Tasks { get; set; } = new();

    /// <summary>
    /// Topological levels computed from task dependencies.
    /// Each inner list contains task IDs that can run in parallel.
    /// </summary>
    [JsonPropertyName("levels")]
    public List<List<Guid>> Levels { get; set; } = new();

    [JsonPropertyName("metadata")]
    public Dictionary<string, object> Metadata { get; set; } = new();
}
