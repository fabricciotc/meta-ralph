using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Abstractions;

public interface IPlanEngine
{
    Plan CreatePlan(Ticket ticket, IEnumerable<Message> memory);
    IEnumerable<IEnumerable<TaskItem>> GetTopologicalBatches(Plan plan);
}
