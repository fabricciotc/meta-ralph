using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface IOrchestrator
{
    Task RunAsync(Ticket ticket, CancellationToken cancellationToken = default);
    Task PauseAsync();
    Task ResumeAsync();
    Task StopAsync();
}
