using AgenticFlow.Application.Abstractions;
using AgenticFlow.Bff.Hubs;
using AgenticFlow.Domain.Events;
using Microsoft.AspNetCore.SignalR;

namespace AgenticFlow.Bff.Infrastructure;

public class SignalREventBus : IEventBus
{
    private readonly IHubContext<DashboardHub> _hubContext;

    public SignalREventBus(IHubContext<DashboardHub> hubContext)
    {
        _hubContext = hubContext;
    }

    public async Task PublishAsync(IDomainEvent domainEvent, CancellationToken cancellationToken = default)
    {
        await _hubContext.Clients.All.SendAsync("event", domainEvent, cancellationToken);
    }
}
