using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Entities;

/// <summary>
/// Kanban ticket entity.
/// Compatible with the legacy Python board ticket schema stored in <c>board.json</c>.
/// </summary>
public class Ticket : Entity
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = "backlog";

    [JsonPropertyName("repoPath")]
    public string RepoPath { get; set; } = string.Empty;

    [JsonPropertyName("branch")]
    public string Branch { get; set; } = string.Empty;

    [JsonPropertyName("assigneeRole")]
    public string AssigneeRole { get; set; } = string.Empty;

    [JsonPropertyName("featureFocus")]
    public string FeatureFocus { get; set; } = string.Empty;

    [JsonPropertyName("storyId")]
    public string StoryId { get; set; } = string.Empty;

    [JsonPropertyName("taskId")]
    public string TaskId { get; set; } = string.Empty;

    [JsonPropertyName("labels")]
    public List<string> Labels { get; set; } = new();

    [JsonPropertyName("blocked")]
    public bool Blocked { get; set; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

    [JsonPropertyName("startedAt")]
    public DateTimeOffset? StartedAt { get; set; }

    [JsonPropertyName("completedAt")]
    public DateTimeOffset? CompletedAt { get; set; }

    [JsonPropertyName("elapsedSeconds")]
    public long ElapsedSeconds { get; set; }

    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;

    [JsonPropertyName("metadata")]
    public Dictionary<string, object> Metadata { get; set; } = new();
}
