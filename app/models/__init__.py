from app.models.assignment import Assignment, AssignmentType, FinalScoreStrategy
from app.models.base import Base
from app.models.homework_details import HomeworkDetails
from app.models.question import Question, QuestionType, ShortTextMatch
from app.models.stats_module import StatsModule
from app.models.widget import Widget

__all__ = [
    "Base",
    "Widget",
    "Assignment",
    "AssignmentType",
    "FinalScoreStrategy",
    "Question",
    "QuestionType",
    "ShortTextMatch",
    "HomeworkDetails",
    "StatsModule",
]
