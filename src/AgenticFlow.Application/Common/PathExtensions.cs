using System.Text.RegularExpressions;

namespace AgenticFlow.Application.Common;

public static class PathExtensions
{
    public static string ResolveRepoPath(string repoPath)
    {
        if (string.IsNullOrWhiteSpace(repoPath))
        {
            return string.Empty;
        }

        var repo = new DirectoryInfo(repoPath);
        if (Path.IsPathFullyQualified(repoPath))
        {
            return repo.FullName;
        }

        var candidates = new[]
        {
            Path.Combine(Directory.GetCurrentDirectory(), repoPath),
            Path.Combine(Directory.GetCurrentDirectory(), "..", repoPath)
        };

        foreach (var candidate in candidates)
        {
            if (Directory.Exists(candidate))
            {
                return Path.GetFullPath(candidate);
            }
        }

        return Path.GetFullPath(candidates[0]);
    }

    public static string SanitizeName(string name)
    {
        var safe = Regex.Replace(name ?? string.Empty, @"[^\w\-_.]", "_");
        safe = Regex.Replace(safe, @"_+", "_").Trim('_', '.');
        return string.IsNullOrWhiteSpace(safe) ? "project" : safe;
    }

    public static string SlugifyTitle(string title)
    {
        var slug = Regex.Replace(title ?? string.Empty, @"[^\w\s-]", string.Empty);
        slug = Regex.Replace(slug, @"\s+", "-").Trim('-');
        return slug.ToLowerInvariant();
    }
}
