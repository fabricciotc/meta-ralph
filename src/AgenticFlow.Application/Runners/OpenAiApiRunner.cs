using AgenticFlow.Application.Abstractions;
using Microsoft.Extensions.Configuration;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.ChatCompletion;

namespace AgenticFlow.Application.Runners;

public class OpenAiApiRunner : IAIRunner
{
    private readonly Kernel _kernel;
    private readonly string _apiKey;

    public string BackendId => "openai-api";
    public int Priority => 10;

    public OpenAiApiRunner(IConfiguration configuration)
    {
        _apiKey = configuration["OpenAI:ApiKey"] ?? string.Empty;
        var modelId = configuration["OpenAI:ModelId"] ?? "gpt-4o";

        var builder = Kernel.CreateBuilder();
        if (!string.IsNullOrWhiteSpace(_apiKey))
        {
            builder.AddOpenAIChatCompletion(modelId, _apiKey);
        }
        _kernel = builder.Build();
    }

    public bool IsAvailable() => !string.IsNullOrWhiteSpace(_apiKey);

    public async Task<string> InvokeAsync(string prompt, CancellationToken cancellationToken = default)
    {
        var chat = _kernel.GetRequiredService<IChatCompletionService>();
        var history = new ChatHistory();
        history.AddUserMessage(prompt);
        var response = await chat.GetChatMessageContentsAsync(history, kernel: _kernel, cancellationToken: cancellationToken);
        return string.Join("\n", response.Select(r => r.Content));
    }
}
