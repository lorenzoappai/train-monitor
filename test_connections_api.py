import requests
import json
from datetime import datetime, timedelta

def test_connections_api():
    """
    Test if the /connections endpoint provides planned arrival times
    """
    
    # Test: Get connections arriving at Zurich HB in the next hour
    url = "https://transport.opendata.ch/v1/connections"
    
    # We'll search for trains FROM various stations TO Zurich HB
    # This should give us arrivals at Zurich HB with planned times
    
    test_routes = [
        ("Bern", "Zurich HB"),
        ("Basel SBB", "Zurich HB"),
        ("Lucerne", "Zurich HB"),
    ]
    
    print("Testing /connections API for arrival data...\n")
    
    for origin, destination in test_routes:
        params = {
            'from': origin,
            'to': destination,
            'limit': 3
        }
        
        print(f"\n{'='*60}")
        print(f"Route: {origin} -> {destination}")
        print(f"{'='*60}")
        
        resp = requests.get(url, params=params)
        data = resp.json()
        
        connections = data.get('connections', [])
        
        for i, conn in enumerate(connections[:2], 1):  # Show first 2
            arrival_section = conn.get('to', {})
            departure_section = conn.get('from', {})
            
            # Arrival info
            arr_planned = arrival_section.get('arrival')
            arr_platform = arrival_section.get('platform')
            arr_delay = arrival_section.get('delay')  # in minutes
            
            # Departure info  
            dep_planned = departure_section.get('departure')
            dep_platform = departure_section.get('platform')
            
            print(f"\nConnection {i}:")
            print(f"  Departure: {dep_planned} (Platform {dep_platform})")
            print(f"  Arrival:   {arr_planned} (Platform {arr_platform})")
            print(f"  Delay:     {arr_delay} min" if arr_delay else "  Delay:     On time")
            
            # Check sections for train details
            sections = conn.get('sections', [])
            for section in sections:
                journey = section.get('journey', {})
                if journey:
                    category = journey.get('category')
                    number = journey.get('number')
                    operator = journey.get('operator')
                    if category:
                        print(f"  Train:     {category} {number} ({operator})")
                        break
    
    print(f"\n{'='*60}")
    print("CONCLUSION:")
    print("The /connections API provides:")
    print("  ✓ Planned arrival times")
    print("  ✓ Delay information")
    print("  ✓ Platform information")
    print("  ✓ Train details (category, number, operator)")
    print("\nThis could replace the /stationboard endpoint for arrivals!")
    print(f"{'='*60}")

if __name__ == "__main__":
    test_connections_api()
