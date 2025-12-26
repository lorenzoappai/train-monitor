import sys
sys.path.insert(0, '.')
from main import SwissConnectionsProvider
import json

provider = SwissConnectionsProvider()
connections = provider.get_connections("Zurich HB", "Bern", limit=1)

if connections:
    print("Sample connection data:")
    print(json.dumps(connections[0], indent=2))
    
    print("\n\nKey fields check:")
    record = connections[0]
    print(f"origin_station: {record.get('origin_station')}")
    print(f"destination_station: {record.get('destination_station')}")
    print(f"planned_departure: {record.get('planned_departure')}")
    print(f"predicted_departure: {record.get('predicted_departure')}")
    print(f"planned_arrival: {record.get('planned_arrival')}")
    print(f"predicted_arrival: {record.get('predicted_arrival')}")
    print(f"departure_delay: {record.get('departure_delay')}")
    print(f"arrival_delay: {record.get('arrival_delay')}")
    print(f"board_type: {record.get('board_type')}")
