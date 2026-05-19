from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import requests
from .models import RainfallData, WeatherData, TideLevelData, FloodRecord, BenchmarkSettings
from django.utils import timezone
from datetime import timedelta
import json
import pytz
from .forms import FloodRecordForm, BARANGAYS
from django.conf import settings
import logging
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO

# Set up logging
logger = logging.getLogger(__name__)


def fetch_api_with_cache(url, params, cache_key, cache_timeout=3600):
    """Fetch API data with caching to reduce external API calls.
    
    Args:
        url: API endpoint URL
        params: Dictionary of query parameters
        cache_key: Unique cache key for this request
        cache_timeout: Cache TTL in seconds (default: 3600 = 1 hour)
        
    Returns:
        tuple: (data: dict or None, from_cache: bool)
    """
    # Try to get from cache first
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        logger.info(f"Cache HIT: {cache_key}")
        return cached_data, True
    
    # Cache miss - fetch from API
    logger.info(f"Cache MISS: {cache_key} - Fetching from API")
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Store in cache
        cache.set(cache_key, data, cache_timeout)
        logger.info(f"Cached data with key: {cache_key} (TTL: {cache_timeout}s)")
        return data, False
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None, False


def validate_barangay_json(barangay_data_json):
    """Validate and sanitize barangay JSON data.
    
    Args:
        barangay_data_json: JSON string to validate
        
    Returns:
        tuple: (is_valid: bool, data: dict or None, error: str or None)
    """
    # Basic sanitization - remove potentially harmful characters
    if not isinstance(barangay_data_json, str):
        return False, None, "Input must be a string"
    
    # Limit JSON size to prevent DoS attacks (1MB max)
    if len(barangay_data_json) > 1024 * 1024:
        return False, None, "JSON data too large (max 1MB)"
    
    try:
        data = json.loads(barangay_data_json)
        
        # Validate structure: must be a dictionary
        if not isinstance(data, dict):
            return False, None, "JSON must be an object/dictionary"
        
        # Validate each barangay entry
        valid_fields = {
            'casualties_dead', 'casualties_injured', 'casualties_missing',
            'affected_persons', 'affected_families',
            'houses_damaged_partially', 'houses_damaged_totally',
            'damage_infrastructure_php', 'damage_agriculture_php',
            'damage_institutions_php', 'damage_private_commercial_php'
        }
        
        for barangay, fields in data.items():
            # Sanitize barangay name (prevent XSS)
            if not isinstance(barangay, str) or len(barangay) > 200:
                return False, None, f"Invalid barangay name: {barangay[:50]}"
            
            # Validate fields structure
            if not isinstance(fields, dict):
                return False, None, f"Invalid data structure for {barangay}"
            
            # Check for unexpected fields
            for field_name in fields.keys():
                if field_name not in valid_fields:
                    return False, None, f"Invalid field '{field_name}' in {barangay}"
            
            # Validate numeric values
            for field_name, value in fields.items():
                try:
                    # Convert to float first for validation
                    numeric_value = float(value) if value not in (None, '', 0) else 0
                    
                    # Check for reasonable ranges
                    if numeric_value < 0:
                        return False, None, f"Negative value not allowed for {field_name} in {barangay}"
                    
                    if numeric_value > 1e12:  # 1 trillion max
                        return False, None, f"Value too large for {field_name} in {barangay}"
                    
                except (ValueError, TypeError):
                    return False, None, f"Invalid numeric value for {field_name} in {barangay}: {value}"
        
        return True, data, None
        
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON format: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in validate_barangay_json: {e}")
        return False, None, "An error occurred while validating data"


def process_barangay_data(barangay_data_json, flood_record):
    """Extract and process barangay-specific data from JSON.
    
    Args:
        barangay_data_json: JSON string containing barangay data
        flood_record: FloodRecord instance to update
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # First, validate and sanitize the input
    is_valid, barangay_data, error_msg = validate_barangay_json(barangay_data_json)
    
    if not is_valid:
        return False, error_msg
    
    if not barangay_data:
        return True, None
    
    try:
            
        # Structure: {barangay_value: {field: value, ...}, ...}
        # Need to restructure to {field: {barangay_name: value, ...}, ...}
        restructured_data = {}
        
        # Get all field names from first barangay (they should all have same fields)
        first_barangay_data = next(iter(barangay_data.values()))
        fields = first_barangay_data.keys()
        
        # For each field, collect values from all barangays
        for field in fields:
            restructured_data[field] = {}
            for barangay_value, values in barangay_data.items():
                # Find barangay name from BARANGAYS list
                barangay_name = next((b[1] for b in BARANGAYS if b[0] == barangay_value), barangay_value)
                value = values.get(field, 0)
                # Validate that value is numeric
                try:
                    numeric_value = float(value) if value else 0
                    if numeric_value > 0:  # Only store non-zero values
                        restructured_data[field][barangay_name] = numeric_value
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid numeric value for {field} in {barangay_name}: {value}")
                    continue
        
        flood_record.barangay_data = restructured_data
        
        # Auto-calculate all totals from barangay data with safe numeric conversion
        flood_record.casualties_dead = int(sum(restructured_data.get('casualties_dead', {}).values()))
        flood_record.casualties_injured = int(sum(restructured_data.get('casualties_injured', {}).values()))
        flood_record.casualties_missing = int(sum(restructured_data.get('casualties_missing', {}).values()))
        flood_record.affected_persons = int(sum(restructured_data.get('affected_persons', {}).values()))
        flood_record.affected_families = int(sum(restructured_data.get('affected_families', {}).values()))
        flood_record.houses_damaged_partially = int(sum(restructured_data.get('houses_damaged_partially', {}).values()))
        flood_record.houses_damaged_totally = int(sum(restructured_data.get('houses_damaged_totally', {}).values()))
        flood_record.damage_infrastructure_php = sum(restructured_data.get('damage_infrastructure_php', {}).values())
        flood_record.damage_agriculture_php = sum(restructured_data.get('damage_agriculture_php', {}).values())
        flood_record.damage_institutions_php = sum(restructured_data.get('damage_institutions_php', {}).values())
        flood_record.damage_private_commercial_php = sum(restructured_data.get('damage_private_commercial_php', {}).values())
        
        # Calculate total damage
        flood_record.damage_total_php = (
            flood_record.damage_infrastructure_php +
            flood_record.damage_agriculture_php +
            flood_record.damage_institutions_php +
            flood_record.damage_private_commercial_php
        )
        
        logger.info(f"Barangay data processed: {len(restructured_data)} fields")
        logger.info(f"Calculated totals - Dead: {flood_record.casualties_dead}, Damage: ₱{flood_record.damage_total_php:,.2f}")
        return True, None
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
        logger.warning(f"Failed to parse barangay_data_json: {e}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Error processing barangay data: {str(e)}"
        logger.error(f"Unexpected error in process_barangay_data: {e}", exc_info=True)
        return False, error_msg


def get_flood_risk_level(rainfall_mm):
    """Determine flood risk level based on rainfall."""
    settings = BenchmarkSettings.get_settings()
    if rainfall_mm >= settings.rainfall_high_threshold:
        return "High Risk (>={:.0f}mm)".format(settings.rainfall_high_threshold), "red"
    elif rainfall_mm >= settings.rainfall_moderate_threshold:
        return "Moderate Risk ({:.0f}-{:.0f}mm)".format(settings.rainfall_moderate_threshold, settings.rainfall_high_threshold), "orange"
    else:
        return "Low Risk (<{:.0f}mm)".format(settings.rainfall_moderate_threshold), "yellow"
    

def get_tide_risk_level(tide_m):
    """Determine tide risk level based on height."""
    settings = BenchmarkSettings.get_settings()
    if tide_m >= settings.tide_high_threshold:
        return "High Risk (>={:.1f}m)".format(settings.tide_high_threshold), "red"
    elif tide_m >= settings.tide_moderate_threshold:
        return "Moderate Risk ({:.1f}-{:.1f}m)".format(settings.tide_moderate_threshold, settings.tide_high_threshold), "orange"
    else:
        return "Low Risk (<{:.1f}m)".format(settings.tide_moderate_threshold), "yellow"
    

def get_combined_risk_level(rainfall_mm, tide_m):
    """
    Determine combined risk level based on threshold-based logic.
    Both rainfall AND tide must meet thresholds to trigger that risk level.
    
    Example with defaults:
    - Rainfall 32mm + Tide 0.3m = Low (rainfall met moderate threshold but tide didn't)
    - Rainfall 32mm + Tide 1.0m = Moderate (both met moderate thresholds)
    - Rainfall 50mm + Tide 1.5m = High (both met high thresholds)
    """
    settings = BenchmarkSettings.get_settings()
    
    # Check HIGH RISK: Both rainfall AND tide must meet high thresholds
    if rainfall_mm >= settings.rainfall_high_threshold and tide_m >= settings.tide_high_threshold:
        return "High Risk", "red"
    
    # Check MODERATE RISK: Both rainfall AND tide must meet moderate thresholds
    if rainfall_mm >= settings.rainfall_moderate_threshold and tide_m >= settings.tide_moderate_threshold:
        return "Moderate Risk", "orange"
    
    # Otherwise: LOW RISK
    return "Low Risk", "yellow"



def generate_flood_insights(weather_forecast, rainfall_data, tide_data, flood_records):
    """Generate intelligent flood prediction insights based on forecast data and historical patterns."""
    settings = BenchmarkSettings.get_settings()
    
    insights = {
        'risk_alerts': [],
        'forecast_analysis': [],
        'recommendations': [],
        'trends': [],
        'severity': 'low'
    }

    if not weather_forecast:
        return insights

    # Analyze forecast for high-risk periods based on rainfall benchmarks
    high_risk_days = []
    total_precipitation = 0
    max_precipitation = 0
    high_rainfall_days = 0

    for i, day in enumerate(weather_forecast):
        precip = day.get('precipitation', 0)
        total_precipitation += precip
        max_precipitation = max(max_precipitation, precip)

        # Check if precipitation exceeds high risk threshold
        if precip >= settings.rainfall_high_threshold:
            high_rainfall_days += 1
            high_risk_days.append({
                'day': i + 1,
                'date': day.get('formatted_date', f'Day {i+1}'),
                'precipitation': precip,
                'risk_level': 'high'
            })

    # Generate risk alerts based on rainfall thresholds
    if high_rainfall_days > 0:
        insights['risk_alerts'].append({
            'type': 'warning',
            'title': f'High Rainfall Alert',
            'message': f'{high_rainfall_days} day(s) with rainfall ≥ {settings.rainfall_high_threshold}mm predicted in the next 7 days',
            'severity': 'high'
        })
        insights['severity'] = 'high'

    if total_precipitation >= settings.rainfall_high_threshold * 2:
        insights['risk_alerts'].append({
            'type': 'warning',
            'title': 'High Total Precipitation',
            'message': f'Total precipitation of {total_precipitation:.1f}mm expected over 7 days',
            'severity': 'medium'
        })

    # Forecast analysis
    avg_temp = sum(day.get('temp_max', 28) for day in weather_forecast) / len(weather_forecast)
    max_humidity = max(day.get('humidity', 75) for day in weather_forecast)

    insights['forecast_analysis'].append({
        'title': 'Temperature Trend',
        'analysis': f'Average maximum temperature: {avg_temp:.1f}\u00b0C. {"High temperatures may intensify rainfall events." if avg_temp > 32 else "Temperatures within normal range."}',
        'impact': 'moderate' if avg_temp > 32 else 'low'
    })

    insights['forecast_analysis'].append({
        'title': 'Humidity Analysis',
        'analysis': f'Maximum humidity: {max_humidity}%. {"High humidity indicates moisture saturation, increasing flood risk." if max_humidity > 85 else "Humidity levels within normal range."}',
        'impact': 'high' if max_humidity > 85 else 'low'
    })

    # Historical context
    if flood_records:
        recent_floods = [record for record in flood_records if record.get('date')]
        if recent_floods:
            insights['trends'].append({
                'title': 'Historical Flood Patterns',
                'analysis': f'{len(recent_floods)} flood events recorded. Current conditions {"similar to past flood events" if total_precipitation > 30 else "different from typical flood patterns"}.',
                'recommendation': 'Monitor closely if patterns match historical flood events.'
            })

    # Generate recommendations based on analysis
    if insights['severity'] == 'high':
        insights['recommendations'].extend([
            {
                'priority': 'high',
                'action': 'Activate Emergency Response Teams',
                'reason': 'Heavy rainfall predicted in forecast'
            },
            {
                'priority': 'high',
                'action': 'Pre-position Emergency Supplies',
                'reason': 'High flood risk identified'
            },
            {
                'priority': 'medium',
                'action': 'Monitor Low-lying Areas',
                'reason': 'Vulnerable barangays at risk'
            }
        ])
    elif total_precipitation > 20:
        insights['recommendations'].extend([
            {
                'priority': 'medium',
                'action': 'Increase Monitoring Frequency',
                'reason': 'Moderate precipitation expected'
            },
            {
                'priority': 'low',
                'action': 'Prepare Drainage Systems',
                'reason': 'Preventive maintenance recommended'
            }
        ])
    else:
        insights['recommendations'].append({
            'priority': 'low',
            'action': 'Maintain Regular Monitoring',
            'reason': 'Current conditions stable'
        })

    # Add time-based insights
    # Get current hour in Philippines timezone (Asia/Manila)
    from django.utils import timezone as tz
    manila_tz = pytz.timezone('Asia/Manila')
    current_time = tz.now().astimezone(manila_tz)
    current_hour = current_time.hour
    
    if 6 <= current_hour <= 18:  # Daytime
        insights['forecast_analysis'].append({
            'title': 'Daytime Monitoring',
            'analysis': 'Currently daytime hours. Visual inspection of vulnerable areas recommended.',
            'impact': 'low'
        })
    else:  # Nighttime
        insights['forecast_analysis'].append({
            'title': 'Nighttime Monitoring',
            'analysis': 'Currently nighttime hours. Focus on automated monitoring systems and emergency response readiness.',
            'impact': 'medium'
        })

    return insights
    
@login_required
def monitoring_view(request):
    # Get time range parameter, default to 24h
    time_range = request.GET.get('time_range', '24h')
    
    # Calculate time filter based on selected range
    now = timezone.now()
    if time_range == '24h':
        time_filter = now - timedelta(hours=24)
        range_label = 'Last 24 Hours'
    elif time_range == '7d':
        time_filter = now - timedelta(days=7)
        range_label = 'Last 7 Days'
    elif time_range == '30d':
        time_filter = now - timedelta(days=30)
        range_label = 'Last 30 Days'
    elif time_range == '90d':
        time_filter = now - timedelta(days=90)
        range_label = 'Last 90 Days'
    elif time_range == 'all':
        time_filter = now - timedelta(days=365)  # Limit to 1 year for performance
        range_label = 'Last Year'
    else:
        time_filter = now - timedelta(hours=24)  # Default fallback
        range_label = 'Last 24 Hours'
    
    # Fetch or create initial data (exclude null timestamps)
    rainfall_data = RainfallData.objects.filter(timestamp__isnull=False).first()
    weather_data = WeatherData.objects.filter(timestamp__isnull=False).first()
    tide_data = TideLevelData.objects.filter(timestamp__isnull=False).first()

    # Initialize forecast data
    weather_forecast = []
    pagasa_data = None
    # Fetch current conditions from Open-Meteo API (hourly updates)
    # Location: Silay City, Negros Occidental
    try:
        api_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': 10.7959,  # Silay City, Negros Occidental
            'longitude': 122.9749,
            'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,rain',
            'hourly': 'temperature_2m,relative_humidity_2m,wind_speed_10m,rain',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,wind_speed_10m_max',
            'timezone': 'Asia/Manila',
            'forecast_days': 7
        }
        
        # Create cache key based on current hour (cache for 1 hour)
        cache_key = f"open_meteo_silay_{timezone.now().strftime('%Y%m%d_%H')}"
        
        logger.info(f"Requesting Open-Meteo API for current conditions: {api_url}")
        data, from_cache = fetch_api_with_cache(api_url, params, cache_key, cache_timeout=3600)
        
        if data:
            # Use current weather data for real-time values
            current = data.get('current', {})
            rainfall_value = current.get('rain', 0)  # Current rain in mm
            temperature = current.get('temperature_2m', 28.5)
            humidity = current.get('relative_humidity_2m', 75)
            wind_speed = current.get('wind_speed_10m', 10)
            
            logger.info(f"Open-Meteo (Current) - Rain: {rainfall_value}mm, Temp: {temperature}°C, Humidity: {humidity}%, Wind: {wind_speed}km/h")

            # Only create new records if data is older than 1 hour OR doesn't exist
            if not rainfall_data or not rainfall_data.timestamp or (timezone.now() - rainfall_data.timestamp).total_seconds() > 3600:
                rainfall_data = RainfallData.objects.create(value_mm=rainfall_value, station_name='Open-Meteo (Silay City)', timestamp=timezone.now())
                logger.info(f"Created new rainfall record: {rainfall_value}mm")

            if not weather_data or not weather_data.timestamp or (timezone.now() - weather_data.timestamp).total_seconds() > 3600:
                weather_data = WeatherData.objects.create(
                    temperature_c=temperature,
                    humidity_percent=humidity,
                    wind_speed_kph=wind_speed,
                    station_name='Open-Meteo (Silay City)',
                    timestamp=timezone.now()
                )
                logger.info(f"Created new weather record")

            # Process 7-day forecast data from Open-Meteo (Silay City)
            logger.info("Using Open-Meteo for Silay City forecast")
            daily_data = data.get('daily', {})
            if daily_data:
                dates = daily_data.get('time', [])
                temp_max = daily_data.get('temperature_2m_max', [])
                temp_min = daily_data.get('temperature_2m_min', [])
                precipitation = daily_data.get('precipitation_sum', [])
                humidity_avg = daily_data.get('relative_humidity_2m_mean', [])
                wind_max = daily_data.get('wind_speed_10m_max', [])
                
                weather_forecast = []
                for i in range(min(len(dates), 7)):
                    from datetime import datetime
                    date_obj = datetime.strptime(dates[i], '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%b %d')
                    
                    forecast_day = {
                        'date': dates[i],
                        'formatted_date': formatted_date,
                        'temp_max': temp_max[i] if i < len(temp_max) else 28.5,
                        'temp_min': temp_min[i] if i < len(temp_min) else 25.0,
                        'precipitation': precipitation[i] if i < len(precipitation) else 0.0,
                        'humidity': humidity_avg[i] if i < len(humidity_avg) else 75,
                        'wind_speed': wind_max[i] if i < len(wind_max) else 10.0,
                    }
                    weather_forecast.append(forecast_day)
                
                logger.info(f"Processed {len(weather_forecast)} days of Open-Meteo forecast for Silay City")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Open-Meteo API Error: {e}")
        if not rainfall_data:
            rainfall_data = RainfallData.objects.create(value_mm=0, station_name='Open-Meteo (Silay City)', timestamp=timezone.now())
            logger.warning("Created default rainfall record due to API error")
        if not weather_data:
            weather_data = WeatherData.objects.create(
                temperature_c=28.5,
                humidity_percent=75,
                wind_speed_kph=10,
                station_name='Open-Meteo (Silay City)',
                timestamp=timezone.now()
            )
            logger.warning("Created default weather record due to API error")
    except Exception as e:
        logger.error(f"Unexpected error fetching weather data: {e}")

    # Fetch tide data from WorldTides (Cebu City)
    if not tide_data or not tide_data.timestamp or (timezone.now() - tide_data.timestamp).total_seconds() > 3600:
        worldtides_api_key = getattr(settings, 'WORLDTIDES_API_KEY', None)
        if worldtides_api_key:
            try:
                tide_api_url = "https://www.worldtides.info/api/v3"
                tide_params = {
                    'heights': '',
                    'lat': 10.3157,  # Cebu City, Cebu
                    'lon': 123.8854,
                    'key': worldtides_api_key,
                    'date': timezone.now().strftime('%Y-%m-%d'),
                    'days': 1
                }
                
                # Cache tide data for 1 hour
                cache_key = f"worldtides_cebu_{timezone.now().strftime('%Y%m%d_%H')}"
                
                logger.info(f"Fetching WorldTides API for Cebu City: {tide_api_url}")
                tide_data_json, from_cache = fetch_api_with_cache(tide_api_url, tide_params, cache_key, cache_timeout=3600)
                
                if tide_data_json:
                    heights = tide_data_json.get('heights', [])
                    
                    if heights:
                        now_timestamp = timezone.now().timestamp()
                        closest_height = min(heights, key=lambda x: abs(x['dt'] - now_timestamp))
                        tide_value = closest_height.get('height', 0.8)
                        
                        tide_data = TideLevelData.objects.create(
                            height_m=tide_value,
                            station_name='WorldTides - Cebu City',
                            timestamp=timezone.now()
                        )
                        cache_status = ' (cached)' if from_cache else ''
                        logger.info(f"Created tide record from WorldTides (Cebu City): {tide_value}m{cache_status}")
                    else:
                        logger.warning("No tide heights in WorldTides API response")
                else:
                    logger.error("WorldTides API request failed")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"WorldTides API Error (backup): {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching WorldTides backup data: {e}")
        else:
            logger.warning("WorldTides API key not configured in settings")

    # Create default tide data if WorldTides failed
    if not tide_data:
        tide_data = TideLevelData.objects.create(height_m=0.8, station_name='Default', timestamp=timezone.now())
        logger.warning("Created default tide record (WorldTides API unavailable)")

    # Convert QuerySets to lists of dictionaries for JSON serialization
    rainfall_history = list(RainfallData.objects.filter(
        timestamp__gte=time_filter
    ).order_by('timestamp').values('timestamp', 'value_mm'))
    
    tide_history = list(TideLevelData.objects.filter(
        timestamp__gte=time_filter
    ).order_by('timestamp').values('timestamp', 'height_m'))
    
    # Simplified flood record summary for dashboard link
    total_flood_records_count = FloodRecord.objects.count()
    
    # We only need a small summary for any quick stats if needed, 
    # but the detailed aggregation is moved to the dedicated page.
    flood_records_summary = FloodRecord.objects.all().order_by('-date')[:5]

    # Prepare rainfall and tide trend data (convert UTC to Manila timezone)
    from django.utils.timezone import localtime
    rainfall_timestamps = [localtime(r['timestamp']).strftime('%Y-%m-%d %H:%M') for r in rainfall_history]
    rainfall_values = [r['value_mm'] for r in rainfall_history]
    tide_timestamps = [localtime(t['timestamp']).strftime('%Y-%m-%d %H:%M') for t in tide_history]
    tide_values = [t['height_m'] for t in tide_history]

    # Prepare forecast data for charts with fallback for empty forecast
    if weather_forecast:
        forecast_dates = [day['formatted_date'] for day in weather_forecast]
        forecast_temp_max = [day['temp_max'] for day in weather_forecast]
        forecast_temp_min = [day['temp_min'] for day in weather_forecast]
        forecast_precipitation = [day['precipitation'] for day in weather_forecast]
        forecast_humidity = [day['humidity'] for day in weather_forecast]
        forecast_wind_speed = [day['wind_speed'] for day in weather_forecast]
    else:
        # Provide empty arrays as fallback when forecast is unavailable
        forecast_dates = []
        forecast_temp_max = []
        forecast_temp_min = []
        forecast_precipitation = []
        forecast_humidity = []
        forecast_wind_speed = []

    # Generate flood prediction insights (using current data and forecast)
    insights = generate_flood_insights(weather_forecast, rainfall_data, tide_data, None)

    # Determine flood risk levels
    rain_risk_level, rain_risk_color = get_flood_risk_level(rainfall_data.value_mm if rainfall_data else 0)
    tide_risk_level, tide_risk_color = get_tide_risk_level(tide_data.height_m if tide_data else 0)
    
    # Get current rainfall and tide values for combined risk calculation
    current_rainfall_mm = rainfall_data.value_mm if rainfall_data else 0
    current_tide_m = tide_data.height_m if tide_data else 0
    combined_risk_level, combined_risk_color = get_combined_risk_level(current_rainfall_mm, current_tide_m)

    # Get earliest and latest data dates for date picker constraints
    earliest_rainfall = RainfallData.objects.order_by('timestamp').first()
    earliest_tide = TideLevelData.objects.order_by('timestamp').first()
    earliest_flood = FloodRecord.objects.order_by('date').first()
    
    # Find the earliest date among all data sources
    earliest_dates = []
    if earliest_rainfall:
        earliest_dates.append(earliest_rainfall.timestamp.date())
    if earliest_tide:
        earliest_dates.append(earliest_tide.timestamp.date())
    if earliest_flood:
        earliest_dates.append(earliest_flood.date)
    
    # Use earliest date or default to 1 year ago if no data exists
    if earliest_dates:
        min_date = min(earliest_dates).isoformat()
    else:
        # Default to 1 year ago if no data exists yet
        min_date = (timezone.now().date() - timedelta(days=365)).isoformat()
    
    max_date = timezone.now().date().isoformat()  # Today's date

    # Get available years from flood records for filter dropdown
    available_years = FloodRecord.objects.dates('date', 'year', order='DESC')
    years_list = [date.year for date in available_years]

    context = {
        'rainfall_data': rainfall_data,
        'weather_data': weather_data,
        'tide_data': tide_data,
        'weather_forecast': weather_forecast,
        'forecast_dates': forecast_dates,
        'forecast_temp_max': forecast_temp_max,
        'forecast_temp_min': forecast_temp_min,
        'forecast_precipitation': forecast_precipitation,
        'forecast_humidity': forecast_humidity,
        'forecast_wind_speed': forecast_wind_speed,
        'insights': insights,
        'rainfall_history': rainfall_history,
        'tide_history': tide_history,
        'rain_risk_level': rain_risk_level,
        'rain_risk_color': rain_risk_color,
        'tide_risk_level': tide_risk_level,
        'tide_risk_color': tide_risk_color,
        'combined_risk_level': combined_risk_level,
        'combined_risk_color': combined_risk_color,
        'total_flood_records_count': total_flood_records_count,
        'rainfall_timestamps': rainfall_timestamps,
        'rainfall_values': rainfall_values,
        'tide_timestamps': tide_timestamps,
        'tide_values': tide_values,
        'time_range': time_range,
        'range_label': range_label,
        'min_date': min_date,
        'max_date': max_date,
    }

    return render(request, 'monitoring/monitoring.html', context)

@login_required
def get_current_risk_status(request):
    """API endpoint for map highlighting - returns current flood risk status."""
    try:
        from django.utils.timezone import localtime
        
        rainfall_data = RainfallData.objects.filter(timestamp__isnull=False).first()
        tide_data = TideLevelData.objects.filter(timestamp__isnull=False).first()
        
        # Get current values
        current_rainfall_mm = rainfall_data.value_mm if rainfall_data else 0
        current_tide_m = tide_data.height_m if tide_data else 0
        
        # Calculate combined risk level
        combined_risk_level, combined_risk_color = get_combined_risk_level(current_rainfall_mm, current_tide_m)
        
        # Determine which zones to highlight based on risk level
        zones_to_highlight = []
        if combined_risk_level == "High Risk":
            zones_to_highlight = ['VHF', 'HF']  # Highlight Very High and High susceptibility zones
        elif combined_risk_level == "Moderate Risk":
            zones_to_highlight = ['VHF', 'HF', 'MF']  # Highlight Very High, High, and Moderate zones
        # Low Risk: no zones highlighted (empty array)
        
        # Get benchmark thresholds for reference
        settings = BenchmarkSettings.get_settings()
        
        data = {
            'risk_level': combined_risk_level,
            'risk_color': combined_risk_color,
            'rainfall_mm': current_rainfall_mm,
            'tide_m': current_tide_m,
            'zones_to_highlight': zones_to_highlight,
            'timestamp': localtime(timezone.now()).strftime('%b %d, %Y %I:%M %p'),
            'thresholds': {
                'rainfall_moderate': settings.rainfall_moderate_threshold,
                'rainfall_high': settings.rainfall_high_threshold,
                'tide_moderate': settings.tide_moderate_threshold,
                'tide_high': settings.tide_high_threshold,
            }
        }
        
        # Return with no-cache headers to ensure fresh data
        response = JsonResponse(data)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    except Exception as e:
        logger.error(f"Error in get_current_risk_status: {e}")
        return JsonResponse({'error': 'Unable to fetch risk status'}, status=500)

@login_required
def fetch_data_api(request):
    """API endpoint for AJAX updates with error handling."""
    try:
        rainfall_data = RainfallData.objects.filter(timestamp__isnull=False).first()
        weather_data = WeatherData.objects.filter(timestamp__isnull=False).first()
        tide_data = TideLevelData.objects.filter(timestamp__isnull=False).first()
        
        data = {
            'rainfall': rainfall_data.value_mm if rainfall_data else 0,
            'temperature': weather_data.temperature_c if weather_data else 0,
            'humidity': weather_data.humidity_percent if weather_data else 0,
            'wind_speed': weather_data.wind_speed_kph if weather_data else 0,
            'tide': tide_data.height_m if tide_data else 0,
            'timestamps': {
                'rainfall': rainfall_data.timestamp.strftime('%b %d, %Y %H:%M') if rainfall_data and rainfall_data.timestamp else '',
                'weather': weather_data.timestamp.strftime('%b %d, %Y %H:%M') if weather_data and weather_data.timestamp else '',
                'tide': tide_data.timestamp.strftime('%b %d, %Y %H:%M') if tide_data and tide_data.timestamp else '',
            }
        }
        # Return with no-cache headers to ensure fresh data
        response = JsonResponse(data)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    except Exception as e:
        logger.error(f"Error in fetch_data_api: {e}")
        return JsonResponse({'error': 'Unable to fetch data'}, status=500)

@login_required
def fetch_trends_api(request):
    """API endpoint for fetching trend data with time range filtering and multi-year comparison."""
    try:
        from datetime import datetime, date
        
        # Define Manila timezone for timestamp formatting
        manila_tz = pytz.timezone('Asia/Manila')
        
        # Check for custom date range parameters
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Get selected single year parameter (e.g., "2024")
        single_year_str = request.GET.get('year', '')
        single_year = int(single_year_str) if single_year_str.isdigit() else None
        
        # Get selected comparison years (comma-separated list, e.g., "2024,2023")
        compare_years_str = request.GET.get('compare_years', '')
        compare_years = [int(y.strip()) for y in compare_years_str.split(',') if y.strip().isdigit()]
        
        now = timezone.now()
        current_year = now.year
        time_filter = None
        range_label = ""
        
        if start_date_str and end_date_str:
            # Custom date range provided
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                
                # Validation: end date should be after start date
                if end_date < start_date:
                    return JsonResponse({'error': 'End date must be after start date'}, status=400)
                
                # Validation: reasonable range (max 2 years)
                date_diff = (end_date - start_date).days
                if date_diff > 730:  # 2 years
                    return JsonResponse({'error': 'Date range cannot exceed 2 years'}, status=400)
                
                # Create datetime objects for filtering (start of start_date to end of end_date)
                start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
                end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
                
                time_filter = start_datetime
                range_label = f'Custom Range: {start_date.strftime("%b %d, %Y")} - {end_date.strftime("%b %d, %Y")}'
                
            except ValueError:
                return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        else:
            # Use predefined time range
            time_range = request.GET.get('time_range', '24h')
            
            if time_range == '24h':
                time_filter = now - timedelta(hours=24)
                range_label = 'Last 24 Hours'
            elif time_range == '7d':
                time_filter = now - timedelta(days=7)
                range_label = 'Last 7 Days'
            elif time_range == '30d':
                time_filter = now - timedelta(days=30)
                range_label = 'Last 30 Days'
            elif time_range == '90d':
                time_filter = now - timedelta(days=90)
                range_label = 'Last 90 Days'
            elif time_range == 'all':
                time_filter = now - timedelta(days=365)  # Limit to 1 year for performance
                range_label = 'Last Year'
            else:
                time_filter = now - timedelta(hours=24)  # Default fallback
                range_label = 'Last 24 Hours'
        
        # Helper function to safely replace year in datetime (handles leap years)
        def safe_year_replace(dt, target_year):
            """Safely replace year in datetime, handling Feb 29 leap year edge case."""
            try:
                if dt.month == 2 and dt.day == 29:
                    # Feb 29 in leap year -> convert to Feb 28 in non-leap year
                    return dt.replace(year=target_year, day=28)
                else:
                    return dt.replace(year=target_year)
            except ValueError:
                # Fallback: use Feb 28 if any other date issue occurs
                return dt.replace(year=target_year, day=28) if dt.month == 2 else dt.replace(year=target_year)
        
        # Helper function to fetch data for a specific year with normalized dates
        def fetch_year_data(year_offset=0):
            """Fetch data for current year or previous years with date normalization."""
            target_year = current_year - year_offset
            
            if start_date_str and end_date_str:
                # Adjust dates for comparison year - use target_year directly, not start_date.year
                try:
                    adjusted_start = start_date.replace(year=target_year)
                    adjusted_end = end_date.replace(year=target_year)
                except ValueError:
                    # Handle leap year Feb 29 issue
                    adjusted_start = safe_year_replace(datetime.combine(start_date, datetime.min.time()), target_year).date()
                    adjusted_end = safe_year_replace(datetime.combine(end_date, datetime.max.time()), target_year).date()
                
                # Create timezone-aware datetimes in Manila timezone to avoid date shifting
                adj_start_datetime = manila_tz.localize(datetime.combine(adjusted_start, datetime.min.time()))
                adj_end_datetime = manila_tz.localize(datetime.combine(adjusted_end, datetime.max.time()))
                
                rainfall = list(RainfallData.objects.filter(
                    timestamp__gte=adj_start_datetime,
                    timestamp__lte=adj_end_datetime
                ).order_by('timestamp').values('timestamp', 'value_mm'))
                
                tide = list(TideLevelData.objects.filter(
                    timestamp__gte=adj_start_datetime,
                    timestamp__lte=adj_end_datetime
                ).order_by('timestamp').values('timestamp', 'height_m'))
            else:
                # Time-based filtering for comparison year
                # Special handling for "all" time range - show entire year
                if time_range == 'all':
                    adjusted_filter = timezone.make_aware(datetime(target_year, 1, 1, 0, 0, 0))
                    adjusted_now = timezone.make_aware(datetime(target_year, 12, 31, 23, 59, 59))
                else:
                    # For current year (year_offset=0), use actual time filter without modification
                    if year_offset == 0:
                        # Current year - use the actual time range
                        adjusted_filter = time_filter
                        adjusted_now = now
                    else:
                        # For past years - shift the time filter to the corresponding period in the target year
                        try:
                            adjusted_filter = time_filter.replace(year=target_year)
                            adjusted_now = now.replace(year=target_year)
                        except ValueError:
                            # Handle leap year issues (e.g., Feb 29)
                            adjusted_filter = time_filter.replace(year=target_year, day=28) if time_filter.month == 2 else time_filter.replace(year=target_year)
                            adjusted_now = now.replace(year=target_year, day=28) if now.month == 2 else now.replace(year=target_year)
                
                rainfall = list(RainfallData.objects.filter(
                    timestamp__gte=adjusted_filter,
                    timestamp__lte=adjusted_now
                ).order_by('timestamp').values('timestamp', 'value_mm'))
                
                tide = list(TideLevelData.objects.filter(
                    timestamp__gte=adjusted_filter,
                    timestamp__lte=adjusted_now
                ).order_by('timestamp').values('timestamp', 'height_m'))
            
            # Normalize timestamps to current year for comparison (only needed for multi-year view)
            # For single year view, keep original timestamps
            for r in rainfall:
                original_dt = r['timestamp']
                r['normalized_timestamp'] = safe_year_replace(original_dt, current_year)
                # For display, show the actual year's timestamp (not normalized)
                r['display_timestamp'] = original_dt.astimezone(manila_tz).strftime('%Y-%m-%d %H:%M')
            
            for t in tide:
                original_dt = t['timestamp']
                t['normalized_timestamp'] = safe_year_replace(original_dt, current_year)
                # For display, show the actual year's timestamp (not normalized)
                t['display_timestamp'] = original_dt.astimezone(manila_tz).strftime('%Y-%m-%d %H:%M')
            
            return rainfall, tide
        
        # Check if single year view requested (e.g., only 2024)
        if single_year and not compare_years:
            # Single year view - treat the requested year as "current" for display purposes
            year_offset = current_year - single_year
            rainfall_data, tide_data = fetch_year_data(year_offset)
            
            # Use the actual year timestamps (not normalized to current year)
            # Need to re-format with the correct target year
            target_year = current_year - year_offset
            rainfall_timestamps = [r['timestamp'].astimezone(manila_tz).strftime('%Y-%m-%d %H:%M') for r in rainfall_data]
            rainfall_values = [r['value_mm'] for r in rainfall_data]
            tide_timestamps = [t['timestamp'].astimezone(manila_tz).strftime('%Y-%m-%d %H:%M') for t in tide_data]
            tide_values = [t['height_m'] for t in tide_data]
            
            data = {
                'time_range': request.GET.get('time_range', 'custom'),
                'range_label': f'{range_label} ({single_year})',
                'rainfall_timestamps': rainfall_timestamps,
                'rainfall_values': rainfall_values,
                'tide_timestamps': tide_timestamps,
                'tide_values': tide_values,
            }
            
            return JsonResponse(data)
        
        # Multi-year comparison view - now supports selecting ANY years (including current year)
        # If compare_years is provided, show ONLY those years
        if compare_years:
            # Prepare data structure for multiple years
            datasets = {
                'rainfall': {},
                'tide': {}
            }
            
            # Determine the most recent year for normalization
            most_recent_year = max(compare_years)
            
            # Fetch data for each selected year
            for year in compare_years:
                year_offset = current_year - year
                if year_offset >= 0 and year_offset <= 10:  # Current year (offset 0) or up to 10 years back
                    rainfall_comp, tide_comp = fetch_year_data(year_offset)
                    
                    # Normalize timestamps to the most recent year for overlapping comparison
                    normalized_rainfall_timestamps = []
                    for r in rainfall_comp:
                        # Replace year with most_recent_year for alignment
                        original_dt = r['timestamp']
                        try:
                            normalized_dt = original_dt.replace(year=most_recent_year)
                        except ValueError:
                            # Handle Feb 29 leap year
                            normalized_dt = safe_year_replace(original_dt, most_recent_year)
                        normalized_rainfall_timestamps.append(normalized_dt.astimezone(manila_tz).strftime('%Y-%m-%d %H:%M'))
                    
                    normalized_tide_timestamps = []
                    for t in tide_comp:
                        original_dt = t['timestamp']
                        try:
                            normalized_dt = original_dt.replace(year=most_recent_year)
                        except ValueError:
                            normalized_dt = safe_year_replace(original_dt, most_recent_year)
                        normalized_tide_timestamps.append(normalized_dt.astimezone(manila_tz).strftime('%Y-%m-%d %H:%M'))
                    
                    datasets['rainfall'][year] = {
                        'timestamps': normalized_rainfall_timestamps,
                        'values': [r['value_mm'] for r in rainfall_comp],
                        'label': f'{year}' + (' (Current)' if year == current_year else '')
                    }
                    datasets['tide'][year] = {
                        'timestamps': normalized_tide_timestamps,
                        'values': [t['height_m'] for t in tide_comp],
                        'label': f'{year}' + (' (Current)' if year == current_year else '')
                    }
            
            # Use the most recent (highest) year's timestamps for the X-axis display
            rainfall_timestamps = datasets['rainfall'][most_recent_year]['timestamps']
            rainfall_values = datasets['rainfall'][most_recent_year]['values']
            tide_timestamps = datasets['tide'][most_recent_year]['timestamps']
            tide_values = datasets['tide'][most_recent_year]['values']
            
            data = {
                'time_range': request.GET.get('time_range', 'custom'),
                'range_label': range_label,
                'rainfall_timestamps': rainfall_timestamps,
                'rainfall_values': rainfall_values,
                'tide_timestamps': tide_timestamps,
                'tide_values': tide_values,
                'datasets': datasets,
                'current_year': current_year,
                'compare_years': compare_years
            }
            
            return JsonResponse(data)
        
        # Default: show current year only (when no parameters provided)
        rainfall_current, tide_current = fetch_year_data(0)
        
        rainfall_timestamps = [r['display_timestamp'] for r in rainfall_current]
        rainfall_values = [r['value_mm'] for r in rainfall_current]
        tide_timestamps = [t['display_timestamp'] for t in tide_current]
        tide_values = [t['height_m'] for t in tide_current]
        
        data = {
            'time_range': request.GET.get('time_range', 'custom'),
            'range_label': range_label,
            'rainfall_timestamps': rainfall_timestamps,
            'rainfall_values': rainfall_values,
            'tide_timestamps': tide_timestamps,
            'tide_values': tide_values,
        }
        
        return JsonResponse(data)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in fetch_trends_api: {e}\n{error_details}")
        return JsonResponse({'error': f'Unable to fetch trend data: {str(e)}'}, status=500)

@login_required
@transaction.atomic
def flood_record_form(request):
    """Handle flood record form submission with comprehensive error handling."""
    if request.method == 'POST':
        form = FloodRecordForm(request.POST)
        
        try:
            if form.is_valid():
                flood_record = form.save(commit=False)
                
                # Process barangay-specific data if provided
                barangay_data_json = request.POST.get('barangay_data_json', '{}')
                success, error_msg = process_barangay_data(barangay_data_json, flood_record)
                
                if not success and error_msg:
                    messages.warning(request, f"Barangay data processing warning: {error_msg}")
                
                flood_record.save()
                
                # Log the activity (import at top of file)
                from maps.models import FloodRecordActivity
                FloodRecordActivity.objects.create(
                    user=request.user,
                    action='CREATE',
                    flood_record_id=flood_record.id,
                    event_type=flood_record.event,
                    event_date=flood_record.date,
                    affected_barangays=flood_record.affected_barangays,
                    casualties_dead=flood_record.casualties_dead,
                    casualties_injured=flood_record.casualties_injured,
                    casualties_missing=flood_record.casualties_missing,
                    affected_persons=flood_record.affected_persons,
                    affected_families=flood_record.affected_families,
                    damage_total_php=flood_record.damage_total_php
                )
                
                success_message = f'Flood record for {flood_record.event} on {flood_record.date.strftime("%Y-%m-%d")} has been successfully added!'
                logger.info(f"Flood record created: {flood_record.id} - {flood_record.event}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'redirect_url': reverse('monitoring_view')
                    })
                
                messages.success(request, success_message)
                return redirect('monitoring_view')
            else:
                error_message = 'Please correct the errors below and try again.'
                logger.warning(f"Form validation errors: {form.errors}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': form.errors
                    })
                    
                messages.error(request, error_message)
        except Exception as e:
            error_message = f'An unexpected error occurred while saving the record: {str(e)}'
            logger.error(f"Error saving flood record: {e}", exc_info=True)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })
                
            messages.error(request, error_message)
    else:
        form = FloodRecordForm()
    
    return render(request, 'monitoring/flood_record_form.html', {
        'form': form, 
        'BARANGAYS': BARANGAYS
    })

@login_required
@transaction.atomic
def flood_record_edit(request, record_id):
    """Handle editing of existing flood record."""
    flood_record = get_object_or_404(FloodRecord, id=record_id)
    
    if request.method == 'POST':
        form = FloodRecordForm(request.POST, instance=flood_record)
        
        try:
            if form.is_valid():
                flood_record = form.save(commit=False)
                
                # Process barangay-specific data if provided
                barangay_data_json = request.POST.get('barangay_data_json', '{}')
                success, error_msg = process_barangay_data(barangay_data_json, flood_record)
                
                if not success and error_msg:
                    messages.warning(request, f"Barangay data processing warning: {error_msg}")
                
                flood_record.save()
                success_message = f'Flood record for {flood_record.event} on {flood_record.date.strftime("%Y-%m-%d")} has been successfully updated!'
                logger.info(f"Flood record updated: {flood_record.id} - {flood_record.event}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'redirect_url': reverse('monitoring_view') + '#flood-records'
                    })
                
                messages.success(request, success_message)
                return redirect(reverse('monitoring_view') + '#flood-records')
            else:
                error_message = 'Please correct the errors below and try again.'
                logger.warning(f"Form validation errors: {form.errors}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': form.errors
                    })
                    
                messages.error(request, error_message)
        except Exception as e:
            error_message = f'An unexpected error occurred while updating the record: {str(e)}'
            logger.error(f"Error updating flood record: {e}", exc_info=True)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })
                
            messages.error(request, error_message)
    else:
        form = FloodRecordForm(instance=flood_record)
    
    return render(request, 'monitoring/flood_record_edit_new.html', {
        'form': form,
        'BARANGAYS': BARANGAYS,
        'record': flood_record
    })

@login_required
@transaction.atomic
def flood_record_delete(request, record_id):
    """Handle deletion of flood record."""
    flood_record = get_object_or_404(FloodRecord, id=record_id)
    
    if request.method == 'POST':
        try:
            event_name = flood_record.event
            event_date = flood_record.date.strftime("%Y-%m-%d")
            # Log the activity before deleting
            from maps.models import FloodRecordActivity
            FloodRecordActivity.objects.create(
                user=request.user,
                action='DELETE',
                flood_record_id=flood_record.id,
                event_type=flood_record.event,
                event_date=flood_record.date,
                affected_barangays=flood_record.affected_barangays,
                casualties_dead=flood_record.casualties_dead,
                casualties_injured=flood_record.casualties_injured,
                casualties_missing=flood_record.casualties_missing,
                affected_persons=flood_record.affected_persons,
                affected_families=flood_record.affected_families,
                damage_total_php=flood_record.damage_total_php
            )
            flood_record.delete()
            
            success_message = f'Flood record for {event_name} on {event_date} has been successfully deleted!'
            logger.info(f"Flood record deleted: {record_id} - {event_name}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('monitoring_view') + '#flood-records'
                })
            
            messages.success(request, success_message)
            return redirect(reverse('monitoring_view') + '#flood-records')
        except Exception as e:
            error_message = f'An error occurred while deleting the record: {str(e)}'
            logger.error(f"Error deleting flood record: {e}", exc_info=True)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })
            
            messages.error(request, error_message)
            return redirect(reverse('monitoring_view') + '#flood-records')
    
    return render(request, 'monitoring/flood_record_delete.html', {
        'record': flood_record
    })


def is_staff_user(user):
    """Check if user is a staff member"""
    return user.is_staff


@login_required
@user_passes_test(is_staff_user)
@require_http_methods(["GET", "POST"])
def benchmark_settings_view(request):
    """View for managing benchmark settings (admin only)"""
    settings = BenchmarkSettings.get_settings()
    
    if request.method == 'POST':
        try:
            # Get form data
            rainfall_moderate = float(request.POST.get('rainfall_moderate_threshold', 30))
            rainfall_high = float(request.POST.get('rainfall_high_threshold', 50))
            tide_moderate = float(request.POST.get('tide_moderate_threshold', 1.0))
            tide_high = float(request.POST.get('tide_high_threshold', 1.5))
            
            # Validation
            errors = []
            if rainfall_moderate >= rainfall_high:
                errors.append("Rainfall moderate threshold must be less than high threshold")
            if tide_moderate >= tide_high:
                errors.append("Tide moderate threshold must be less than high threshold")
            if rainfall_moderate <= 0 or rainfall_high <= 0:
                errors.append("Rainfall thresholds must be positive")
            if tide_moderate <= 0 or tide_high <= 0:
                errors.append("Tide thresholds must be positive")
            
            if errors:
                for error in errors:
                    messages.error(request, f"{error}")
                return render(request, 'monitoring/benchmark_settings.html', {
                    'settings': settings,
                    'errors': errors
                })
            
            # Update settings
            settings.rainfall_moderate_threshold = rainfall_moderate
            settings.rainfall_high_threshold = rainfall_high
            settings.tide_moderate_threshold = tide_moderate
            settings.tide_high_threshold = tide_high
            settings.updated_by = request.user.get_full_name() or request.user.username
            settings.save()
            
            messages.success(request, "Benchmark settings updated successfully!")
            return redirect('benchmark_settings')
        
        except ValueError as e:
            messages.error(request, f"Invalid input: Please enter valid numbers")
            return render(request, 'monitoring/benchmark_settings.html', {
                'settings': settings
            })
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return render(request, 'monitoring/benchmark_settings.html', {
                'settings': settings
            })
    
    return render(request, 'monitoring/benchmark_settings.html', {
        'settings': settings
    })


@login_required
def export_trends(request):
    """Export rainfall and tide trends data to CSV or PDF"""
    import csv
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    import base64
    
    # Handle both GET and POST requests
    if request.method == 'POST':
        export_type = request.GET.get('type', 'pdf')
        time_range = request.GET.get('time_range', '')
        start_date_str = request.GET.get('start_date', '')
        end_date_str = request.GET.get('end_date', '')
        single_year_str = request.GET.get('year', '')
        compare_years_str = request.GET.get('compare_years', '')
        
        # Get chart images from POST data with size protection
        rainfall_chart_b64 = request.POST.get('rainfall_chart', '')
        tide_chart_b64 = request.POST.get('tide_chart', '')
        
        # SECURITY: Limit base64 payload size to prevent memory-based DoS
        max_size = getattr(settings, 'MAX_CHART_BASE64_SIZE', 2 * 1024 * 1024)
        if len(rainfall_chart_b64) > max_size or len(tide_chart_b64) > max_size:
            messages.error(request, "Chart data too large. Please try a smaller date range.")
            return redirect('monitoring')
    else:
        export_type = request.GET.get('type', 'csv')
        time_range = request.GET.get('time_range', '')
        start_date_str = request.GET.get('start_date', '')
        end_date_str = request.GET.get('end_date', '')
        single_year_str = request.GET.get('year', '')
        compare_years_str = request.GET.get('compare_years', '')
        rainfall_chart_b64 = ''
        tide_chart_b64 = ''
    
    # Get selected year parameters
    single_year_str = request.GET.get('year', '')
    compare_years_str = request.GET.get('compare_years', '')
    
    logger.info(f"Export parameters: year={single_year_str}, compare_years={compare_years_str}")
    logger.info(f"Full GET params: {request.GET}")
    
    single_year = int(single_year_str) if single_year_str.isdigit() else None
    compare_years = [int(y.strip()) for y in compare_years_str.split(',') if y.strip().isdigit()] if compare_years_str else []
    
    logger.info(f"Parsed: single_year={single_year}, compare_years={compare_years}")
    
    # Determine which years to export
    current_year = timezone.now().year
    years_to_export = []
    
    if compare_years:
        years_to_export = compare_years
        logger.info(f"Using compare_years: {years_to_export}")
    elif single_year:
        years_to_export = [single_year]
        logger.info(f"Using single_year: {years_to_export}")
    else:
        years_to_export = [current_year]
        logger.info(f"Using current_year (default): {years_to_export}")
    
    # If specific years are selected (not current year), default to 'all' time range if not specified
    if not time_range and (single_year or compare_years):
        if single_year and single_year != current_year:
            time_range = 'all'
        elif compare_years:
            time_range = 'all'
    
    # Determine filtering method
    now = timezone.now()
    
    if start_date_str and end_date_str:
        # Custom date range
        try:
            from datetime import date as date_module
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            
            time_filter = start_datetime
            end_filter = end_datetime
            range_label = f'Custom Range: {start_date.strftime("%b %d, %Y")} - {end_date.strftime("%b %d, %Y")}'
            use_range = True
        except ValueError:
            # Fallback to default
            time_filter = now - timedelta(hours=24)
            end_filter = now
            range_label = 'Last 24 Hours'
            use_range = True
    else:
        # Predefined time range
        use_range = False
        if time_range == '24h':
            time_filter = now - timedelta(hours=24)
            range_label = 'Last 24 Hours'
        elif time_range == '7d':
            time_filter = now - timedelta(days=7)
            range_label = 'Last 7 Days'
        elif time_range == '30d':
            time_filter = now - timedelta(days=30)
            range_label = 'Last 30 Days'
        elif time_range == '90d':
            time_filter = now - timedelta(days=90)
            range_label = 'Last 90 Days'
        elif time_range == 'all':
            time_filter = now - timedelta(days=365)
            range_label = 'Last Year'
        else:
            time_filter = now - timedelta(hours=24)
            range_label = 'Last 24 Hours'
    
    # Fetch data based on filter type and selected years
    combined_data = []
    
    for year in years_to_export:
        year_offset = current_year - year
        
        logger.info(f"Export: Processing year {year}, offset {year_offset}")
        
        if use_range and 'end_filter' in locals():
            # Adjust date range for this year
            adjusted_start = start_date.replace(year=year)
            adjusted_end = end_date.replace(year=year)
            adj_start_datetime = timezone.make_aware(datetime.combine(adjusted_start, datetime.min.time()))
            adj_end_datetime = timezone.make_aware(datetime.combine(adjusted_end, datetime.max.time()))
            
            logger.info(f"Export: Querying from {adj_start_datetime} to {adj_end_datetime}")
            
            rainfall_data = RainfallData.objects.filter(
                timestamp__gte=adj_start_datetime,
                timestamp__lte=adj_end_datetime
            ).order_by('timestamp')
            tide_data = TideLevelData.objects.filter(
                timestamp__gte=adj_start_datetime,
                timestamp__lte=adj_end_datetime
            ).order_by('timestamp')
            
            logger.info(f"Export: Found {rainfall_data.count()} rainfall records and {tide_data.count()} tide records for year {year}")
        else:
            # Adjust time range for this year
            # Special handling for "all" time range - show entire year
            if time_range == 'all':
                adjusted_filter = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
                adjusted_now = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))
            else:
                # Shift the time filter to the corresponding period in the target year
                try:
                    adjusted_filter = time_filter.replace(year=year)
                    adjusted_now = now.replace(year=year)
                except ValueError:
                    # Handle leap year issues (e.g., Feb 29)
                    adjusted_filter = time_filter.replace(year=year, day=28) if time_filter.month == 2 else time_filter.replace(year=year)
                    adjusted_now = now.replace(year=year, day=28) if now.month == 2 else now.replace(year=year)
            
            rainfall_data = RainfallData.objects.filter(
                timestamp__gte=adjusted_filter,
                timestamp__lte=adjusted_now
            ).order_by('timestamp')
            tide_data = TideLevelData.objects.filter(
                timestamp__gte=adjusted_filter,
                timestamp__lte=adjusted_now
            ).order_by('timestamp')
        
        # Add year label to data
        for r in rainfall_data:
            combined_data.append({
                'timestamp': r.timestamp,
                'rainfall': r,
                'tide': None,
                'year': year
            })
        
        for t in tide_data:
            # Check if timestamp already exists
            existing = next((d for d in combined_data if d['timestamp'] == t.timestamp and d['year'] == year), None)
            if existing:
                existing['tide'] = t
            else:
                combined_data.append({
                    'timestamp': t.timestamp,
                    'rainfall': None,
                    'tide': t,
                    'year': year
                })
    
    # Sort by timestamp
    combined_data.sort(key=lambda x: x['timestamp'])
    
    # Update range label to include years
    if len(years_to_export) > 1:
        years_label = ', '.join(map(str, sorted(years_to_export, reverse=True)))
        range_label = f'{range_label} ({years_label})'
    elif len(years_to_export) == 1 and years_to_export[0] != current_year:
        range_label = f'{range_label} ({years_to_export[0]})'
    
    if export_type == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'rainfall_tide_trends_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        writer.writerow(['# Rainfall & Tide Trends Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Time Range: {range_label}'])
        writer.writerow([f'# Total Records: {len(combined_data)}'])
        writer.writerow([])
        
        writer.writerow(['#', 'Timestamp', 'Rainfall (mm)', 'Tide Level (m)'])
        
        for idx, data in enumerate(combined_data, 1):
            rainfall_value = data['rainfall'].value_mm if data['rainfall'] else '-'
            tide_value = data['tide'].height_m if data['tide'] else '-'
            writer.writerow([
                idx,
                data['timestamp'].strftime('%Y-%m-%d %H:%M'),
                rainfall_value,
                tide_value
            ])
        
        return response
    
    elif export_type == 'pdf':
        from reportlab.platypus import Image as RLImage, PageBreak
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        import os
        import io
        
        # Use BytesIO buffer for PDF generation to satisfy type checkers
        buffer = io.BytesIO()
        response = HttpResponse(content_type='application/pdf')
        filename = f'rainfall_tide_trends_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Custom page template with header and footer (PORTRAIT)
        def add_header_footer(canvas, doc):
            canvas.saveState()
            
            # Header - DRRMO logo/header
            header_path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR / 'static', 'images', 'drrmo_header.png')
            if os.path.exists(header_path):
                try:
                    page_width = letter[0]
                    canvas.drawImage(header_path, 0, doc.height + doc.topMargin, 
                                   width=page_width, height=0.9*inch, 
                                   preserveAspectRatio=True, mask='auto')
                except:
                    pass
            
            # Footer line
            page_width = letter[0]
            canvas.setStrokeColor(colors.HexColor('#1e3a5f'))
            canvas.setLineWidth(2)
            canvas.line(0.5*inch, 0.45*inch, page_width - 0.5*inch, 0.45*inch)
            
            # Footer text
            canvas.setFont('Helvetica-Bold', 8)
            canvas.setFillColor(colors.HexColor('#1e3a5f'))
            footer_text = "SILAY CITY DISASTER RISK REDUCTION & MANAGEMENT COUNCIL"
            text_width = canvas.stringWidth(footer_text, 'Helvetica-Bold', 8)
            canvas.drawString((page_width - text_width) / 2, 0.28*inch, footer_text)
            
            # Page number
            canvas.setFont('Helvetica', 7)
            canvas.setFillColor(colors.HexColor('#6b7280'))
            page_text = f"Page {canvas.getPageNumber()}"
            canvas.drawRightString(page_width - 0.5*inch, 0.28*inch, page_text)
            
            canvas.restoreState()
        
        # Use PORTRAIT orientation
        doc = SimpleDocTemplate(buffer, pagesize=letter, 
                                bottomMargin=0.5*inch, topMargin=0.5*inch,
                                rightMargin=0.5*inch, leftMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1e3a5f'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Title
        title = Paragraph('RAINFALL & TIDE TRENDS REPORT', title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.08*inch))
        
        # Metadata with professional styling
        metadata_style = ParagraphStyle(
            'Metadata',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#4a5568'),
            leading=11,
            alignment=TA_CENTER
        )
        
        metadata_text = f'''
        <b>Report Generated:</b> {datetime.now().strftime("%B %d, %Y at %I:%M %p")} | 
        <b>Time Range:</b> {range_label} | 
        <b>Total Data Points:</b> {len(combined_data):,} records | 
        <b>Document Type:</b> Environmental Monitoring Data | 
        <b>Prepared By:</b> Silay City DRRMO
        '''
        
        metadata_para = Paragraph(metadata_text, metadata_style)
        metadata_table = Table([[metadata_para]], colWidths=[7*inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eff6ff')),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#3b82f6')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Add charts to PDF - use captured images from frontend if available
        if rainfall_chart_b64 and tide_chart_b64:
            try:
                # RLImage and PageBreak are already imported in outer scope
                
                # Decode base64 images (remove data:image/png;base64, prefix if present)
                rainfall_image_data = rainfall_chart_b64.split(',')[1] if ',' in rainfall_chart_b64 else rainfall_chart_b64
                tide_image_data = tide_chart_b64.split(',')[1] if ',' in tide_chart_b64 else tide_chart_b64
                
                # Decode base64 to bytes
                rainfall_bytes = base64.b64decode(rainfall_image_data)
                tide_bytes = base64.b64decode(tide_image_data)
                
                # Create BytesIO objects
                rainfall_buffer = BytesIO(rainfall_bytes)
                tide_buffer = BytesIO(tide_bytes)
                
                # Add charts title
                charts_title_style = ParagraphStyle(
                    'ChartsTitle',
                    parent=styles['Heading2'],
                    fontSize=12,
                    textColor=colors.HexColor('#1e3a5f'),
                    spaceAfter=10,
                    fontName='Helvetica-Bold'
                )
                charts_title = Paragraph('Visual Trends Analysis', charts_title_style)
                elements.append(charts_title)
                elements.append(Spacer(1, 0.1*inch))
                
                # Add rainfall chart - BIGGER
                rainfall_img = RLImage(rainfall_buffer, width=7*inch, height=3.5*inch)
                elements.append(rainfall_img)
                elements.append(Spacer(1, 0.2*inch))
                
                # Add tide chart - BIGGER
                tide_img = RLImage(tide_buffer, width=7*inch, height=3.5*inch)
                elements.append(tide_img)
                
                # Page break after charts for cleaner layout
                elements.append(PageBreak())
                
                # Add section title for data table
                data_table_title_style = ParagraphStyle(
                    'DataTableTitle',
                    parent=styles['Heading2'],
                    fontSize=11,
                    textColor=colors.HexColor('#1e3a5f'),
                    spaceAfter=6,
                    fontName='Helvetica-Bold'
                )
                data_table_title = Paragraph('Detailed Data Records', data_table_title_style)
                elements.append(data_table_title)
                elements.append(Spacer(1, 0.08*inch))
                
            except Exception as e:
                logger.error(f"Error adding chart images to PDF: {str(e)}")
                # Continue without charts if there's an error
                pass
        else:
            # Fallback to matplotlib charts if no images provided
            try:
                # Prepare data by year for chart generation
                year_data = {}
                for data in combined_data:
                    year = data['year']
                    if year not in year_data:
                        year_data[year] = {'timestamps': [], 'rainfall': [], 'tide': []}
                    
                    year_data[year]['timestamps'].append(data['timestamp'])
                    year_data[year]['rainfall'].append(data['rainfall'].value_mm if data['rainfall'] else 0)
                    year_data[year]['tide'].append(data['tide'].height_m if data['tide'] else 0)
                
                # Year colors matching the web interface
                year_colors = {
                    2025: '#473672',  # Purple
                    2024: '#53629E',  # Blue
                    2023: '#87BAC3',  # Light Blue
                }
                
                # Create charts with smooth styling matching web interface
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 7))
                fig.patch.set_facecolor('white')
                
                # Calculate date range for formatting
                if len(combined_data) > 0:
                    date_range = (combined_data[-1]['timestamp'] - combined_data[0]['timestamp']).total_seconds() / 86400
                
                # Rainfall chart - matching web interface style
                for year in sorted(year_data.keys(), reverse=True):
                    data = year_data[year]
                    color = year_colors.get(year, '#1e3a5f')
                    
                    # Plot with fill_between for gradient effect (matching web)
                    line = ax1.plot(data['timestamps'], data['rainfall'], 
                                   label=f'{year}', color=color, linewidth=2.5, alpha=0.9)[0]
                    
                    # Add filled area under the curve with gradient effect
                    ax1.fill_between(data['timestamps'], data['rainfall'], 
                                    alpha=0.15, color=color, linewidth=0)
                
                ax1.set_title('Rainfall Trends', fontsize=13, fontweight='bold', color='#1e3a5f', 
                             pad=15, loc='left')
                ax1.set_ylabel('Rainfall (mm)', fontsize=10, color='#4a5568', fontweight='600')
                ax1.grid(True, alpha=0.15, linestyle='-', linewidth=0.8, color='#94a3b8')
                ax1.tick_params(axis='both', labelsize=9, colors='#4a5568')
                ax1.set_facecolor('#fafafa')
                ax1.spines['top'].set_visible(False)
                ax1.spines['right'].set_visible(False)
                ax1.spines['left'].set_color('#cbd5e0')
                ax1.spines['bottom'].set_color('#cbd5e0')
                ax1.set_ylim(bottom=0)
                
                # Format x-axis dates for rainfall
                if len(combined_data) > 0:
                    if date_range <= 1:
                        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                    elif date_range <= 7:
                        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
                        ax1.xaxis.set_major_locator(mdates.DayLocator())
                    else:
                        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
                        ax1.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, int(date_range/10))))
                
                if len(year_data) > 1:
                    ax1.legend(fontsize=9, loc='upper left', framealpha=0.95, 
                              edgecolor='#cbd5e0', fancybox=True, shadow=False)
                
                # Tide Level chart - matching web interface style
                for year in sorted(year_data.keys(), reverse=True):
                    data = year_data[year]
                    color = year_colors.get(year, '#1e3a5f')
                    
                    # Plot with fill_between for gradient effect (matching web)
                    line = ax2.plot(data['timestamps'], data['tide'], 
                                   label=f'{year}', color=color, linewidth=2.5, alpha=0.9)[0]
                    
                    # Add filled area under the curve with gradient effect
                    ax2.fill_between(data['timestamps'], data['tide'], 
                                    alpha=0.15, color=color, linewidth=0)
                
                ax2.set_title('Tide Level Trends', fontsize=13, fontweight='bold', color='#1e3a5f', 
                             pad=15, loc='left')
                ax2.set_xlabel('Date & Time', fontsize=10, color='#4a5568', fontweight='600')
                ax2.set_ylabel('Tide Level (m)', fontsize=10, color='#4a5568', fontweight='600')
                ax2.grid(True, alpha=0.15, linestyle='-', linewidth=0.8, color='#94a3b8')
                ax2.tick_params(axis='both', labelsize=9, colors='#4a5568')
                ax2.set_facecolor('#fafafa')
                ax2.spines['top'].set_visible(False)
                ax2.spines['right'].set_visible(False)
                ax2.spines['left'].set_color('#cbd5e0')
                ax2.spines['bottom'].set_color('#cbd5e0')
                ax2.set_ylim(bottom=0)
                
                # Format x-axis dates for tide
                if len(combined_data) > 0:
                    if date_range <= 1:
                        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                        ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                    elif date_range <= 7:
                        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))
                        ax2.xaxis.set_major_locator(mdates.DayLocator())
                    else:
                        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
                        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, int(date_range/10))))
                
                # Rotate x-axis labels for better readability
                plt.setp(ax2.xaxis.get_majorticklabels(), rotation=0, ha='center')
                
                if len(year_data) > 1:
                    ax2.legend(fontsize=9, loc='upper left', framealpha=0.95, 
                              edgecolor='#cbd5e0', fancybox=True, shadow=False)
                
                plt.tight_layout(pad=2.0)
                
                # Save chart to BytesIO
                chart_buffer = BytesIO()
                plt.savefig(chart_buffer, format='png', dpi=180, bbox_inches='tight', 
                           facecolor='white', edgecolor='none', pad_inches=0.1)
                chart_buffer.seek(0)
                plt.close()
                
                # Add chart to PDF
                from reportlab.platypus import Image as RLImage
                chart_image = RLImage(chart_buffer, width=7*inch, height=6.5*inch)
                elements.append(chart_image)
                elements.append(Spacer(1, 0.15*inch))
                
                # Add section title for data table
                data_table_title_style = ParagraphStyle(
                    'DataTableTitle',
                    parent=styles['Heading2'],
                    fontSize=11,
                    textColor=colors.HexColor('#1e3a5f'),
                    spaceAfter=6,
                    fontName='Helvetica-Bold'
                )
                data_table_title = Paragraph('Detailed Data Records', data_table_title_style)
                elements.append(data_table_title)
                elements.append(Spacer(1, 0.08*inch))
                
            except Exception as e:
                logger.error(f"Error generating matplotlib charts for PDF: {str(e)}")
                # Continue without charts if there's an error
                pass
        
        # Table text styles
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.white
        )
        
        cell_style_center = ParagraphStyle(
            'CellStyleCenter',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER
        )
        
        cell_style_right = ParagraphStyle(
            'CellStyleRight',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT
        )
        
        # Table headers - ADD YEAR COLUMN
        table_data = [[
            Paragraph('#', header_style),
            Paragraph('Year', header_style),
            Paragraph('Date & Time', header_style),
            Paragraph('Rainfall (mm)', header_style),
            Paragraph('Tide Level (m)', header_style)
        ]]
        
        # Add all records with year information
        manila_tz = pytz.timezone('Asia/Manila')
        
        for idx, data in enumerate(combined_data, 1):
            rainfall_value = f"{data['rainfall'].value_mm:.2f}" if data['rainfall'] else '0.00'
            tide_value = f"{data['tide'].height_m:.2f}" if data['tide'] else '0.00'
            
            # Show the year from the data dictionary
            year_display = str(data['year'])
            
            # Convert timestamp to Manila timezone for display
            local_timestamp = data['timestamp'].astimezone(manila_tz)
            
            table_data.append([
                Paragraph(str(idx), cell_style_center),
                Paragraph(year_display, cell_style_center),
                Paragraph(local_timestamp.strftime('%m-%d  %H:%M'), cell_style_center),
                Paragraph(rainfall_value, cell_style_right),
                Paragraph(tide_value, cell_style_right)
            ])
        
        # Column widths for portrait - adjusted for year column
        col_widths = [
            0.4*inch,   # #
            0.6*inch,   # Year
            2.2*inch,   # Date & Time (no year in format now)
            1.9*inch,   # Rainfall
            1.9*inch    # Tide Level
        ]
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            
            # Data rows styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e0')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Border styling
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#1e3a5f')),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#cbd5e0')),
        ]))
        
        elements.append(table)
        doc.build(elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
        
        # Write buffer content to response
        response.write(buffer.getvalue())
        buffer.close()
        
        return response


@login_required
def export_flood_records(request):
    """Export flood records to CSV or PDF"""
    import csv
    from django.http import HttpResponse
    from datetime import datetime
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT
    import io
    
    export_type = request.GET.get('type', 'csv')
    start_year = request.GET.get('start_year')
    end_year = request.GET.get('end_year')
    
    # Fetch flood records with optional year filtering
    flood_records = FloodRecord.objects.all().order_by('-date')
    
    # Apply year filters if provided
    if start_year:
        try:
            flood_records = flood_records.filter(date__year__gte=int(start_year))
        except ValueError:
            pass
    
    if end_year:
        try:
            flood_records = flood_records.filter(date__year__lte=int(end_year))
        except ValueError:
            pass
    
    if export_type == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'flood_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        writer.writerow(['# Flood Records Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {flood_records.count()}'])
        writer.writerow([])
        
        writer.writerow([
            '#', 'Date', 'Event', 'Barangays', 'Dead', 'Injured', 'Missing',
            'Affected Persons', 'Affected Families', 'Houses Damaged (Partial)',
            'Houses Damaged (Total)', 'Infrastructure Damage (PHP)', 'Agriculture Damage (PHP)',
            'Institutions Damage (PHP)', 'Private/Commercial Damage (PHP)', 'Total Damage (PHP)'
        ])
        
        for idx, record in enumerate(flood_records, 1):
            writer.writerow([
                idx,
                record.date.strftime('%Y-%m-%d'),
                record.event,
                record.affected_barangays,
                record.casualties_dead,
                record.casualties_injured,
                record.casualties_missing,
                record.affected_persons,
                record.affected_families,
                record.houses_damaged_partially,
                record.houses_damaged_totally,
                f'₱{record.damage_infrastructure_php:,.2f}',
                f'₱{record.damage_agriculture_php:,.2f}',
                f'₱{record.damage_institutions_php:,.2f}',
                f'₱{record.damage_private_commercial_php:,.2f}',
                f'₱{record.damage_total_php:,.2f}'
            ])
        
        return response
    
    elif export_type == 'pdf':
        from reportlab.platypus import Image as RLImage
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        
        # Use BytesIO buffer for PDF generation
        buffer = io.BytesIO()
        response = HttpResponse(content_type='application/pdf')
        filename = f'flood_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Custom page template with header and footer (LANDSCAPE)
        def add_header_footer(canvas, doc):
            canvas.saveState()
            
            # Header - DRRMO logo/header
            header_path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR / 'static', 'images', 'drrmo_header.png')
            if os.path.exists(header_path):
                try:
                    page_width = landscape(letter)[0]
                    canvas.drawImage(header_path, 0, doc.height + doc.topMargin, 
                                   width=page_width, height=0.9*inch, 
                                   preserveAspectRatio=True, mask='auto')
                except:
                    pass
            
            # Footer line
            page_width = landscape(letter)[0]
            canvas.setStrokeColor(colors.HexColor('#1e3a5f'))
            canvas.setLineWidth(2)
            canvas.line(0.4*inch, 0.45*inch, page_width - 0.4*inch, 0.45*inch)
            
            # Footer text
            canvas.setFont('Helvetica-Bold', 8)
            canvas.setFillColor(colors.HexColor('#1e3a5f'))
            footer_text = "SILAY CITY DISASTER RISK REDUCTION & MANAGEMENT COUNCIL"
            text_width = canvas.stringWidth(footer_text, 'Helvetica-Bold', 8)
            canvas.drawString((page_width - text_width) / 2, 0.28*inch, footer_text)
            
            # Page number
            canvas.setFont('Helvetica', 7)
            canvas.setFillColor(colors.HexColor('#6b7280'))
            page_text = f"Page {canvas.getPageNumber()}"
            canvas.drawRightString(page_width - 0.4*inch, 0.28*inch, page_text)
            
            canvas.restoreState()
        
        # Use LANDSCAPE orientation
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), 
                               topMargin=1.3*inch, bottomMargin=1*inch,
                               leftMargin=0.5*inch, rightMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1e3a5f'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Title
        title = Paragraph('FLOOD RECORDS & DAMAGE ASSESSMENT REPORT', title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.08*inch))
        
        # Metadata with professional styling
        metadata_style = ParagraphStyle(
            'Metadata',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#4a5568'),
            leading=11,
            alignment=TA_CENTER
        )
        
        # Build metadata text with optional filter info
        filter_info = ""
        if start_year or end_year:
            if start_year and end_year:
                filter_info = f" | <b>Filtered:</b> Years {start_year} - {end_year}"
            elif start_year:
                filter_info = f" | <b>Filtered:</b> From year {start_year}"
            elif end_year:
                filter_info = f" | <b>Filtered:</b> Up to year {end_year}"
        
        metadata_text = f'''
        <b>Report Generated:</b> {datetime.now().strftime("%B %d, %Y at %I:%M %p")} | 
        <b>Total Flood Events:</b> {flood_records.count():,} records{filter_info} | 
        <b>Document Type:</b> Historical Flood Event Documentation | 
        <b>Prepared By:</b> Silay City DRRMO
        '''
        
        metadata_para = Paragraph(metadata_text, metadata_style)
        metadata_table = Table([[metadata_para]], colWidths=[9.5*inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eff6ff')),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#3b82f6')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.12*inch))
        
        # Table text styles
        header_style = ParagraphStyle(
            'HeaderStyle',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.white
        )
        
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
            wordWrap='CJK'
        )
        
        cell_style_center = ParagraphStyle(
            'CellStyleCenter',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_CENTER
        )
        
        cell_style_right = ParagraphStyle(
            'CellStyleRight',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_RIGHT
        )
        
        # Table headers
        table_data = [[
            Paragraph('#', header_style),
            Paragraph('Date', header_style),
            Paragraph('Event', header_style),
            Paragraph('Barangays', header_style),
            Paragraph('Casualties<br/>(D/I/M)', header_style),
            Paragraph('Affected<br/>Persons', header_style),
            Paragraph('Affected<br/>Families', header_style),
            Paragraph('Houses<br/>(P/T)', header_style),
            Paragraph('Infrastructure<br/>Damage (PHP)', header_style),
            Paragraph('Agriculture<br/>Damage (PHP)', header_style),
            Paragraph('Total<br/>Damage (PHP)', header_style)
        ]]
        
        # Add all records without truncating
        for idx, record in enumerate(flood_records, 1):
            # Format casualties as D/I/M
            casualties = f"{record.casualties_dead}/{record.casualties_injured}/{record.casualties_missing}"
            
            # Format houses as P/T
            houses = f"{record.houses_damaged_partially}/{record.houses_damaged_totally}"
            
            # Format currency values (use PHP instead of peso symbol)
            infra_dmg = f"PHP {record.damage_infrastructure_php:,.0f}"
            agri_dmg = f"PHP {record.damage_agriculture_php:,.0f}"
            total_dmg = f"PHP {record.damage_total_php:,.0f}"
            
            table_data.append([
                Paragraph(str(idx), cell_style_center),
                Paragraph(record.date.strftime('%Y-%m-%d'), cell_style_center),
                Paragraph(str(record.event), cell_style),  # No truncation
                Paragraph(str(record.affected_barangays), cell_style),  # No truncation
                Paragraph(casualties, cell_style_center),
                Paragraph(f"{record.affected_persons:,}", cell_style_right),
                Paragraph(f"{record.affected_families:,}", cell_style_right),
                Paragraph(houses, cell_style_center),
                Paragraph(infra_dmg, cell_style_right),
                Paragraph(agri_dmg, cell_style_right),
                Paragraph(total_dmg, cell_style_right)
            ])
        
        # Optimized column widths for landscape
        col_widths = [
            0.3*inch,   # #
            0.75*inch,  # Date
            1.5*inch,   # Event (wider)
            1.4*inch,   # Barangays (wider to prevent cutoff)
            0.65*inch,  # Casualties
            0.75*inch,  # Affected Persons
            0.75*inch,  # Affected Families
            0.6*inch,   # Houses
            1.05*inch,  # Infrastructure
            1.0*inch,   # Agriculture
            1.05*inch   # Total Damage
        ]
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            
            # Data rows styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            
            # Vertical lines for better separation
            ('LINEAFTER', (0, 0), (0, -1), 1, colors.HexColor('#d1d5db')),
            ('LINEAFTER', (1, 0), (1, -1), 1, colors.HexColor('#d1d5db')),
            ('LINEAFTER', (3, 0), (3, -1), 1, colors.HexColor('#d1d5db')),
            ('LINEAFTER', (7, 0), (7, -1), 1, colors.HexColor('#d1d5db')),
        ]))
        
        elements.append(table)
        doc.build(elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
        
        # Write buffer content to response
        response.write(buffer.getvalue())
        buffer.close()
        
        return response

@login_required
def flood_records_list(request):
    """View to display historical flood records in a dedicated list page."""
    # Get filters
    start_year = request.GET.get('start_year')
    end_year = request.GET.get('end_year')
    search_query = request.GET.get('search', '')
    
    # Get all flood records ordered by date
    flood_records_queryset = FloodRecord.objects.all().order_by('-date')
    
    # Apply filters
    if start_year:
        flood_records_queryset = flood_records_queryset.filter(date__year__gte=start_year)
    if end_year:
        flood_records_queryset = flood_records_queryset.filter(date__year__lte=end_year)
    if search_query:
        flood_records_queryset = flood_records_queryset.filter(event__icontains=search_query) | \
                                 flood_records_queryset.filter(affected_barangays__icontains=search_query)

    # Pagination
    page_number = request.GET.get('page', 1)
    records_per_page = 20
    paginator = Paginator(flood_records_queryset, records_per_page)
    
    try:
        flood_records_page = paginator.page(page_number)
    except PageNotAnInteger:
        flood_records_page = paginator.page(1)
    except EmptyPage:
        flood_records_page = paginator.page(paginator.num_pages)
    
    # Format numbers for display
    flood_records = []
    for record in flood_records_page:
        record_dict = {
            'id': record.id,
            'event': record.event,
            'date': record.date,
            'affected_barangays': record.affected_barangays,
            'casualties_dead_fmt': "{:,.0f}".format(record.casualties_dead),
            'casualties_injured_fmt': "{:,.0f}".format(record.casualties_injured),
            'casualties_missing_fmt': "{:,.0f}".format(record.casualties_missing),
            'affected_persons_fmt': "{:,.0f}".format(record.affected_persons),
            'affected_families_fmt': "{:,.0f}".format(record.affected_families),
            'houses_damaged_partially_fmt': "{:,.0f}".format(record.houses_damaged_partially),
            'houses_damaged_totally_fmt': "{:,.0f}".format(record.houses_damaged_totally),
            'damage_infrastructure_php_fmt': "{:,.2f}".format(record.damage_infrastructure_php),
            'damage_agriculture_php_fmt': "{:,.2f}".format(record.damage_agriculture_php),
        'damage_total_php_fmt': "{:,.2f}".format(record.damage_total_php),
            'barangay_data_json': json.dumps(record.barangay_data or {})
        }
        flood_records.append(record_dict)

    # Aggregate data for graphs (based on the filtered queryset)
    graph_queryset = flood_records_queryset.order_by('date').values(
        'date', 'casualties_dead', 'casualties_injured', 'casualties_missing',
        'affected_persons', 'affected_families', 'houses_damaged_partially', 'houses_damaged_totally',
        'damage_infrastructure_php', 'damage_agriculture_php', 'damage_institutions_php',
        'damage_private_commercial_php', 'damage_total_php', 'barangay_data'
    )

    graph_dates = []
    casualties_data = {'dead': [], 'injured': [], 'missing': []}
    affected_data = {'persons': [], 'families': []}
    houses_data = {'partially': [], 'totally': []}
    damage_data = {'infrastructure': [], 'agriculture': [], 'institutions': [], 'private_commercial': [], 'total': []}
    barangay_data_by_date = {}

    for record in graph_queryset:
        date_str = record['date'].strftime('%Y-%m-%d')
        graph_dates.append(date_str)
        casualties_data['dead'].append(record['casualties_dead'])
        casualties_data['injured'].append(record['casualties_injured'])
        casualties_data['missing'].append(record['casualties_missing'])
        affected_data['persons'].append(record['affected_persons'])
        affected_data['families'].append(record['affected_families'])
        houses_data['partially'].append(record['houses_damaged_partially'])
        houses_data['totally'].append(record['houses_damaged_totally'])
        damage_data['infrastructure'].append(float(record['damage_infrastructure_php']))
        damage_data['agriculture'].append(float(record['damage_agriculture_php']))
        damage_data['institutions'].append(float(record['damage_institutions_php']))
        damage_data['private_commercial'].append(float(record['damage_private_commercial_php']))
        damage_data['total'].append(float(record['damage_total_php']))
        barangay_data_by_date[date_str] = record.get('barangay_data', {}) or {}

    # Get available years for filter
    available_years = FloodRecord.objects.dates('date', 'year', order='DESC')
    years_list = [date.year for date in available_years]

    context = {
        'flood_records': flood_records,
        'flood_records_page': flood_records_page,
        'available_years': years_list,
        'start_year': start_year,
        'end_year': end_year,
        'search_query': search_query,
        'total_count': flood_records_queryset.count(),
        'graph_dates': graph_dates,
        'casualties_data': casualties_data,
        'affected_data': affected_data,
        'houses_data': houses_data,
        'damage_data': damage_data,
        'barangay_data_by_date': json.dumps(barangay_data_by_date),
    }
    return render(request, 'monitoring/flood_records_list.html', context)