using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class PMLeadRole : Role
{
    private readonly Actions.ConsolidatePrdAction _action;

    public PMLeadRole(Actions.ConsolidatePrdAction action)
    {
        Name = "pm_lead";
        _action = action;
    }

    public override bool HasPendingWork(IContext context) =>
        context.Memory.GetByType("research").Any() &&
        !context.Memory.GetByType("prd_ready").Any();

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var message = await _action.RunAsync(context, cancellationToken);
        context.Memory.Add(message);
    }
}
