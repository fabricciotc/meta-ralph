using AgenticFlow.Application.Abstractions;
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ConfigController : ControllerBase
{
    private readonly IConfigStore _configStore;

    public ConfigController(IConfigStore configStore)
    {
        _configStore = configStore;
    }

    [HttpGet]
    public IActionResult GetConfig()
    {
        var config = _configStore.Load();
        return Ok(config);
    }

    [HttpPatch]
    public IActionResult UpdateConfig([FromBody] AppConfig config)
    {
        _configStore.Save(config);
        return Ok(config);
    }
}
