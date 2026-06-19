using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Events;

public class PhaseCompletedEvent : DomainEventBase
{
    [JsonPropertyName("ticketId")]
    public Guid TicketId { get; set; }

    [JsonPropertyName("phase")]
    public string Phase { get; set; } = string.Empty;
}
