namespace AgenticFlow.Application.Runners;

public class KimiCliRunner : CliRunnerBase
{
    public override string BackendId => "kimi";
    public override int Priority => 1;
    protected override string CommandName => "kimi";
}
