using AgenticFlow.Application.Abstractions;
using AgenticFlow.Application.Roles;

namespace AgenticFlow.Application.Orchestration;

public class Environment : IEnvironment
{
    private readonly List<Role> _roles = new();

    public void RegisterRole(Role role)
    {
        _roles.Add(role);
    }

    public async Task RunRoundAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var pending = _roles.Where(r => r.HasPendingWork(context)).ToList();
        await Task.WhenAll(pending.Select(r => r.RunAsync(context, cancellationToken)));
    }
}
