using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Orchestration;

public class DefaultContext : IContext
{
    public Ticket Ticket { get; }
    public IMemoryStore Memory { get; }
    public CancellationToken CancellationToken { get; }

    public DefaultContext(Ticket ticket, IMemoryStore memory, CancellationToken cancellationToken)
    {
        Ticket = ticket;
        Memory = memory;
        CancellationToken = cancellationToken;
    }
}
