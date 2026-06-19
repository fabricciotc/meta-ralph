using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Roles;

public class EngineerRole : Role
{
    private readonly Actions.ImplementAction _implementAction;
    private readonly Actions.CorrectionAction _correctionAction;

    public EngineerRole(Actions.ImplementAction implementAction, Actions.CorrectionAction correctionAction)
    {
        Name = "engineer";
        _implementAction = implementAction;
        _correctionAction = correctionAction;
    }

    public override bool HasPendingWork(IContext context) => true;

    public override async Task RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var hasQaRejection = context.Ticket.Metadata.TryGetValue("qa_rejection", out var value)
                             && value is true;

        Message message;
        if (hasQaRejection)
        {
            message = await _correctionAction.RunAsync(context, cancellationToken);
        }
        else
        {
            message = await _implementAction.RunAsync(context, cancellationToken);
        }

        context.Memory.Add(message);
    }
}
