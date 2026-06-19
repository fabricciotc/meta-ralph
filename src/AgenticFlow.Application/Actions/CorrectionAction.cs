using AgenticFlow.Application.Abstractions;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class CorrectionAction : Action
{
    private readonly IAIRunner _runner;

    public CorrectionAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var ticket = context.Ticket;
        var metadata = ticket.Metadata;

        var task = GetDictionary(metadata, "task");
        var taskId = GetString(task, "id", string.Empty);
        var reason = GetString(metadata, "reason", string.Empty);
        var suggestedFix = GetString(metadata, "suggested_fix", string.Empty);
        var repoPath = GetString(metadata, "repo_path", ".");
        var branch = GetString(metadata, "branch", string.Empty);
        var phaseName = GetString(metadata, "phase_name", "engineer_correction");
        var timeoutSeconds = GetInt(metadata, "timeout_seconds", 300);

        var prompt = BuildCorrectionPrompt(task, reason, suggestedFix, repoPath, branch);

        string content;
        if (_runner.IsAvailable())
        {
            var output = await _runner.InvokeAsync(prompt, cancellationToken);
            content = ExtractCorrectionPrompt(output);
        }
        else
        {
            content = ExtractCorrectionPrompt(string.Empty);
        }

        return new Message
        {
            Cause = ticket.Id.ToString(),
            Role = $"qa-{taskId}",
            Type = "correction_prompt_ready",
            Recipient = "orchestrator",
            Content = content,
            Metadata = new Dictionary<string, object>
            {
                ["task_id"] = taskId,
                ["task"] = task,
                ["reason"] = reason,
                ["suggested_fix"] = suggestedFix,
            }
        };
    }

    private static string BuildCorrectionPrompt(
        Dictionary<string, object> task,
        string reason,
        string suggestedFix,
        string repoPath,
        string? branch)
    {
        var files = GetStringList(task, "files_to_touch");
        var filesStr = files.Count > 0 ? string.Join(", ", files) : "N/A";

        return
            "You are a Senior Engineer. Generate a clear, actionable correction prompt so "
            + "another Engineer can fix the issues found by QA.\n\n"
            + $"TASK: {GetString(task, "id", string.Empty)} - {GetString(task, "title", string.Empty)}\n"
            + $"DESCRIPTION: {GetString(task, "description", string.Empty)}\n"
            + $"COMPLEXITY: {GetString(task, "complexity", "M")}\n"
            + $"FILES: {filesStr}\n\n"
            + $"REPO: {repoPath}\n"
            + $"BRANCH: {branch ?? "N/A"}\n\n"
            + $"REJECTION REASON:\n{reason}\n\n"
            + $"QA SUGGESTION:\n{suggestedFix}\n\n"
            + "The correction prompt must:\n"
            + "1. Summarize the problem in one sentence.\n"
            + "2. List concrete steps to fix it.\n"
            + "3. Explain how to validate locally before requesting review again.\n\n"
            + "Respond in English.";
    }

    private static string ExtractCorrectionPrompt(string? output)
    {
        if (!string.IsNullOrWhiteSpace(output))
        {
            return output.Trim();
        }

        return "Fix the issues flagged by QA and request review again. "
               + "Verify build/tests locally before submitting.";
    }

    private static Dictionary<string, object> GetDictionary(Dictionary<string, object> source, string key)
    {
        if (source.TryGetValue(key, out var value) && value is Dictionary<string, object> dict)
        {
            return dict;
        }

        return new Dictionary<string, object>();
    }

    private static string GetString(Dictionary<string, object> source, string key, string defaultValue)
    {
        if (source.TryGetValue(key, out var value))
        {
            return value?.ToString() ?? defaultValue;
        }

        return defaultValue;
    }

    private static int GetInt(Dictionary<string, object> source, string key, int defaultValue)
    {
        if (source.TryGetValue(key, out var value))
        {
            return value switch
            {
                int i => i,
                long l => (int)l,
                string s when int.TryParse(s, out var parsed) => parsed,
                _ => defaultValue
            };
        }

        return defaultValue;
    }

    private static IReadOnlyList<string> GetStringList(Dictionary<string, object> source, string key)
    {
        if (source.TryGetValue(key, out var value) && value is IEnumerable<object> enumerable)
        {
            return enumerable.Select(x => x?.ToString() ?? string.Empty).ToList();
        }

        return Array.Empty<string>();
    }
}
