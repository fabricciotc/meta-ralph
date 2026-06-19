using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Orchestration;

public class BatchScheduler
{
    private readonly IPlanEngine _planEngine;

    public BatchScheduler(IPlanEngine planEngine)
    {
        _planEngine = planEngine;
    }

    public IEnumerable<IEnumerable<TaskItem>> Schedule(Plan plan)
    {
        return _planEngine.GetTopologicalBatches(plan);
    }
}
