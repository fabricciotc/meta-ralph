using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Orchestration;

public class PlanEngine : IPlanEngine
{
    public Plan CreatePlan(Ticket ticket, IEnumerable<Message> memory)
    {
        return new Plan
        {
            Tasks = new List<TaskItem>()
        };
    }

    public IEnumerable<IEnumerable<TaskItem>> GetTopologicalBatches(Plan plan)
    {
        var remaining = new HashSet<TaskItem>(plan.Tasks);
        while (remaining.Count > 0)
        {
            var batch = remaining.Where(t => t.Dependencies.All(d => !remaining.Any(r => r.Id == d))).ToList();
            if (batch.Count == 0)
                throw new InvalidOperationException("Cyclic dependency detected");

            foreach (var item in batch)
                remaining.Remove(item);

            yield return batch;
        }
    }
}
