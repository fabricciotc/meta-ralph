using AgenticFlow.Application.Abstractions;
using Microsoft.AspNetCore.Mvc;

namespace AgenticFlow.Bff.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TicketsController : ControllerBase
{
    private readonly ITicketService _ticketService;

    public TicketsController(ITicketService ticketService)
    {
        _ticketService = ticketService;
    }

    [HttpGet]
    public async Task<IActionResult> GetTickets()
    {
        var tickets = await _ticketService.GetAllAsync();
        return Ok(tickets);
    }

    [HttpPost("{id:guid}/play")]
    public async Task<IActionResult> Play(Guid id)
    {
        await _ticketService.PlayAsync(id);
        return Ok(new { status = "started", id });
    }
}
