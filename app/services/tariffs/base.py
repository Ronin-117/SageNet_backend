from abc import ABC, abstractmethod

class BaseTariff(ABC):
    @abstractmethod
    def calculate(self, units: float, config: dict) -> float:
        """
        Returns the bill amount in local currency.
        config: contains 'phase', 'connection_type', etc.
        """
        pass