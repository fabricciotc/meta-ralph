using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class DesignReviewAction : Action
{
    private readonly IAIRunner _runner;

    public DesignReviewAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var architecture = context.Memory.GetByType("architecture_ready").LastOrDefault()?.Content ?? string.Empty;

        var prompt =
            "You are the AgenticFlow Architect. Review the architecture document below and extract ONLY the design " +
            "decisions that still need confirmation. Respond with a numbered list of clear, brief questions. " +
            "If there are no pending decisions, respond exactly: 'NO_PENDING_DECISIONS'.\n\n" +
            $"Ticket: {context.Ticket.Title}\n" +
            $"Description: {context.Ticket.Description}\n\n" +
            $"Architecture:\n{architecture}";

        var result = await _runner.InvokeAsync(prompt, cancellationToken);

        var hasPending = !string.IsNullOrWhiteSpace(result) &&
                         !result.Contains("NO_PENDING_DECISIONS", StringComparison.OrdinalIgnoreCase);

        return new Message
        {
            Role = "architect",
            Type = hasPending ? "design_review_requested" : "design_review_answered",
            Content = result,
            Cause = context.Ticket.Id.ToString(),
            Metadata = new Dictionary<string, object>
            {
                ["artifact"] = hasPending ? "design_review_questions" : "design_review_answers"
            }
        };
    }
}
