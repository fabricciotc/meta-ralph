using AgenticFlow.Application.Roles;

namespace AgenticFlow.Application.Abstractions;

public interface IEnvironment
{
    void RegisterRole(Role role);
    Task RunRoundAsync(IContext context, CancellationToken cancellationToken = default);
}
