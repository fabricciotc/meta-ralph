using AgenticFlow.Application.Abstractions;
using AgenticFlow.Persistence.JsonStores;

namespace AgenticFlow.Persistence.Repositories;

public class SnapshotStore : ISnapshotStore
{
    private readonly JsonFileStore<Dictionary<string, Snapshot>> _store;

    public SnapshotStore(JsonFileStore<Dictionary<string, Snapshot>> store)
    {
        _store = store;
    }

    public Snapshot? Load(string ticketId)
    {
        var all = _store.Load();
        return all.TryGetValue(ticketId, out var snapshot) ? snapshot : null;
    }

    public void Save(string ticketId, Snapshot snapshot)
    {
        var all = _store.Load();
        all[ticketId] = snapshot;
        _store.Save(all);
    }
}
