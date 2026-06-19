using System.Text.Json.Serialization;

namespace AgenticFlow.Domain.Events;

public class TicketStartedEvent : DomainEventBase
{
    [JsonPropertyName("ticketId")]
    public Guid TicketId { get; set; }
}
