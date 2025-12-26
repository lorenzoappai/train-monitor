import os
import logging
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TrainProvider(ABC):
    @abstractmethod
    def get_departures(self, station_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        pass

class SwissTrainProvider(TrainProvider):
    BASE_URL = "https://transport.opendata.ch/v1"

    def __init__(self):
        self.session = self._create_retry_session()

    def _create_retry_session(self, retries=3, backoff_factor=0.3):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(500, 502, 504),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def get_departures(self, station_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/stationboard"
        params = {
            'station': station_name,
            'limit': limit
        }
        
        try:
            logger.info(f"Fetching data from Swiss API for station: {station_name}")
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            departures = []
            for connection in data.get("stationboard", []):
                try:
                    stop = connection.get("stop", {})
                    prognosis = stop.get("prognosis", {})
                    if prognosis is None: prognosis = {}
                    
                    category = connection.get("category")
                    number = connection.get("number")
                    
                    # Times
                    dep_planned = stop.get("departure")
                    dep_predicted = prognosis.get("departure")
                    dep_effective = dep_predicted if dep_predicted else dep_planned
                    
                    arr_planned = stop.get("arrival") 
                    arr_predicted = prognosis.get("arrival")

                    # Platforms
                    plat_planned = stop.get("platform")
                    plat_predicted = prognosis.get("platform")
                    
                    # Status/Delays - Check multiple sources
                    delay_min = 0
                    
                    # Method 1: Get from prognosis if available
                    prognosis_delay = prognosis.get("delay")
                    if prognosis_delay is not None:
                        delay_min = prognosis_delay
                    # Method 2: Get from stop if available
                    elif stop.get("delay") is not None:
                        delay_min = stop.get("delay")
                    # Method 3: Calculate from timestamp difference if both times exist
                    elif dep_planned and dep_predicted and dep_predicted != dep_planned:
                        try:
                            from datetime import datetime as dt
                            planned_dt = dt.fromisoformat(dep_planned.replace('Z', '+00:00'))
                            predicted_dt = dt.fromisoformat(dep_predicted.replace('Z', '+00:00'))
                            delay_seconds = (predicted_dt - planned_dt).total_seconds()
                            delay_min = int(delay_seconds / 60)
                        except:
                            delay_min = 0
                    
                    # Departure status
                    status = "ON TIME"
                    if delay_min > 0: status = "DELAYED"
                    elif delay_min < 0: 
                        status = "EARLY"
                        delay_min = abs(delay_min)  # Keep delay as positive value
                    if prognosis.get("status") == "cancelled": status = "CANCELLED"
                    
                    # Arrival status (if arrival times are available)
                    status_arrival = "N/A"  # For departure boards, arrival at monitored station not usually available
                    arrival_delay_min = 0
                    if arr_planned and arr_predicted:
                        try:
                            from datetime import datetime as dt
                            arr_planned_dt = dt.fromisoformat(arr_planned.replace('Z', '+00:00'))
                            arr_predicted_dt = dt.fromisoformat(arr_predicted.replace('Z', '+00:00'))
                            arrival_delay_sec = (arr_predicted_dt - arr_planned_dt).total_seconds()
                            arrival_delay_min = int(arrival_delay_sec / 60)
                            
                            if arrival_delay_min > 0: status_arrival = "DELAYED"
                            elif arrival_delay_min < 0: 
                                status_arrival = "EARLY"
                                arrival_delay_min = abs(arrival_delay_min)
                            else:
                                status_arrival = "ON TIME"
                        except:
                            status_arrival = "N/A"
                            arrival_delay_min = 0
                    
                    # Generate journey_id for deduplication (combine category+number+date+destination)
                    journey_date = dep_planned[:10] if dep_planned else datetime.utcnow().strftime("%Y-%m-%d")
                    destination_clean = connection.get("to", "UNKNOWN").replace(" ", "")[:20]
                    journey_id = f"{category}{number}_{journey_date}_{destination_clean}"

                    row = {
                        "created_at": datetime.utcnow().isoformat(),
                        "station": station_name,
                        "train_name": f"{category} {number}",
                        "destination": connection.get("to"),
                        "category": category,
                        "number": str(number),
                        "operator": connection.get("operator"),
                        "partner_operator": "", # Not easily available
                        "raw_departure_iso": dep_planned, # fallback to planned
                        "planned_departure": dep_planned,
                        "predicted_departure": dep_effective,
                        "delay_minutes": delay_min,
                        "delay": delay_min,
                        "status": status,
                        "status_arrival": status_arrival,
                        "planned_platform": plat_planned,
                        "predicted_platform": plat_predicted,
                        "planned_arrival": arr_planned,
                        "predicted_arrival": arr_predicted,
                        "arrival_delay": arrival_delay_min,
                        "is_cancelled": status == "CANCELLED",
                        "cancellation_reason": "",
                        "train_speed": "",
                        "journey_duration": "",
                        "stops_count": len(connection.get("pass_list", [])),
                        "api_response_time": 0, # Could measure
                        "journey_id": journey_id,
                        "record_id": f"{category}_{number}_{station_name}_{dep_planned}",
                        "data_quality": 100, # Placeholder
                        "raw_json": json.dumps(connection)
                    }
                    departures.append(row)
                except Exception as e:
                    logger.warning(f"Skipping malformed connection entry: {e}")
                    continue
            
            return departures

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from Swiss API: {e}")
            return []

class ViaggiatrenoTrainProvider(TrainProvider):
    # Unofficial API endpoints
    # Use HTTP to avoid redirects that lose headers/method or cause 301->400 issues
    BASE_URL = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"

    def __init__(self):
        self.session = self._create_retry_session()
        self.time_offset_ms = 0
        self._sync_time()

    def _sync_time(self):
        """Syncs local time with server time to handle potential skews"""
        try:
            # Head request to get server time
            resp = self.session.head(self.BASE_URL, timeout=5)
            server_date = resp.headers.get('Date')
            if server_date:
                # Parse HTTP Date format: "Thu, 25 Dec 2025 16:00:00 GMT"
                server_dt = datetime.strptime(server_date, "%a, %d %b %Y %H:%M:%S %Z")
                # Naive to local (UTC) comparison for offset
                local_now = datetime.utcnow()
                self.time_offset_ms = (server_dt - local_now).total_seconds() * 1000
                logger.info(f"Time Sync: Local={local_now}, Server={server_dt}, Offset={self.time_offset_ms:.0f}ms")
            else:
                logger.warning("No Date header in response, skipping time sync.")
        except Exception as e:
            logger.warning(f"Time sync failed, using local time: {e}")

    def _create_retry_session(self, retries=3, backoff_factor=0.3):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(500, 502, 504),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def get_departures(self, station_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        # 1. Get Station ID
        try:
            station_id, found_name = self._get_station_id(station_name)
            if not station_id:
                logger.warning(f"Station not found: {station_name}")
                return []
            
            logger.info(f"Resolved '{station_name}' to '{found_name}' ({station_id})")
            
            # 2. Get Departures List
            raw_departures = self._fetch_departures_raw(station_id, found_name)
            
            # 3. Enrich with details (this is the heavy part)
            detailed_departures = []
            
            # Limit processing to avoid too many API calls
            to_process = raw_departures[:limit]
            logger.info(f"Processing {len(to_process)} departures for detailed metrics...")

            for item in to_process:
                try:
                    details = self._get_train_details(item, station_id)
                    detailed_departures.append(details)
                    # Be nice to the API
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error processing train {item.get('numeroTreno')}: {e}")
                    continue
            
            return detailed_departures

        except Exception as e:
            logger.error(f"Error fetching Italian train data: {e}")
            return []

    def _get_station_id(self, station_name: str) -> Optional[str]:
        # Simple cache could be added here
        url = f"{self.BASE_URL}/cercaStazione/{station_name}"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                # Return ID and Name
                return data[0].get('id'), data[0].get('nomeLungo')
        except Exception as e:
            logger.error(f"Failed to lookup station ID for {station_name}: {e}")
        return None, None

    def _fetch_departures_raw(self, station_id: str, station_name: str) -> List[Dict[str, Any]]:
        # Apply offset to get server-compatible time
        ts_ms = int((datetime.utcnow().timestamp() * 1000) + self.time_offset_ms)
        
        # WORKAROUND: GitHub runners may have clock set to 2025 instead of 2024
        # If detected year is 2025, subtract one year (31536000000 ms)
        current_dt = datetime.utcnow()
        if current_dt.year == 2025:
            logger.warning(f"Detected year 2025, subtracting 1 year from timestamp for API compatibility")
            ts_ms -= 31536000000  # Subtract 365 days in milliseconds
        
        url = f"{self.BASE_URL}/partenze/{station_id}/{ts_ms}"
        try:
            logger.info(f"Fetching departure board for {station_name} ({station_id})")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"Failed to fetch departures board: {e}")
            return []

    def _get_train_details(self, departure_item: Dict[str, Any], current_station_id: str) -> Dict[str, Any]:
        """
        Fetches 'andamentoTreno' to get full details.
        """
        train_number = departure_item.get('numeroTreno')
        origin_id = departure_item.get('codOrigine')
        
        if not origin_id:
            logger.warning(f"Missing origin ID for train {train_number}, skipping details.")
            return self._basic_fallback(departure_item)

        # Use current timestamp for request context
        ts_ms = int(time.time() * 1000)
        url = f"{self.BASE_URL}/andamentoTreno/{origin_id}/{train_number}/{ts_ms}"
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 204 or response.status_code == 404:
                # Train not found (maybe too far in future?), fallback
                return self._basic_fallback(departure_item)
                
            response.raise_for_status()
            details = response.json()
            
            # --- Extract Metrics ---
            
            # Locate current station in stops list to find specific arrival/dep info
            stops = details.get('fermate', [])
            current_stop_info = next((s for s in stops if s.get('id') == current_station_id), {})
            
            # Max Delay
            # Iterate all stops that have been visited or have delay info
            # 'ritardo' field in stops.
            max_delay = 0
            for stop in stops:
                delay = stop.get('ritardo', 0)
                if delay and isinstance(delay, (int, float)) and delay > max_delay:
                    max_delay = delay

            # Times and Gates
            # Prefer data from 'current_stop_info' if available, otherwise details top-level
            
            # Planned Departure
            dep_planned_ts = current_stop_info.get('partenza_teorica') # ms timestamp
            # Effective Departure
            dep_effective_ts = current_stop_info.get('partenza_reale') # ms timestamp
            
            # Planned Arrival (at this station - meaningful if not origin)
            arr_planned_ts = current_stop_info.get('arrivo_teorico')
            # Effective Arrival
            arr_effective_ts = current_stop_info.get('arrivo_reale')
            
            # Gates
            gate_planned = current_stop_info.get('binarioProgrammatoPartenzaDescrizione')
            gate_effective = current_stop_info.get('binarioEffettivoPartenzaDescrizione')
            
            arr_gate_planned = current_stop_info.get('binarioProgrammatoArrivoDescrizione')
            arr_gate_effective = current_stop_info.get('binarioEffettivoArrivoDescrizione')

            # Status
            cancelled = details.get('provvedimento') == 1 or departure_item.get('circolazioneInterrotta', False) 
            
            train_type = details.get('categoria') # "Regionale", "Frecciarossa"
            
            # Format Times
            def fmt_ts(ms):
                if ms:
                    return datetime.fromtimestamp(ms / 1000.0).isoformat()
                return ""
                
            dep_planned_str = fmt_ts(dep_planned_ts)
            dep_effective_str = fmt_ts(dep_effective_ts)
            arr_planned_str = fmt_ts(arr_planned_ts) 
            arr_effective_str = fmt_ts(arr_effective_ts)

            # Delay calc
            delay_minutes = 0
            if dep_planned_ts and dep_effective_ts:
                 delay_minutes = round((dep_effective_ts - dep_planned_ts) / 60000.0)
            if max_delay > delay_minutes:
                 delay_minutes = max_delay # Use max recorded delay if higher?

            # Departure status
            status = "ON TIME"
            if cancelled: status = "CANCELLED"
            elif delay_minutes > 5: status = "DELAYED"
            elif delay_minutes < -5: status = "EARLY"
            
            # Arrival status
            status_arrival = "N/A"
            arrival_delay_min = 0
            if arr_planned_ts and arr_effective_ts:
                arrival_delay_min = round((arr_effective_ts - arr_planned_ts) / 60000.0)
                if arrival_delay_min > 5: status_arrival = "DELAYED"
                elif arrival_delay_min < -5: status_arrival = "EARLY"
                else: status_arrival = "ON TIME"
            
            # Journey ID for deduplication
            journey_date = dep_planned_str[:10] if dep_planned_str else datetime.utcnow().strftime("%Y-%m-%d")
            destination_clean = details.get('destinazione', 'UNKNOWN').replace(" ", "")[:20]
            journey_id = f"{train_type}{train_number}_{journey_date}_{destination_clean}"
            
            row = {
                "created_at": datetime.utcnow().isoformat(),
                "station": details.get('stazioneCorrente') or departure_item.get('localita', {}).get('descrizione'),
                "train_name": f"{train_type} {train_number}",
                "destination": details.get('destinazione'),
                "category": train_type,
                "number": str(train_number),
                "operator": "Trenitalia",
                "partner_operator": "",
                "raw_departure_iso": dep_planned_str or self._parse_time(departure_item.get('compOrarioPartenza', '00:00')),
                
                "planned_departure": dep_planned_str,
                "predicted_departure": dep_effective_str,
                "delay_minutes": delay_minutes,
                "delay": delay_minutes,
                "status": status,
                "status_arrival": status_arrival,
                
                "planned_platform": gate_planned,
                "predicted_platform": gate_effective,
                
                "planned_arrival": arr_planned_str,
                "predicted_arrival": arr_effective_str,
                "arrival_delay": arrival_delay_min,
                
                "is_cancelled": cancelled,
                "cancellation_reason": "",
                "train_speed": "",
                "journey_duration": "", 
                "stops_count": len(stops),
                "api_response_time": 0,
                "journey_id": journey_id,
                "record_id": f"IT_{train_number}_{details.get('stazioneCorrente', 'UNK')}_{dep_planned_str}",
                "data_quality": 100,
                "raw_json": json.dumps(details)
            }
            pass # Replacement end
            
            return row
            
        except Exception as e:
            logger.warning(f"Failed to get details for train {train_number}: {e}")
            return self._basic_fallback(departure_item)

    def _basic_fallback(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback if detailed info fails"""
        category = item.get('categoria')
        number = str(item.get('numeroTreno'))
        dep_idx = item.get('compOrarioPartenza', '00:00')
        parsed_dep = self._parse_time(dep_idx)
        
        row = {
            "created_at": datetime.utcnow().isoformat(),
            "station": "Unknown",
            "train_name": f"{category} {number}",
            "destination": item.get('destinazione'),
            "category": category,
            "number": number,
            "operator": "Trenitalia",
            "partner_operator": "",
            "raw_departure_iso": parsed_dep,
            "planned_departure": parsed_dep,
            "predicted_departure": parsed_dep,
            "delay_minutes": 0,
            "delay": 0,
            "status": "UNKNOWN",
            "status_arrival": "N/A",
            "planned_platform": item.get('binarioProgrammatoPartenzaDescrizione'),
            "predicted_platform": item.get('binarioEffettivoPartenzaDescrizione'),
            "planned_arrival": "",
            "predicted_arrival": "",
            "arrival_delay": 0,
            "is_cancelled": False,
            "cancellation_reason": "Fallback data",
            "train_speed": "",
            "journey_duration": "",
            "stops_count": 0,
            "api_response_time": 0,
            "journey_id": f"{category}{number}_UNKNOWN",
            "record_id": f"IT_FB_{number}_{parsed_dep}",
            "data_quality": 50,
            "raw_json": json.dumps(item)
        }
        return row

    def _parse_time(self, hhmm: str) -> str:
        try:
            now = datetime.now()
            hour, minute = map(int, hhmm.split(':'))
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return dt.isoformat()
        except:
            return datetime.utcnow().isoformat()

class TrainMonitor:
    def __init__(self, data_endpoint: str, provider: TrainProvider):
        self.data_endpoint = data_endpoint
        self.provider = provider
        self.session = self._create_retry_session()

    def _create_retry_session(self, retries=3, backoff_factor=0.3):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(500, 502, 504),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def run(self, station_name: str):
        if not station_name:
            logger.error("STATION_NAME is not set")
            return

        departures = self.provider.get_departures(station_name)
        
        if not departures:
            logger.info("No departures found or API error occurred.")
            return

        logger.info(f"Found {len(departures)} departures. Sending to Data Endpoint...")
        self._send_to_endpoint(departures)

    def _send_to_endpoint(self, rows: List[Dict[str, Any]]):
        if not self.data_endpoint:
            logger.warning("DATA_ENDPOINT not set. Skipping upload (Dry Run equivalent).")
            # For debugging show what would be sent
            logger.debug(f"Payload: {json.dumps({'data': rows}, indent=2)}")
            return

        payload = {"data": rows}
        
        try:
            # Handle potential redirects (GAS Web Apps often redirect)
            response = self.session.post(
                self.data_endpoint, 
                json=payload,
                timeout=15,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Check for application-level errors from GAS
            try:
                resp_json = response.json()
                if resp_json.get("status") == "error":
                    logger.error(f"GAS App Error: {resp_json.get('message')}")
                else:
                    logger.info(f"Successfully sent data. Response: {resp_json}")
            except json.JSONDecodeError:
                # GAS sometimes returns HTML on error pages or auth screens
                logger.warning(f"Response was not JSON. Status: {response.status_code}. Text preview: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send data to endpoint: {e}")

def main():
    # Configuration
    data_url = os.environ.get("DATA_ENDPOINT")
    
    # Provider selection
    provider_type = os.environ.get("TRAIN_PROVIDER", "swiss").lower()
    
    # Check if user wants multi-station mode
    multi_station_mode = os.environ.get("MULTI_STATION", "false").lower() == "true"
    
    # Single station from environment variable
    env_station = os.environ.get("STATION_NAME")
    
    logger.info("=== Train Monitor Started ===")
    
    if not data_url:
        logger.warning("DATA_ENDPOINT is not set. Running in DRY RUN mode.")
    else:
        logger.info("DATA_ENDPOINT is configured.")
    
    # Determine stations to monitor
    stations_to_monitor = []
    
    if multi_station_mode:
        # Load stations from config file
        try:
            with open('stations.json', 'r') as f:
                config = json.load(f)
                if provider_type == "italy":
                    stations_to_monitor = config.get("italian_stations", [])
                    logger.info(f"Multi-station mode: Monitoring {len(stations_to_monitor)} Italian stations")
                else:
                    stations_to_monitor = config.get("swiss_stations", [])
                    logger.info(f"Multi-station mode: Monitoring {len(stations_to_monitor)} Swiss stations")
        except FileNotFoundError:
            logger.error("stations.json not found. Falling back to single station mode.")
            multi_station_mode = False
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing stations.json: {e}. Falling back to single station mode.")
            multi_station_mode = False
    
    # Single station mode (fallback or explicit)
    if not multi_station_mode:
        if provider_type == "italy":
            station = env_station if env_station else "Roma Termini"
        else:
            station = env_station if env_station else "Zurich HB"
        stations_to_monitor = [station]
        logger.info(f"Single station mode: {station}")
    
    # Initialize provider
    if provider_type == "italy":
        provider = ViaggiatrenoTrainProvider()
        logger.info(f"Using Italian Train Provider (Viaggiatreno)")
    else:
        provider = SwissTrainProvider()
        logger.info(f"Using Swiss Train Provider (Opendata.ch)")
    
    # Monitor all stations
    monitor = TrainMonitor(data_url, provider)
    
    for station in stations_to_monitor:
        logger.info(f"Processing station: {station}")
        try:
            monitor.run(station)
        except Exception as e:
            logger.error(f"Error processing {station}: {e}")
            continue
    
    logger.info("=== Train Monitor Finished ===")

if __name__ == "__main__":
    main()
