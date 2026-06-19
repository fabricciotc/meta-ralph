using AgenticFlow.Application.Abstractions;
using AgenticFlow.Persistence.FileSystem;
using AgenticFlow.Persistence.JsonStores;
using AgenticFlow.Persistence.Repositories;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace AgenticFlow.Persistence;

public static class DependencyInjection
{
    public static IServiceCollection AddPersistence(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddSingleton<AppDataPathProvider>();
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<BoardState>(pathProvider, "board.json");
        });
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<RunState>(pathProvider, "run-state.json");
        });
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<AppConfig>(pathProvider, "config.json");
        });
        services.AddSingleton(provider =>
        {
            var pathProvider = provider.GetRequiredService<AppDataPathProvider>();
            return new JsonFileStore<Dictionary<string, Snapshot>>(pathProvider, "snapshots.json");
        });

        services.AddSingleton<IBoardStore, BoardStore>();
        services.AddSingleton<IRunStateStore, RunStateStore>();
        services.AddSingleton<IConfigStore, ConfigStore>();
        services.AddSingleton<ISnapshotStore, SnapshotStore>();

        return services;
    }
}
