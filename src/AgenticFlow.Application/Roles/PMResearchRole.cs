using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class PMResearchRole : Role
{
    private readonly Actions.ResearchAction _action;

    public PMResearchRole(Actions.ResearchAction action)
    {
        Name = "pm_research";
        _action = action;
    }

    public override bool HasPendingWork(IContext context) => !context.Memory.GetByRole(Name).Any();

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var message = await _action.RunAsync(context, cancellationToken);
        context.Memory.Add(message);
    }
}
