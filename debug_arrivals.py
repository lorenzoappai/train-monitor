import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_arrivals(station="Zurich HB"):
    url = "https://transport.opendata.ch/v1/stationboard"
    params = {
        'station': station,
        'limit': 50,
        'type': 'arrival' 
    }
    
    logger.info(f"Fetching arrivals for {station}...")
    resp = requests.get(url, params=params)
    data = resp.json()
    
    count_arrival_planned = 0
    count_arrival_predicted = 0
    count_weird = 0
    
    print(f"\n--- Analysis for {station} ---")
    
    for conn in data.get("stationboard", []):
        stop = conn.get("stop", {})
        prog = stop.get("prognosis", {})
        if not prog: prog = {}
        
        name = f"{conn.get('category')} {conn.get('number')}"
        to = conn.get("to")
        
        arr_planned = stop.get("arrival")
        arr_predicted = prog.get("arrival")
        
        if arr_planned: count_arrival_planned += 1
        if arr_predicted: count_arrival_predicted += 1
        
        if arr_predicted and not arr_planned:
            count_weird += 1
            st_name = stop.get("station", {}).get("name")
            print(f"[WEIRD] {name} to {to}")
            print(f"  Station Name in JSON: '{st_name}'")
            print(f"  Planned Arr (Stop): {arr_planned}")
            print(f"  Predict Arr (Prog): {arr_predicted}")
            
            # Check passList content
            pass_list = conn.get("passList", [])
            print(f"  PassList ({len(pass_list)} stops):")
            for i, p in enumerate(pass_list):
                p_name = p.get("station", {}).get("name")
                p_arr = p.get("arrival")
                if i < 3 or p_name == st_name: # Print first 3 and matches
                     print(f"    - {p_name}: Arr={p_arr}")
            
            found = False
            for p in pass_list:
                if p.get("station", {}).get("name") == st_name:
                    print(f"  >> FOUND in passList: {p.get('arrival')}")
                    found = True
                    break
            if not found:
                print("  >> NOT found in passList (Name mismatch?)")
            
        # NORMAL CASE: Both exist
        elif arr_planned and arr_predicted:
            # print(f"[OK] {name} -> {to} | P: {arr_planned} E: {arr_predicted}")
            pass
            
        # NULL CASE: Neither exist
        elif not arr_planned and not arr_predicted:
            # Likely a starting train?
            # print(f"[START?] {name} -> {to}")
            pass

    print(f"\nSummary:")
    print(f"Total Records: {len(data.get('stationboard', []))}")
    print(f"With Planned Arrival: {count_arrival_planned}")
    print(f"With Predicted Arrival: {count_arrival_predicted}")
    print(f"Weird (Pred but no Plan): {count_weird}")

if __name__ == "__main__":
    check_arrivals("Zurich HB")
    check_arrivals("Bern")
