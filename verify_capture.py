import sys
sys.path.insert(0, '.')
from main import SwissConnectionsProvider
import json

provider = SwissConnectionsProvider()
connections = provider.get_connections("Zurich HB", "Bern", limit=1)

if connections:
    record = connections[0]
    
    print("=" * 60)
    print("DEPARTURE (at Zurich HB)")
    print("=" * 60)
    print(f"Planned:   {record.get('planned_departure')}")
    print(f"Predicted: {record.get('predicted_departure')}")
    print(f"Delay:     {record.get('departure_delay')} minutes")
    print(f"Platform:  {record.get('planned_platform')}")
    
    print("\n" + "=" * 60)
    print("ARRIVAL (at Bern)")
    print("=" * 60)
    print(f"Planned:   {record.get('planned_arrival')}")  # <-- THIS IS CAPTURED!
    print(f"Predicted: {record.get('predicted_arrival')}")
    print(f"Delay:     {record.get('arrival_delay')} minutes")
    print(f"Platform:  {record.get('predicted_platform')}")
    
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    if record.get('planned_arrival'):
        print("✅ planned_arrival IS CAPTURED!")
    else:
        print("❌ planned_arrival is MISSING")
