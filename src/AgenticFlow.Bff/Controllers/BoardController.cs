using AgenticFlow.Application.Abstractions;
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class BoardController : ControllerBase
{
    private readonly IBoardStore _boardStore;

    public BoardController(IBoardStore boardStore)
    {
        _boardStore = boardStore;
    }

    [HttpGet]
    public IActionResult GetBoard()
    {
        var state = _boardStore.Load();
        return Ok(new { tickets = state.Tickets });
    }
}
