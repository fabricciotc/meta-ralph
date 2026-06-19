using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Entities;

/// <summary>
/// Task inside a plan.
/// Compatible with the legacy Python <c>core.plan.Task</c> schema.
/// </summary>
public class TaskItem
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("dependencies")]
    public List<Guid> Dependencies { get; set; } = new();

    [JsonPropertyName("files_to_touch")]
    public List<string> FilesToTouch { get; set; } = new();

    [JsonPropertyName("complexity")]
    public string Complexity { get; set; } = "M";

    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    [JsonPropertyName("assigned_to")]
    public string? Assignee { get; set; }

    [JsonPropertyName("batch_id")]
    public int? BatchId { get; set; }

    [JsonPropertyName("qa_checklist")]
    public List<string> QaChecklist { get; set; } = new();

    [JsonPropertyName("metadata")]
    public Dictionary<string, object> Metadata { get; set; } = new();
}
