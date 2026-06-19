using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ArchitectAction : Action
{
    private readonly IAIRunner _runner;

    public ArchitectAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prd = context.Memory.GetByType("prd_ready").LastOrDefault()?.Content ?? context.Ticket.Description;

        var prompt =
            "You are the AgenticFlow Architect. Design the global technical architecture for the following PRD. " +
            "Do NOT implement code; define patterns, APIs, directory structure, conventions, and technical decisions.\n\n" +
            $"Ticket: {context.Ticket.Title}\n" +
            $"Description: {context.Ticket.Description}\n\n" +
            $"PRD:\n{prd}\n\n" +
            "Generate a markdown architecture document with sections: summary, key technical decisions, " +
            "recommended directories/modules, APIs/interfaces/contracts, code patterns/conventions, and risks/mitigations. " +
            "If there are pending design decisions, list them clearly under the heading 'PENDING DECISIONS:'.";

        var result = await _runner.InvokeAsync(prompt, cancellationToken);

        return new Message
        {
            Role = "architect",
            Type = "architecture_ready",
            Content = result,
            Cause = context.Ticket.Id.ToString(),
            Metadata = new Dictionary<string, object>
            {
                ["artifact"] = "architecture"
            }
        };
    }
}
