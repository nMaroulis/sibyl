"""Sibyl's native coordinator; ProtoLink supplies registry discovery and delegation.

Specialists advertise their own evidence and help tools. Sibyl chooses among
those native capabilities without a custom routing table or delegation tools.
"""

from protolink import Agent

from sibyl.agents.utils.common import COMMON_PROMPT
from sibyl.investigations.repository import InvestigationRepository
from sibyl.investigations.scheduling.readers import briefing_snapshot
from sibyl.investigations.scheduling.repository import BriefingRepository
from sibyl.storage import Store

SYSTEM_PROMPT = (
    "You are Sibyl, the lead agent of a personal crypto workspace. Answer general questions directly. "
    "ProtoLink automatically provides the agents registered in your workspace. When specialist evidence is "
    "needed, delegate to an appropriate advertised agent using native agent calls, then synthesize its answer. "
    "You do not own the specialists' module tools. To execute one, use ProtoLink's native agent-call "
    "protocol addressed to its owning specialist; never call its function as a local tool on yourself. "
    "Before answering a workspace-specific how-to question, consult a specialist or request its help/guide tool. Explain its "
    "steps and link to the destination. Instructions do not require a balance or price read. "
    "For questions about actual holdings, orders, reports or news, request the relevant evidence. "
    "Choose collaborators yourself; do not invent agents, consultations or data. Include the user's exact "
    "market, source, account, selected report or article in delegated prompts. Never assume BTC when the user "
    "names another coin; ask for clarification if an account or trading pair is ambiguous. "
    "Name the specialists you actually consulted, cite returned sources and explain missing evidence. "
    "Specialists can have different configured models, including tool-only settings. If a reasoning "
    "consultation is unavailable, explain it; you may use an advertised read-only tool when appropriate. "
    "Never claim the user's settings were changed or that a fallback model was selected. "
    "Use investigation_reports to find and inspect the user's saved research. Those reports are dated "
    "model interpretations, not fresh market observations; consult specialists for current evidence. "
    "Use briefing_schedules for saved calendars and report/delivery outcomes. The app can run explicitly "
    "scheduled investigations; you can explain the controls and inspect state, but cannot create, pause "
    "or change schedules or authorize message delivery. Never claim you have scheduled something. "
    "Only you delegate; specialists use their own read-only tools. You cannot trade, start strategies, "
    "change settings or send messages. Disclose demo data, mock models, paper strategies and baseline forecasts."
)


def create_agent(store: Store, **runtime) -> Agent:
    """Let ProtoLink supply discovery, agent-call schemas, dispatch and child-task lifecycle."""
    agent = Agent(
        name="sibyl-sibyl",
        description="Sibyl, your connected intelligence. Connect specialist evidence into a clear answer.",
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = True
    reports = InvestigationRepository(store)
    calendars = BriefingRepository(store)

    @agent.tool
    def investigation_reports(investigation_id: str = "", run_id: str = "") -> dict:
        """Find saved research questions or read a specific version's findings and source references.

        Omit IDs to list the latest twenty investigations. Use an investigation_id from
        that list to see its question and versions, then a run_id from those versions
        to read its report. Reports are historical model interpretations; their original
        selections, model attribution and dates do not establish current market facts.
        """
        if not investigation_id:
            if run_id:
                raise ValueError("Select an investigation before selecting a report version.")
            return {"items": reports.list()[:20], "url": "/sibyl?tab=investigations"}
        definition = reports.get(investigation_id)
        result = {
            "investigation": definition,
            "url": f"/sibyl?tab=investigations&investigation={investigation_id}",
        }
        if run_id:
            run = reports.run(investigation_id, run_id)
            result["run"] = {
                **run,
                "sources": [
                    {key: value for key, value in source.items() if key != "preview"}
                    for source in run["sources"]
                ],
            }
            result["url"] += f"&run={run_id}"
        return result

    @agent.tool
    def briefing_schedules(investigation_id: str = "", schedule_id: str = "") -> dict:
        """Explain a saved briefing's calendar, next run, missed/failed runs and Telegram delivery outcomes.

        Omit IDs to list up to twenty schedules. Use an investigation_id from
        investigation_reports to filter them, or a schedule_id from this list to
        inspect its latest five occurrences and confirmed delivery-part counts.
        Returns actual saved state plus separate setup instructions and an app link.
        This tool cannot create, run, pause or edit a schedule or send a message.
        """
        return briefing_snapshot(calendars, investigation_id, schedule_id)

    return agent
