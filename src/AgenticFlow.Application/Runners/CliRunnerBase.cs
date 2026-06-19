using System.Diagnostics;
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Runners;

public abstract class CliRunnerBase : IAIRunner
{
    public abstract string BackendId { get; }
    public abstract int Priority { get; }
    protected abstract string CommandName { get; }

    public virtual bool IsAvailable()
    {
        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = CommandName,
                    Arguments = "--version",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false
                }
            };
            process.Start();
            process.WaitForExit();
            return process.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    public virtual async Task<string> InvokeAsync(string prompt, CancellationToken cancellationToken = default)
    {
        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = CommandName,
                Arguments = $"\"{prompt.Replace("\"", "\\\"")}\"",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false
            }
        };

        process.Start();
        var output = await process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        return output;
    }
}
