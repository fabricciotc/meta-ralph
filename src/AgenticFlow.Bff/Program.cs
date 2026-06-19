using AgenticFlow.Application.Actions;
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Application.Memory;
using AgenticFlow.Application.Orchestration;
using AgenticFlow.Application.Roles;
using AgenticFlow.Application.Runners;
using AgenticFlow.Application.Services;
using AgenticFlow.Application.Skills;
using AgenticFlow.Bff.Hubs;
using AgenticFlow.Bff.Infrastructure;
using AgenticFlow.Persistence;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddPersistence(builder.Configuration);
builder.Services.AddSingleton<IEventBus, SignalREventBus>();

builder.Services.AddSingleton<IMemoryStore, MemoryStore>();
builder.Services.AddSingleton<IEnvironment, Environment>();
builder.Services.AddSingleton<IPlanEngine, PlanEngine>();
builder.Services.AddSingleton<IOrchestrator, Orchestrator>();
builder.Services.AddSingleton<IBackendRegistry, BackendRegistry>();
builder.Services.AddSingleton<ISkillRegistry, SkillRegistry>();
builder.Services.AddSingleton<ITicketService, TicketService>();

builder.Services.AddSingleton<IAIRunner, KimiCliRunner>();
builder.Services.AddSingleton<IAIRunner, ClaudeCodeRunner>();
builder.Services.AddSingleton<IAIRunner, OpenAiApiRunner>();

builder.Services.AddScoped<ResearchAction>();
builder.Services.AddScoped<ImplementAction>();
builder.Services.AddScoped<ReviewAction>();
builder.Services.AddScoped<PMResearchRole>();
builder.Services.AddScoped<EngineerRole>();
builder.Services.AddScoped<QARole>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseDefaultFiles();
app.UseStaticFiles();
app.UseRouting();
app.MapControllers();
app.MapHub<DashboardHub>("/hub");

app.Run();
