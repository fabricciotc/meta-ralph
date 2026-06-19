using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Memory;

public class MemoryStore : IMemoryStore
{
    private readonly List<Message> _messages = new();

    public void Add(Message message) => _messages.Add(message);
    public IReadOnlyList<Message> GetAll() => _messages.AsReadOnly();
    public IReadOnlyList<Message> GetByCause(string cause) => _messages.Where(m => m.Cause == cause).ToList().AsReadOnly();
    public IReadOnlyList<Message> GetByRole(string role) => _messages.Where(m => m.Role == role).ToList().AsReadOnly();
    public IReadOnlyList<Message> GetByType(string type) => _messages.Where(m => m.Type == type).ToList().AsReadOnly();
    public IReadOnlyList<Message> GetByRecipient(string recipient) => _messages.Where(m => m.Recipient == recipient).ToList().AsReadOnly();
}
