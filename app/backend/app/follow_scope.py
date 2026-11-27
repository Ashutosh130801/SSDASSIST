"""Team Follow-up scope.

A *team follower* (primary role 'teamfollower', or a team lead / FOS / caller holding the extra
team-follower hat and currently in that view) tracks the COMPLETE performance of the people
assigned to them in the ``team_follow`` table — irrespective of case or portfolio.

Only read access is granted through this module; nothing here changes what any other role sees.
"""
from sqlalchemy.orm import Session

from . import models

FOLLOWER_ROLE = "teamfollower"


def is_follower_view(user) -> bool:
    """True when the request is in the team-follower view (active role)."""
    return getattr(user, "role", None) == FOLLOWER_ROLE


def member_ids(db: Session, follower_id: int) -> set[int]:
    return {m for (m,) in db.query(models.TeamFollow.member_id)
            .filter(models.TeamFollow.follower_id == follower_id).all()}


def follows(db: Session, viewer, target_id: int) -> bool:
    """Viewer is in the follower view and target is one of their members."""
    return is_follower_view(viewer) and target_id in member_ids(db, viewer.id)
