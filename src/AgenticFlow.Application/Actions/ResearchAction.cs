using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ResearchAction : Action
{
    private readonly IAIRunner _runner;

    public ResearchAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var prompt = $"Research the following request from the angle of your assigned focus. " +
                     $"Ticket title: {context.Ticket.Title}. Description: {context.Ticket.Description}";

        var result = await _runner.InvokeAsync(prompt, cancellationToken);

        return new Message
        {
            Role = "pm_research",
            Type = "research",
            Content = result,
            Cause = context.Ticket.Id.ToString()
        };
    }
}
