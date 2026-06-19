using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Runners;

public class BackendRegistry : IBackendRegistry
{
    private readonly IEnumerable<IAIRunner> _runners;

    public BackendRegistry(IEnumerable<IAIRunner> runners)
    {
        _runners = runners;
    }

    public IReadOnlyList<IAIRunner> GetAvailableRunners() =>
        _runners.Where(r => r.IsAvailable()).OrderBy(r => r.Priority).ToList();

    public IAIRunner? GetRunner(string backendId) =>
        _runners.FirstOrDefault(r => r.BackendId == backendId);
}
