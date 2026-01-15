from app.services.tariffs.base import BaseTariff

class KSEBTariff(BaseTariff):
    def calculate(self, units: float, config: dict) -> float:
        # Default to Single Phase Domestic if unknown
        phase = config.get('phase', '1') 
        is_3_phase = str(phase) == '3'
        
        # 1. Fixed Charges (Monthly)
        fixed_charge = 50.0 if is_3_phase else 25.0
        
        # 2. Energy Charges (Telescopic Slabs - Domestic LT-1A)
        # Note: These rates are approx based on your image. 
        # In a real app, fetch these rates from a DB Config.
        energy_charge = 0.0
        rem_units = units

        # Slab 1: 0-40 units @ 1.50
        if rem_units > 0:
            slab_units = min(rem_units, 40)
            energy_charge += slab_units * 1.50
            rem_units -= slab_units

        # Slab 2: 41-100 units @ 4.67 (Total 60 units in this slab)
        if rem_units > 0:
            slab_units = min(rem_units, 60)
            energy_charge += slab_units * 4.67
            rem_units -= slab_units
            
        # Slab 3: 101-250 units @ 6.40 (Total 150 units)
        if rem_units > 0:
            slab_units = min(rem_units, 150)
            energy_charge += slab_units * 6.40
            rem_units -= slab_units
            
        # Slab 4: 251-400 units @ 8.54 (Total 150 units)
        if rem_units > 0:
            slab_units = min(rem_units, 150)
            energy_charge += slab_units * 8.54
            rem_units -= slab_units

        # Slab 5: Above 400 @ 9.60
        if rem_units > 0:
            energy_charge += rem_units * 9.60

        # 3. Duty & Meter Rent
        duty = energy_charge * 0.10 # 10% Duty
        meter_rent = 6.0 # Standard single phase rent
        
        total = fixed_charge + energy_charge + duty + meter_rent
        return round(total, 2)