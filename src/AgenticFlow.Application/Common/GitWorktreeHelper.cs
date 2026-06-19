using System.Diagnostics;
using System.Text.RegularExpressions;

namespace AgenticFlow.Application.Common;

public static class GitWorktreeHelper
{
    public const string RepoMissingError = "REPO_MISSING";
    public const string RepoInsideEngineError = "REPO_INSIDE_ENGINE";
    public const string RepoNotFolderError = "REPO_NOT_FOLDER";
    public const string RepoCreateFailedError = "REPO_CREATE_FAILED";
    public const string BranchCreateFailedError = "BRANCH_CREATE_FAILED";

    public static (string? ErrorCode, string? ErrorMessage) ValidateRepoPath(
        string repoPath,
        string engineDirectory)
    {
        if (string.IsNullOrWhiteSpace(repoPath))
        {
            return (RepoMissingError, "The ticket does not have a repository configured.");
        }

        var resolved = PathExtensions.ResolveRepoPath(repoPath);
        var repo = new DirectoryInfo(resolved);

        try
        {
            var engineFullPath = Path.GetFullPath(engineDirectory);
            var repoFullPath = repo.FullName;
            if (repoFullPath.StartsWith(engineFullPath.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase))
            {
                return (RepoInsideEngineError,
                    $"The folder '{repoPath}' is inside the AgenticFlow engine directory. Choose a folder outside the engine installation.");
            }
        }
        catch (Exception exc)
        {
            return (RepoCreateFailedError, $"Could not validate folder '{repoPath}': {exc.Message}");
        }

        if (repo.Exists && !repo.Attributes.HasFlag(FileAttributes.Directory))
        {
            return (RepoNotFolderError, $"Path '{repoPath}' exists but is not a folder.");
        }

        try
        {
            Directory.CreateDirectory(repo.FullName);
        }
        catch (Exception exc)
        {
            return (RepoCreateFailedError, $"Could not create folder '{repoPath}': {exc.Message}");
        }

        return (null, null);
    }

    public static (string? BranchName, string? ErrorCode, string? ErrorMessage) CreateOrSwitchBranch(
        string repoPath,
        string ticketId,
        string title)
    {
        var resolved = PathExtensions.ResolveRepoPath(repoPath);
        var gitDir = Path.Combine(resolved, ".git");
        if (!Directory.Exists(gitDir))
        {
            return (string.Empty, null, null);
        }

        var slug = PathExtensions.SlugifyTitle(title);
        var branch = $"feature/{ticketId}-{slug}".ToLowerInvariant();

        try
        {
            var existsResult = RunGit(resolved, "rev-parse", "--verify", branch);
            if (existsResult.ExitCode == 0)
            {
                var checkoutResult = RunGit(resolved, "checkout", branch);
                if (checkoutResult.ExitCode != 0)
                {
                    return (null, BranchCreateFailedError,
                        $"Could not switch to branch: {checkoutResult.StdErr}");
                }
            }
            else
            {
                var createResult = RunGit(resolved, "checkout", "-b", branch);
                if (createResult.ExitCode != 0)
                {
                    return (null, BranchCreateFailedError,
                        $"Could not create branch: {createResult.StdErr}");
                }
            }

            return (branch, null, null);
        }
        catch (Exception exc)
        {
            return (null, BranchCreateFailedError, $"Could not create branch: {exc.Message}");
        }
    }

    public static bool DetectDotnetProject(string repoPath)
    {
        var resolved = PathExtensions.ResolveRepoPath(repoPath);
        if (!Directory.Exists(resolved))
        {
            return false;
        }

        return Directory.EnumerateFiles(resolved, "*.csproj", SearchOption.AllDirectories).Any()
               || Directory.EnumerateFiles(resolved, "*.sln", SearchOption.AllDirectories).Any();
    }

    public static (string BuildOutput, string TestOutput, bool Ok, string Reason) RunExecutableFeedback(
        string repoPath,
        string taskId,
        int commandTimeoutSeconds = 120)
    {
        var resolved = PathExtensions.ResolveRepoPath(repoPath);
        if (!DetectDotnetProject(resolved))
        {
            return (string.Empty, string.Empty, true, string.Empty);
        }

        var dotnet = FindDotnet();
        if (string.IsNullOrWhiteSpace(dotnet))
        {
            return (string.Empty, string.Empty, true, "dotnet not found; executable validation skipped");
        }

        var buildResult = RunShell(dotnet, "build", resolved, commandTimeoutSeconds);
        var buildFull = CombineOutput(buildResult.StdOut, buildResult.StdErr);
        if (buildResult.ExitCode != 0)
        {
            return (buildFull, string.Empty, false, $"dotnet build failed for task {taskId}");
        }

        var testResult = RunShell(dotnet, "test", resolved, commandTimeoutSeconds);
        var testFull = CombineOutput(testResult.StdOut, testResult.StdErr);
        if (testResult.ExitCode != 0)
        {
            return (buildFull, testFull, false, $"dotnet test failed for task {taskId}");
        }

        return (buildFull, testFull, true, string.Empty);
    }

    public static string GetEngineerNotesDir(string repoPath)
    {
        var resolved = PathExtensions.ResolveRepoPath(repoPath);
        return Path.Combine(resolved, ".agenticflow", "engineer-notes");
    }

    public static string GetWorktreesDir()
    {
        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "AgenticFlow",
            "worktrees");
        Directory.CreateDirectory(path);
        return path;
    }

    public static string GetWorktreeDir(string projectName, string ticketId)
    {
        var path = Path.Combine(GetWorktreesDir(), PathExtensions.SanitizeName(projectName), ticketId);
        Directory.CreateDirectory(path);
        return path;
    }

    private static string? FindDotnet()
    {
        foreach (var candidate in new[] { "dotnet" })
        {
            try
            {
                var result = RunShell(candidate, "--version", Directory.GetCurrentDirectory(), 10);
                if (result.ExitCode == 0)
                {
                    return candidate;
                }
            }
            catch
            {
                // Ignore and try next
            }
        }

        var pathEnv = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
        var separator = OperatingSystem.IsWindows() ? ';' : ':';
        foreach (var dir in pathEnv.Split(separator, StringSplitOptions.RemoveEmptyEntries))
        {
            var file = OperatingSystem.IsWindows()
                ? Path.Combine(dir, "dotnet.exe")
                : Path.Combine(dir, "dotnet");
            if (File.Exists(file))
            {
                return file;
            }
        }

        return null;
    }

    private static (int ExitCode, string StdOut, string StdErr) RunGit(
        string workingDirectory,
        params string[] args)
    {
        return RunShell("git", string.Join(" ", args), workingDirectory, 60);
    }

    private static (int ExitCode, string StdOut, string StdErr) RunShell(
        string command,
        string arguments,
        string workingDirectory,
        int timeoutSeconds)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = command,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        try
        {
            using var process = Process.Start(startInfo);
            if (process == null)
            {
                return (-1, string.Empty, $"Failed to start process: {command}");
            }

            var completed = process.WaitForExit(timeoutSeconds * 1000);
            if (!completed)
            {
                try
                {
                    process.Kill(entireProcessTree: true);
                }
                catch
                {
                    // Best effort
                }

                return (-1, string.Empty, $"timeout ({timeoutSeconds}s)");
            }

            return (process.ExitCode, process.StandardOutput.ReadToEnd(), process.StandardError.ReadToEnd());
        }
        catch (Exception exc)
        {
            return (-1, string.Empty, exc.Message);
        }
    }

    private static string CombineOutput(string stdout, string stderr)
    {
        var parts = new List<string>();
        if (!string.IsNullOrWhiteSpace(stdout))
        {
            parts.Add(stdout);
        }

        if (!string.IsNullOrWhiteSpace(stderr))
        {
            parts.Add(stderr);
        }

        return string.Join(Environment.NewLine, parts).Trim();
    }
}
