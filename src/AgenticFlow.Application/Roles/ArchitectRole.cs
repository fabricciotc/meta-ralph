using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Roles;

public class ArchitectRole : Role
{
    private readonly Actions.ArchitectAction _architectAction;
    private readonly Actions.DesignReviewAction _designReviewAction;

    public ArchitectRole(Actions.ArchitectAction architectAction, Actions.DesignReviewAction designReviewAction)
    {
        Name = "architect";
        _architectAction = architectAction;
        _designReviewAction = designReviewAction;
    }

    public override bool HasPendingWork(IContext context) =>
        context.Memory.GetByType("prd_ready").Any() &&
        !context.Memory.GetByType("architecture_ready").Any();

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var architectureMessage = await _architectAction.RunAsync(context, cancellationToken);
        context.Memory.Add(architectureMessage);

        var reviewMessage = await _designReviewAction.RunAsync(context, cancellationToken);
        context.Memory.Add(reviewMessage);
    }
}
