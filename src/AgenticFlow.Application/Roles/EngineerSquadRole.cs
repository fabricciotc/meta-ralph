using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class EngineerSquadRole : Role
{
    private readonly IEnumerable<EngineerRole> _engineers;

    public EngineerSquadRole(IEnumerable<EngineerRole> engineers)
    {
        Name = "engineer_squad";
        _engineers = engineers;
    }

    public override bool HasPendingWork(IContext context) => _engineers.Any(e => e.HasPendingWork(context));

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        await Task.WhenAll(_engineers.Select(e => e.RunAsync(context, cancellationToken)));
    }
}
