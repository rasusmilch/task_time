"""Owned project review using the existing movement/modal request lifecycle."""
from .move_window import MoveWindow


class ProjectMoveWindow(MoveWindow):
    operation = 'move_project_subtree'

    def __init__(self, owner, project_id, state):
        if not owner.candidate_presentation:
            raise ValueError('Project movement requires the explicit candidate profile')
        super().__init__(owner, project_id, state)
