from abc import ABC, abstractmethod
from ..models import Project

class BaseRenderer(ABC):
    def __init__(self, project: Project):
        self.project = project
        
    @abstractmethod
    def render(self, filepath: str):
        """
        Renders the Project structure into the target format (e.g., .RPP)
        and writes it to the filepath.
        """
        pass
