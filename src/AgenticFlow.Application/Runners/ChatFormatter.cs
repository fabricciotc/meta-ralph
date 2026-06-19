using System.Text.RegularExpressions;
using AgenticFlow.Application.Abstractions;

namespace AgenticFlow.Application.Runners;

public class ChatFormatter : IChatFormatter
{
    public string Format(string rawOutput)
    {
        if (string.IsNullOrWhiteSpace(rawOutput))
            return rawOutput;

        var cleaned = Regex.Replace(rawOutput, @"\x1B\[[0-9;]*m", string.Empty);
        return cleaned.Trim();
    }
}
