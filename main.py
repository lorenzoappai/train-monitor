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
                    category = connection.get("category")
                    number = connection.get("number")
                    
                    row = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "station": station_name,
                        "name": f"{category} {number}",
                        "to": connection.get("to"),
                        "category": category,
                        "number": number,
                        "operator": connection.get("operator"),
                        "departure_iso": stop.get("departure")
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

            row = {
                "timestamp": datetime.utcnow().isoformat(),
                "station": details.get('stazioneCorrente') or departure_item.get('localita', {}).get('descrizione'), # fallback
                "name": f"{train_type} {train_number}",
                "to": details.get('destinazione'),
                "category": train_type,
                "number": str(train_number),
                "operator": "Trenitalia",
                "departure_iso": fmt_ts(dep_planned_ts) or self._parse_time(departure_item.get('compOrarioPartenza', '00:00')),
                
                # Extended fields
                "departure_planned": fmt_ts(dep_planned_ts),
                "departure_effective": fmt_ts(dep_effective_ts),
                "gate_planned": gate_planned,
                "gate_effective": gate_effective,
                
                "arrival_planned": fmt_ts(arr_planned_ts),
                "arrival_effective": fmt_ts(arr_effective_ts),
                "arrival_gate_planned": arr_gate_planned,
                "arrival_gate_effective": arr_gate_effective,
                
                "cancelled":  "YES" if cancelled else "NO",
                "max_delay": max_delay,
                "train_type": details.get('tipologia') or train_type # 'tipologia' might be descriptive
            }
            
            return row
            
        except Exception as e:
            logger.warning(f"Failed to get details for train {train_number}: {e}")
            return self._basic_fallback(departure_item)

    def _basic_fallback(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback if detailed info fails"""
        row = {
            "timestamp": datetime.utcnow().isoformat(),
            "station": "Unknown", # Should be passed in
            "name": f"{item.get('categoria')} {item.get('numeroTreno')}",
            "to": item.get('destinazione'),
            "category": item.get('categoria'),
            "number": str(item.get('numeroTreno')),
            "operator": "Trenitalia",
            "departure_iso": self._parse_time(item.get('compOrarioPartenza', '00:00')),
            # Empty extended fields
            "departure_planned": "", "departure_effective": "",
            "gate_planned": item.get('binarioProgrammatoPartenzaDescrizione'),
            "gate_effective": item.get('binarioEffettivoPartenzaDescrizione'),
            "cancelled": "Unknown",
            "max_delay": 0,
            "train_type": item.get('categoria')
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
    
    # Handle empty string or None for STATION_NAME based on provider defaults?
    env_station = os.environ.get("STATION_NAME")
    
    if provider_type == "italy":
        station = env_station if env_station else "Roma Termini"
        provider = ViaggiatrenoTrainProvider()
        logger.info(f"Using Italian Train Provider (Viaggiatreno)")
    else:
        station = env_station if env_station else "Zurich HB"
        provider = SwissTrainProvider()
        logger.info(f"Using Swiss Train Provider (Opendata.ch)")

    logger.info("=== Train Monitor Started ===")
    logger.info(f"Target Station: {station}")
    
    if not data_url:
        logger.warning("DATA_ENDPOINT is not set. Running in DRY RUN mode.")
    else:
        logger.info("DATA_ENDPOINT is configured.")

    monitor = TrainMonitor(data_url, provider)
    monitor.run(station)
    logger.info("=== Train Monitor Finished ===")

if __name__ == "__main__":
    main()
