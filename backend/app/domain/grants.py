"""Map authoritative permission_grants actions to the UI's display grants.

Only unambiguous actions are mapped. In this slice grants are display hints for the persona
picker and home; every module API (not wired yet) must check permission_grants itself.
"""

ACTION_TO_UI_GRANT: dict[str, str] = {
    "learning:own": "onboarding.learn",
    "learning:supervise": "onboarding.supervise",
    "work:report": "work.report",
    "delegation:confirm": "delegation.confirm",
    "handover:publish": "handover.publish",
    "knowledge:review": "knowledge.review",
    "curriculum:read": "curriculum.read",
    "curriculum:manage": "curriculum.manage",
    "responsibility:transfer": "responsibility.confirm",
}


def ui_grants(actions: list[str]) -> list[str]:
    return sorted({ACTION_TO_UI_GRANT[a] for a in actions if a in ACTION_TO_UI_GRANT})
