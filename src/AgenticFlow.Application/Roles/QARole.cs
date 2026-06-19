using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class QARole
{
    public string Name { get; } = "qa";
    public Task RunAsync(IContext context, CancellationToken cancellationToken = default) => Task.CompletedTask;
}
