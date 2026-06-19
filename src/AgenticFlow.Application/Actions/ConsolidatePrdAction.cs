using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ConsolidatePrdAction : Action
{
    private readonly IAIRunner _runner;

    public ConsolidatePrdAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var research = context.Memory.GetByType("research");
        var findings = string.Join("\n\n---\n\n", research.Select(r => r.Content));

        var prompt =
            $"You are the Lead Product Manager. Consolidate the following research findings into a concise, " +
            $"actionable Product Requirements Document (PRD) for the ticket '{context.Ticket.Title}'.\n\n" +
            $"Ticket description: {context.Ticket.Description}\n\n" +
            $"Research findings:\n{findings}\n\n" +
            $"Generate a markdown PRD with sections: summary, functional requirements, non-functional requirements, " +
            $"user stories/acceptance criteria, suggested technical tasks, and risks/open questions.";

        var result = await _runner.InvokeAsync(prompt, cancellationToken);

        return new Message
        {
            Role = "pm_lead",
            Type = "prd_ready",
            Content = result,
            Cause = context.Ticket.Id.ToString(),
            Metadata = new Dictionary<string, object>
            {
                ["artifact"] = "PRD"
            }
        };
    }
}
