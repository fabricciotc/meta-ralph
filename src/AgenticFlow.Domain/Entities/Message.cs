using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Entities;

/// <summary>
/// Domain message exchanged between roles/agents.
/// Compatible with the legacy Python <c>core.models.Message</c> schema.
/// </summary>
public class Message
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [JsonPropertyName("cause_by")]
    public string Cause { get; set; } = string.Empty;

    [JsonPropertyName("sent_from")]
    public string Role { get; set; } = string.Empty;

    [JsonPropertyName("msg_type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("send_to")]
    public string Recipient { get; set; } = "all";

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("metadata")]
    public Dictionary<string, object> Metadata { get; set; } = new();

    [JsonPropertyName("routing_key")]
    public string? RoutingKey { get; set; }

    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    /// <summary>
    /// Returns true if the message is addressed to <paramref name="roleId"/> or broadcast.
    /// </summary>
    public bool IsFor(string roleId)
    {
        return Recipient == "all" || Recipient == roleId;
    }

    /// <summary>
    /// Returns true if the message is a broadcast to all roles.
    /// </summary>
    public bool IsBroadcast()
    {
        return Recipient == "all";
    }
}
