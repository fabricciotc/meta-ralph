using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;
using AgenticFlow.Domain.Events;

namespace AgenticFlow.Application.Orchestration;

public class Orchestrator : IOrchestrator
{
    private readonly IEnvironment _environment;
    private readonly IPlanEngine _planEngine;
    private readonly IMemoryStore _memory;
    private readonly IEventBus _eventBus;
    private readonly ISnapshotStore _snapshotStore;

    public Orchestrator(
        IEnvironment environment,
        IPlanEngine planEngine,
        IMemoryStore memory,
        IEventBus eventBus,
        ISnapshotStore snapshotStore)
    {
        _environment = environment;
        _planEngine = planEngine;
        _memory = memory;
        _eventBus = eventBus;
        _snapshotStore = snapshotStore;
    }

    public async Task RunAsync(Ticket ticket, CancellationToken cancellationToken = default)
    {
        await _eventBus.PublishAsync(new TicketStartedEvent { TicketId = ticket.Id }, cancellationToken);

        var plan = _planEngine.CreatePlan(ticket, _memory.GetAll());
        var batches = _planEngine.GetTopologicalBatches(plan);

        foreach (var batch in batches)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var context = new DefaultContext(ticket, _memory, cancellationToken);
            await _environment.RunRoundAsync(context, cancellationToken);
        }

        await _eventBus.PublishAsync(new PhaseCompletedEvent { TicketId = ticket.Id, Phase = "execution" }, cancellationToken);
    }

    public Task PauseAsync() => Task.CompletedTask;
    public Task ResumeAsync() => Task.CompletedTask;
    public Task StopAsync() => Task.CompletedTask;
}
