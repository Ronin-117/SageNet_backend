from app.services.tariffs.kseb import KSEBTariff
from app.core.logger import setup_logger

log = setup_logger("TariffManager")

class TariffManager:
    def __init__(self):
        self.strategies = {
            "IN_KL": KSEBTariff(), # India_Kerala
            # Add "IN_TN": TNEBTariff() later
        }

    def calculate_bill(self, country: str, state: str, units: float, config: dict) -> float:
        key = f"{country}_{state}"
        strategy = self.strategies.get(key)
        
        if not strategy:
            # Fallback: Flat rate of 8.0 per unit if state unknown
            return units * 8.0
            
        return strategy.calculate(units, config)

tariff_mgr = TariffManager()