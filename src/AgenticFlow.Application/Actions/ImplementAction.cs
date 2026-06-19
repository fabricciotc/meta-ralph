using System.Text;
using AgenticFlow.Application.Abstractions;
using AgenticFlow.Application.Common;
using AgenticFlow.Domain.Entities;

namespace AgenticFlow.Application.Actions;

public class ImplementAction : Action
{
    private readonly IAIRunner _runner;

    public ImplementAction(IAIRunner runner)
    {
        _runner = runner;
    }

    public override async Task<Message> RunAsync(IContext context, CancellationToken cancellationToken = default)
    {
        var ticket = context.Ticket;
        var metadata = ticket.Metadata;

        var task = GetDictionary(metadata, "task");
        var repoPath = GetString(metadata, "repo_path", ".");
        var branch = GetString(metadata, "branch", $"feature/{ticket.Id}");
        var dependenciesContext = GetString(metadata, "dependencies_context", string.Empty);
        var prdPath = GetString(metadata, "prd_path", string.Empty);
        var architecturePath = GetString(metadata, "architecture_path", string.Empty);
        var ticketId = GetString(metadata, "ticket_id", ticket.Id.ToString());
        var ticketTitle = GetString(metadata, "ticket_title", ticket.Title);
        var ticketDescription = GetString(metadata, "ticket_description", ticket.Description);
        var agentId = GetString(metadata, "agent_id", "engineer");
        var phaseName = GetString(metadata, "phase_name", "engineer_implement");
        var timeoutSeconds = GetInt(metadata, "timeout_seconds", 600);

        var taskId = GetString(task, "id", string.Empty);
        var taskTitle = GetString(task, "title", string.Empty);

        var prompt = BuildPrompt(
            task,
            repoPath,
            branch,
            dependenciesContext,
            prdPath,
            architecturePath,
            ticketTitle,
            ticketDescription);

        string output;
        bool fallback;
        if (_runner.IsAvailable())
        {
            output = await _runner.InvokeAsync(prompt, cancellationToken);
            fallback = false;
        }
        else
        {
            output = WriteFallbackImplementation(repoPath, branch, task, dependenciesContext);
            fallback = true;
        }

        var (buildOutput, testOutput, executableOk, executableReason) =
            GitWorktreeHelper.RunExecutableFeedback(repoPath, taskId, commandTimeoutSeconds: 120);

        var summary = output.Length > 500 ? output[..500] : output;

        var resultMetadata = new Dictionary<string, object>
        {
            ["task_id"] = taskId,
            ["task"] = task,
            ["repo_path"] = repoPath,
            ["branch"] = branch,
            ["summary"] = summary,
            ["fallback"] = fallback,
            ["build_output"] = buildOutput,
            ["test_output"] = testOutput,
        };

        if (!executableOk)
        {
            resultMetadata["reason"] = executableReason;
            return new Message
            {
                Cause = ticket.Id.ToString(),
                Role = agentId,
                Type = "task_failed",
                Recipient = "orchestrator",
                Content = executableReason,
                Metadata = resultMetadata
            };
        }

        return new Message
        {
            Cause = ticket.Id.ToString(),
            Role = agentId,
            Type = "task_completed",
            Recipient = "orchestrator",
            Content = output,
            Metadata = resultMetadata
        };
    }

    private static string BuildPrompt(
        Dictionary<string, object> task,
        string repoPath,
        string branch,
        string dependenciesContext,
        string prdPath,
        string architecturePath,
        string ticketTitle,
        string ticketDescription)
    {
        var filesToTouch = GetStringList(task, "files_to_touch");

        var filesSection = new StringBuilder();
        if (filesToTouch.Count > 0)
        {
            filesSection.AppendLine("\nFiles to modify:");
            foreach (var file in filesToTouch)
            {
                filesSection.AppendLine($"- {file}");
            }
        }

        var depsSection = string.IsNullOrWhiteSpace(dependenciesContext)
            ? string.Empty
            : $"\n\nCompleted dependency context:\n{dependenciesContext}";

        var prdSection = string.IsNullOrWhiteSpace(prdPath) || !File.Exists(prdPath)
            ? string.Empty
            : $"\n\nPRD: {prdPath}";

        var archSection = string.IsNullOrWhiteSpace(architecturePath) || !File.Exists(architecturePath)
            ? string.Empty
            : $"\n\nArchitecture: {architecturePath}";

        return
            "You are a senior software Engineer in a MetaGPT-style software factory. "
            + "Implement the following task in the given repository and branch. "
            + "Do not write explanations instead of code; generate real changes, tests when applicable, "
            + "and respect project conventions. If you are blocked by missing product context, technical ambiguity, "
            + "or another task's behavior, say so explicitly in your final summary and name the agent or role that "
            + "should answer. The Engineering Squad Lead will use that to coordinate follow-up.\n\n"
            + $"TICKET: {ticketTitle}\n"
            + $"DESCRIPTION: {ticketDescription}\n\n"
            + $"TASK: {GetString(task, "title", string.Empty)}\n"
            + $"TASK ID: {GetString(task, "id", string.Empty)}\n"
            + $"TASK DESCRIPTION: {GetString(task, "description", string.Empty)}\n"
            + $"REPO: {repoPath}\n"
            + $"BRANCH: {branch}{filesSection}{depsSection}{prdSection}{archSection}\n\n"
            + "Respond with a brief summary of the changes made.";
    }

    private static string WriteFallbackImplementation(
        string repoPath,
        string branch,
        Dictionary<string, object> task,
        string dependenciesContext)
    {
        var workDir = GitWorktreeHelper.GetEngineerNotesDir(repoPath);
        Directory.CreateDirectory(workDir);

        var taskId = GetString(task, "id", "unknown");
        var safeBranch = branch.Replace("/", "-");
        var notePath = Path.Combine(workDir, $"{taskId}-{safeBranch}.md");

        var filesToTouch = GetStringList(task, "files_to_touch");
        var filesSection = filesToTouch.Count > 0
            ? string.Join("\n", filesToTouch.Select(f => $"- {f}"))
            : "None";

        var content =
            $"# Implementation: {GetString(task, "title", taskId)}\n\n"
            + $"**Branch:** {branch}\n\n"
            + $"**Description:**\n{GetString(task, "description", string.Empty)}\n\n"
            + $"**Files to modify:**\n{filesSection}\n\n"
            + $"**Dependency context:**\n{dependenciesContext}\n\n"
            + "This note was generated locally because no AI runner is available.\n";

        File.WriteAllText(notePath, content);
        return content;
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
