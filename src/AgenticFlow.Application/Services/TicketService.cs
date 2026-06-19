using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Services;

public class TicketService : ITicketService
{
    private readonly IBoardStore _boardStore;
    private readonly IOrchestrator _orchestrator;

    public TicketService(IBoardStore boardStore, IOrchestrator orchestrator)
    {
        _boardStore = boardStore;
        _orchestrator = orchestrator;
    }

    public Task<IReadOnlyList<Ticket>> GetAllAsync()
    {
        var state = _boardStore.Load();
        return Task.FromResult<IReadOnlyList<Ticket>>(state.Tickets);
    }

    public Task<Ticket?> GetByIdAsync(Guid id)
    {
        var state = _boardStore.Load();
        return Task.FromResult(state.Tickets.FirstOrDefault(t => t.Id == id));
    }

    public async Task PlayAsync(Guid id)
    {
        var ticket = await GetByIdAsync(id);
        if (ticket == null) throw new InvalidOperationException($"Ticket {id} not found");
        await _orchestrator.RunAsync(ticket);
    }
}
