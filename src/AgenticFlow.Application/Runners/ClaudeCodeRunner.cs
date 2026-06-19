namespace AgenticFlow.Application.Runners;

public class ClaudeCodeRunner : CliRunnerBase
{
    public override string BackendId => "claude";
    public override int Priority => 2;
    protected override string CommandName => "claude";
}
